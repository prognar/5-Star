"""Snowflake SQL API client for PHIDB_PROD.EW — PAT auth, no MCP.

Run via snow.ps1 (sets SNOWFLAKE_PAT from the DPAPI-encrypted token before
invoking python), not directly — there is no PAT in this process otherwise.
"""
import csv
import datetime
import os
import time
import uuid

import requests

ACCOUNT = os.environ.get("SNOWFLAKE_ACCOUNT", "lj10919.us-east-1")
ROLE = os.environ.get("SNOWFLAKE_ROLE", "PH_USER_DATASCIENCE")
# PH_USER_EW is not granted to this user — do not use it as a fallback/default.
WAREHOUSE = os.environ.get("SNOWFLAKE_WAREHOUSE", "PROD_ANALYTIC_WH")
DATABASE = os.environ.get("SNOWFLAKE_DATABASE", "DATASCIENCE")
SCHEMA = os.environ.get("SNOWFLAKE_SCHEMA", "AXC1195")
BASE_URL = f"https://{ACCOUNT}.snowflakecomputing.com/api/v2/statements"

_EPOCH = datetime.date(1970, 1, 1)


def epoch_to_date(epoch_days):
    """Snowflake DATE columns come back as epoch days over the SQL API."""
    if epoch_days is None:
        return None
    return _EPOCH + datetime.timedelta(days=int(epoch_days))


def _headers():
    pat = os.environ.get("SNOWFLAKE_PAT")
    if not pat:
        raise RuntimeError("SNOWFLAKE_PAT not set — run this script via snow.ps1")
    return {
        "Authorization": f"Bearer {pat}",
        "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "snow_client/1.0",
    }


def _poll(handle, timeout):
    deadline = time.time() + timeout
    url = f"{BASE_URL}/{handle}"
    while True:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 202:
            if time.time() > deadline:
                raise TimeoutError(f"statement {handle} still running after {timeout}s")
            time.sleep(1)
            continue
        if not resp.ok:
            raise RuntimeError(f"{resp.status_code} {resp.reason}: {resp.text}")
        return resp.json()


def _fetch_partition(handle, index, timeout):
    url = f"{BASE_URL}/{handle}"
    resp = requests.get(url, headers=_headers(), params={"partition": index}, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.reason}: {resp.text}")
    return resp.json()


def query(sql, timeout=600, warehouse=None, role=None, database=None, schema=None):
    """Run one SQL statement via Snowflake's SQL API. Returns (columns, rows).

    requests negotiates gzip automatically via Accept-Encoding; large result
    sets are paginated server-side and stitched back together here.
    """
    body = {
        "statement": sql,
        "timeout": timeout,
        "warehouse": warehouse or WAREHOUSE,
        "role": role or ROLE,
        "database": database or DATABASE,
        "schema": schema or SCHEMA,
    }

    resp = requests.post(
        BASE_URL,
        headers=_headers(),
        json=body,
        params={"requestId": str(uuid.uuid4()), "async": "false"},
        timeout=min(timeout, 55),
    )

    if resp.status_code == 202:
        data = _poll(resp.json()["statementHandle"], timeout)
    else:
        if not resp.ok:
            raise RuntimeError(f"{resp.status_code} {resp.reason}: {resp.text}")
        data = resp.json()

    meta = data["resultSetMetaData"]
    columns = [c["name"] for c in meta["rowType"]]
    rows = list(data.get("data", []))

    handle = data.get("statementHandle")
    partitions = meta.get("partitionInfo", [])
    if handle and len(partitions) > 1:
        for i in range(1, len(partitions)):
            part = _fetch_partition(handle, i, timeout)
            rows.extend(part.get("data", []))

    return columns, rows


def to_csv(columns, rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

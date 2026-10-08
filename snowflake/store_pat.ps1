<#
One-time (and per-rotation) store of a Snowflake Programmatic Access Token.
Encrypts with Windows DPAPI, tied to this Windows user + this machine.
The encrypted file lives outside OneDrive, at %LOCALAPPDATA%\snowflake\pat.txt.
#>

$dir = Join-Path $env:LOCALAPPDATA "snowflake"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$path = Join-Path $dir "pat.txt"

$secure = Read-Host "Paste Snowflake PAT (generated under role PH_USER_EW)" -AsSecureString
if ($secure.Length -eq 0) {
    Write-Error "No token entered."
    exit 1
}

$secure | ConvertFrom-SecureString | Set-Content -Path $path -Encoding UTF8

Write-Host "Stored encrypted PAT at $path"
Write-Host "Verify with: powershell -ExecutionPolicy Bypass -File snow.ps1 smoke_test.py"

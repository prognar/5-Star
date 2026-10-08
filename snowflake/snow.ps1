<#
Run a python script with SNOWFLAKE_PAT decrypted (DPAPI) into the environment.
Usage: powershell -ExecutionPolicy Bypass -File snow.ps1 <script.py> [args...]
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Script,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$path = Join-Path $env:LOCALAPPDATA "snowflake\pat.txt"
if (-not (Test-Path $path)) {
    Write-Error "No stored PAT at $path - run store_pat.ps1 first."
    exit 1
}

$secure = Get-Content $path | ConvertTo-SecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$env:SNOWFLAKE_PAT = $plain
python $Script @ScriptArgs
$exitCode = $LASTEXITCODE

Remove-Item Env:\SNOWFLAKE_PAT
exit $exitCode

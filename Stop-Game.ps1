<#
.SYNOPSIS  Stops a running game (server and tunnel) and deletes the temporary tunnel. Safe to run any time.
#>
$ErrorActionPreference = "Continue"

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match "^python" -and $_.CommandLine -match "app\.main" } |
    ForEach-Object { Write-Host "Stopping game server (pid $($_.ProcessId))"; Stop-Process -Id $_.ProcessId -Force }

Get-Process -Name devtunnel -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "Stopping tunnel (pid $($_.Id))"; Stop-Process -Id $_.Id -Force }

$idFile = Join-Path $env:TEMP "bz-tunnel-id.txt"
if (Test-Path $idFile) {
    $id = (Get-Content $idFile -Raw).Trim()
    if ($id) { Write-Host "Deleting tunnel $id"; devtunnel delete $id -f 2>&1 | Out-Null }
    Remove-Item $idFile -ErrorAction SilentlyContinue
}
Write-Host "Done."

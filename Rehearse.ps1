<#
.SYNOPSIS
  Rehearsal: fills a RUNNING game (Start-Game.ps1) with bots that haggle like people, so you can see the host screen come alive.

.EXAMPLE
  .\Rehearse.ps1                    # 25 bots + 6 late joiners, 5-minute game, with a festive rush and a squeeze
  .\Rehearse.ps1 -Bots 40 -Delay 2  # heavier load, faster bots
  .\Rehearse.ps1 -ResetAfter        # wipe the rehearsal when done (so the real lobby is clean)

  Bots speak English, Hinglish, Hindi and other Indian languages and try prompt tricks. Real people can join during a rehearsal.
  Click "New game" on the host screen before the real event.
#>
param(
    [int]$Port = 8000,
    [int]$Bots = 25,
    [int]$Late = 6,
    [double]$Delay = 3,
    [int]$Minutes = 5,
    [switch]$ResetAfter
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\Start-Game.ps1 once first." }
$key = ((Get-Content (Join-Path $PSScriptRoot ".env")) | Where-Object { $_ -match "^\s*ADMIN_KEY\s*=" } | Select-Object -First 1) -replace "^\s*ADMIN_KEY\s*=\s*", ""
if (-not $key) { throw "No host key found. Run .\Start-Game.ps1 first." }
$env:PYTHONIOENCODING = "utf-8"
& $py tools\bots.py --url "http://localhost:$Port" --n $Bots --late $Late --events --delay $Delay --admin-key $key.Trim() --reset --start --minutes $Minutes --end
if ($ResetAfter) {
    curl.exe -s -m 10 -X POST -H "X-Admin-Key: $($key.Trim())" -H "Content-Type: application/json" -d "{}" "http://localhost:$Port/api/admin/reset" | Out-Null
    Write-Host "Rehearsal wiped. The lobby is clean."
}

<#
.SYNOPSIS
  Starts Bargain Bazaar: game server + public link + host screen, with a pre-flight check.

.EXAMPLE
  .\Start-Game.ps1               # normal: public dev tunnel + host screen opens in your browser
  .\Start-Game.ps1 -Try          # play it yourself on this PC: host screen + two separate player tabs (no public link)
  .\Start-Game.ps1 -NoTunnel     # local only (dry run on this PC, or a bot rehearsal)
  .\Start-Game.ps1 -Resume       # after a crash or restart: keep the players, bags and scores
  .\Start-Game.ps1 -NewKey       # generate a new host key

  Press Ctrl+C in this window to stop everything (the tunnel is deleted too).
#>
param(
    [int]$Port = 8000,
    [switch]$NoTunnel,
    [switch]$Resume,
    [switch]$NewKey,
    [switch]$NoBrowser,
    [switch]$Try
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Try) { $NoTunnel = $true }

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }
function Ok($text) { Write-Host "  [ok]   $text" -ForegroundColor Green }
function Bad($text) { Write-Host "  [warn] $text" -ForegroundColor Yellow }

# Run a native command without PowerShell turning its stderr into an error.
function Quiet([scriptblock]$cmd) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $cmd 2>&1 | Out-String } finally { $ErrorActionPreference = $old }
}

# curl.exe behaves the same in Windows PowerShell 5.1 and PowerShell 7 (Invoke-RestMethod can stall on the proxy for localhost).
function Get-Json([string]$url, [string]$method = "GET", [string]$key = "", [int]$timeout = 3) {
    $a = @("-s", "-m", "$timeout", "-X", $method)
    if ($key) { $a += @("-H", "X-Admin-Key: $key") }
    $a += $url
    $t = Quiet { curl.exe @a }
    try { return ($t | ConvertFrom-Json) } catch { return $null }
}

Say "`nBARGAIN BAZAAR: starting up" Cyan

# ---------------------------------------------------------------- 1. Python environment
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $base = $null
    foreach ($c in "py", "python", "python3") { $cmd = Get-Command $c -ErrorAction SilentlyContinue; if ($cmd) { $base = $cmd.Source; break } }
    if (-not $base) { throw "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/" }
    Say "  Creating the Python environment (first run only)..."
    & $base -m venv (Join-Path $PSScriptRoot ".venv")
    if ($LASTEXITCODE) { throw "Could not create the virtual environment." }
}
$stamp = Join-Path $PSScriptRoot ".venv\.deps-stamp"
if (-not (Test-Path $stamp) -or (Get-Item "requirements.txt").LastWriteTime -gt (Get-Item $stamp).LastWriteTime) {
    Say "  Installing packages (first run only)..."
    & $py -m pip install -q --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE) { throw "pip install failed. Check your internet connection." }
    New-Item -ItemType File -Force $stamp | Out-Null
}
Ok "Python environment ready"

# ---------------------------------------------------------------- 2. settings (.env) and a stable host key
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $PSScriptRoot ".env.example") $envFile }
function Get-Setting($name) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -First 1
    if ($line) { return ($line -replace "^\s*$name\s*=\s*", "").Trim() } else { return "" }
}
function Set-Setting($name, $value) {
    $out = @(); $found = $false
    foreach ($l in (Get-Content $envFile)) {
        if ($l -match "^\s*$name\s*=") { $out += "$name=$value"; $found = $true } else { $out += $l }
    }
    if (-not $found) { $out += "$name=$value" }
    [System.IO.File]::WriteAllLines($envFile, $out, (New-Object System.Text.UTF8Encoding $false))
}
$adminKey = Get-Setting "ADMIN_KEY"
if ($NewKey -or -not $adminKey) {
    $adminKey = -join ((48..57) + (97..122) | Get-Random -Count 12 | ForEach-Object { [char]$_ })
    Set-Setting "ADMIN_KEY" $adminKey
}
$env:ADMIN_KEY = $adminKey
$env:PORT = "$Port"
if ($Resume) { $env:RESUME = "1" } else { Remove-Item Env:RESUME -ErrorAction SilentlyContinue }

# ---------------------------------------------------------------- 3. are the AI replies reachable? (only the one allowed account)
$provider = (Get-Setting "LLM_PROVIDER").ToLower()
$keyVars = @{ azure = @("LLM_API_KEY", "AZURE_OPENAI_API_KEY"); claude = @("LLM_API_KEY", "ANTHROPIC_API_KEY"); gemini = @("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY") }
$hasKey = $false
if ($keyVars.ContainsKey($provider)) { foreach ($k in $keyVars[$provider]) { if (Get-Setting $k) { $hasKey = $true } } }
if ($provider -in @("azure", "claude") -and -not $hasKey) {
    $res = if ($provider -eq "claude") { "https://ai.azure.com" } else { "https://cognitiveservices.azure.com" }
    $sub = Get-Setting "AZURE_SUBSCRIPTION_ID"
    $allowed = Get-Setting "AZURE_ALLOWED_ACCOUNT"
    if (-not $sub -or -not $allowed) {
        Bad "AZURE_SUBSCRIPTION_ID and AZURE_ALLOWED_ACCOUNT must both be set in .env. The game only ever uses that one account, never your default Azure subscription, so the AI replies are OFF."
    } elseif (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        Bad "The Azure CLI ('az') is not installed, so $((Get-Content (Join-Path $PSScriptRoot 'config\game.json') -Raw | ConvertFrom-Json).shopkeeper) will use ready-made lines."
    } else {
        $who = (Quiet { az account show --subscription $sub --query user.name -o tsv }).Trim()
        if (-not $who -or $who -match "ERROR") {
            Bad "Not signed in for the AI replies. Run:  az login   (sign in as $allowed)"
        } elseif ($who.ToLower() -ne $allowed.ToLower()) {
            Bad "That subscription is signed in as '$who', but the game may only use '$allowed'. The AI replies stay OFF (ready-made lines)."
        } else {
            $r = Quiet { az account get-access-token --resource $res --subscription $sub --query expiresOn -o tsv }
            if ($r -match "\d{4}-\d{2}-\d{2}") { Ok "AI replies ($provider) will use the Azure account $who only (the one allowed in .env)" }
            else { Bad "Could not get an Azure token for $who. Run:  az login   (sign in as $allowed)" }
        }
    }
} elseif ($hasKey) {
    Ok "AI replies ($provider) use an API key"
} elseif ($provider -eq "gemini") {
    Bad "No Gemini API key: set GEMINI_API_KEY in .env. Ready-made lines will be used."
} elseif ($provider -in @("", "none")) {
    Ok "No AI model set (LLM_PROVIDER=none): Raju Anna uses ready-made lines. To add a model, see docs\CONFIGURATION.md"
} elseif ($provider -notin @("azure", "claude")) {
    Bad "Unknown LLM_PROVIDER '$provider' (use none, azure, claude or gemini): ready-made lines only."
}

# ---------------------------------------------------------------- 4. port must be free
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Is another game running? Run .\Stop-Game.ps1 first."
}

# ---------------------------------------------------------------- 5. public link (dev tunnel)
$publicUrl = ""; $tunnel = $null; $tunnelId = ""
if (-not $NoTunnel) {
    if (-not (Get-Command devtunnel -ErrorAction SilentlyContinue)) {
        Bad "The 'devtunnel' tool is not installed, so the game runs on this PC only. Install:  winget install Microsoft.devtunnel"
    } else {
        if ((Quiet { devtunnel user show }) -notmatch "Logged in") { Say "  Signing in to dev tunnels..."; devtunnel user login | Out-Null }
        $log = Join-Path $env:TEMP "bz-devtunnel.out"
        Remove-Item $log, "$log.err" -ErrorAction SilentlyContinue
        $tunnel = Start-Process devtunnel -ArgumentList "host", "-p", $Port, "--allow-anonymous" -RedirectStandardOutput $log `
            -RedirectStandardError "$log.err" -WindowStyle Hidden -PassThru
        for ($i = 0; $i -lt 60 -and -not $publicUrl; $i++) {
            Start-Sleep -Milliseconds 500
            $t = Get-Content $log -Raw -ErrorAction SilentlyContinue
            # The tool prints two links on ONE line ("https://<id>.inc1.devtunnels.ms:8000, https://<id>-8000.inc1.devtunnels.ms").
            # Take the one without a port number: plain https on 443 also gets through office firewalls that block other ports.
            $line = [regex]::Match("$t", "Connect via browser:[^\r\n]*").Value
            $urls = @([regex]::Matches($line, "https://[^\s,]+") | ForEach-Object { $_.Value.TrimEnd("/") })
            $publicUrl = @($urls | Where-Object { $_ -notmatch ":\d+$" })[0]
            if (-not $publicUrl) { $publicUrl = $urls[0] }
            if ($t -match "tunnel:\s*(\S+)") { $tunnelId = $Matches[1] }
        }
        # The tunnel id is what Stop-Game uses to delete the tunnel (an account may own only 10), so make sure we have it.
        for ($i = 0; $publicUrl -and -not $tunnelId -and $i -lt 10; $i++) {
            Start-Sleep -Milliseconds 500
            if ((Get-Content $log -Raw -ErrorAction SilentlyContinue) -match "tunnel:\s*(\S+)") { $tunnelId = $Matches[1] }
        }
        if ($publicUrl) { Set-Content (Join-Path $env:TEMP "bz-tunnel-id.txt") $tunnelId; Ok "Public link created" }
        else { Bad "Could not read the tunnel link (see $log). The game runs on this PC only." }
    }
}
$env:PUBLIC_URL = $publicUrl

# ---------------------------------------------------------------- 6. keep the PC awake while the game runs
Add-Type -Namespace Win -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);' -ErrorAction SilentlyContinue
[void][Win.Power]::SetThreadExecutionState([uint32]2147483651)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED

# ---------------------------------------------------------------- 7. start the server
$srv = Start-Process -FilePath $py -ArgumentList "-m", "app.main" -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru
try {
    $local = "http://localhost:$Port"
    $up = $false
    for ($i = 0; $i -lt 40 -and -not $up; $i++) {
        Start-Sleep -Milliseconds 500
        $h = Get-Json "$local/healthz" "GET" "" 2
        $up = [bool]($h -and $h.ok)
    }
    if (-not $up) { throw "The game server did not start. Look for error messages above." }

    # -------------------------------------------------------------- 8. pre-flight
    Say "`nPre-flight check" Cyan
    Ok "Game server is running"
    if ($publicUrl) {
        $up2 = $false
        for ($i = 0; $i -lt 5 -and -not $up2; $i++) {            # a brand-new tunnel can take a few seconds to carry traffic
            $p = Get-Json "$publicUrl/healthz" "GET" "" 10
            $up2 = [bool]($p -and $p.ok)
            if (-not $up2) { Start-Sleep -Seconds 2 }
        }
        if ($up2) { Ok "Public link works from outside" }
        else { Bad "Public link did not answer yet. Wait 10 seconds and open it on your phone to double-check." }
    }
    if ($provider -notin @("", "none")) {
        $ai = Get-Json "$local/api/admin/test-ai" "POST" $adminKey 25
        if ($ai -and $ai.ok) { Ok ("AI replies answer in {0:N1}s" -f ($ai.ms / 1000)) }
        elseif ($ai) { Bad "AI replies: $($ai.message). Ready-made lines will be used." }
        else { Bad "Could not test the AI replies." }
    }

    $playerUrl = if ($publicUrl) { "$publicUrl/" } else { "$local/" }
    $adminUrl = "$local/admin?key=$adminKey"
    if ($publicUrl) { try { Set-Clipboard $playerUrl } catch { } }
    Say ""
    Say "==================================================================" Cyan
    Say "  PLAYERS JOIN AT :  $playerUrl" Green
    if ($publicUrl) { Say "                     (copied to your clipboard: paste it in the meeting chat)" Gray }
    Say "  HOST SCREEN     :  $adminUrl" Green
    Say "  Share ONLY the browser window 'Bargain Bazaar: Host screen' in your meeting." Gray
    Say "  Tip: move the mouse over the bottom bar for controls. Press H to hide them." Gray
    if ($publicUrl) { Say "  First-time visitors see a Microsoft 'developer tunnel' page: tell them to click Continue." Yellow }
    else { Say "  Local only: players on other computers cannot join." Yellow }
    if ($Try) {
        Say "  TRY MODE: a host tab and two player tabs open. In the player tabs join with two different names" Cyan
        Say "  (the second tab is $local/?p=2). Then hover the bottom bar of the host tab and click 'Open the shop'." Cyan
    }
    Say "  Press Ctrl+C here to stop everything." Gray
    Say "==================================================================`n" Cyan
    if (-not $NoBrowser) {
        Start-Process $adminUrl
        if ($Try) { Start-Sleep -Milliseconds 700; Start-Process "$local/"; Start-Sleep -Milliseconds 700; Start-Process "$local/?p=2" }
    }
    $srv.WaitForExit()
}
finally {
    if ($srv) { Quiet { taskkill /PID $srv.Id /T /F } | Out-Null }          # the whole tree: a venv python is a launcher stub
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
    if ($tunnelId) { Quiet { devtunnel delete $tunnelId -f } | Out-Null }
    [void][Win.Power]::SetThreadExecutionState([uint32]2147483648)
    Say "Stopped. Results from this game are in the 'data' folder." Gray
}

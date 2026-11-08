<#
  Ready to Fly v1.1 - the shared "get this PC ready" step for ArcGIS Earth Unlocked tools.
  Called by a tool's one-click .bat. Windows PowerShell 5.1 compatible (no PS7-only syntax).

  Checks, in order, and fixes what it can, in plain words:
    0. Internet (Windows' own NCSI verdict + probe) - only a heads-up, never a stop:
       no internet = ArcGIS Earth's online basemaps won't load; captive Wi-Fi = sign in first.
    1. Python 3.9+ (py launcher, python on PATH - ignoring the Microsoft Store stub - and the usual
       install folders). Missing: asks, then installs it for this user with Windows' own installer (winget),
       shown normally - nothing silent, nothing downloaded and run by this script, no Windows setting changed
       (v1.1). No winget: opens python.org's download page with what to click.
    2. Python libraries the tool needs (-Packages "pillow,pyserial"): pip install if missing.
    3. ArcGIS Earth (-NeedEarth): find it (remembered path, known folders, Windows' installed-programs
       list, folder search). Missing: offer Esri's free download page. Never installs it.
    4. ArcGIS Earth running: start it if needed.
    5. Automation API answering on http://localhost:8000 (-NeedApi): if ArcGIS Earth is running but the
       API never answers, explain how to switch it on.
  Writes the Python to use into python_path.txt (and the ArcGIS Earth path into ArcGIS_Earth_path.txt)
  in -Folder. Exit 0 = ready, 1 = stopped (the .bat pauses so the message can be read).
  Log: Ready_To_Fly_log.txt in -Folder.
#>
param(
    [string]$Folder = $PSScriptRoot,
    [string]$Tool = "this tool",
    [string]$Packages = "",          # comma list of pip names, e.g. "pillow,pyserial"
    [string]$Imports = "",           # matching import names, e.g. "PIL,serial" (defaults to the pip names)
    [switch]$NeedEarth,
    [switch]$NeedApi,
    [switch]$NeedTk,
    [int]$ApiWaitS = 90,
    [switch]$EarthOnly,              # only find ArcGIS Earth and save its path (taskbar shortcut maker)
    [switch]$Unattended              # no questions (answers 'no' to installs); for scheduled/test runs
)

$ErrorActionPreference = "Continue"
$VERSION = "1.1"
$MIN_PY = [version]"3.9"
$ESRI_PAGE = "https://www.esri.com/en-us/arcgis/products/arcgis-earth/downloads"
$PY_PAGE = "https://www.python.org/downloads/windows/"
$API = "http://localhost:8000/arcgisearth/camera"
$LogFile = Join-Path $Folder "Ready_To_Fly_log.txt"

function Log([string]$m) { try { Add-Content -Path $LogFile -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m) -Encoding UTF8 } catch {} }
function Say([string]$m, [string]$c = "Gray") { Write-Host $m -ForegroundColor $c; Log $m }
function Ok([string]$m)   { Say ("  OK   " + $m) "Green" }
function Warn([string]$m) { Say ("  NOTE " + $m) "Yellow" }
function Bad([string]$m)  { Say ("  STOP " + $m) "Red" }
function Ask([string]$q) {
    if ($Unattended) { Log ("ASK (unattended -> no): " + $q); return $false }
    Write-Host ""
    $a = Read-Host ($q + " [Y/N]")
    Log ("ASK: " + $q + " -> " + $a)
    return ($a -match '^\s*[Yy]')
}

# ---------------------------------------------------------------- 0. internet (heads-up only)
$script:Online = $null
function Test-Internet {
    if ($script:Online -ne $null) { return $script:Online }
    $verdict = "unknown"
    try {
        $profiles = @(Get-NetConnectionProfile -ErrorAction Stop)
        if ($profiles | Where-Object { $_.IPv4Connectivity -eq 'Internet' -or $_.IPv6Connectivity -eq 'Internet' }) { $verdict = "internet" }
        elseif ($profiles.Count -gt 0) { $verdict = "local" }
    } catch { $verdict = "unknown" }
    Log ("NCSI profile verdict: " + $verdict)
    # Confirm with the NCSI probe itself (also catches hotel/airport sign-in pages).
    try {
        $r = [System.Net.WebRequest]::Create("http://www.msftconnecttest.com/connecttest.txt")
        $r.Timeout = 4000; $r.ReadWriteTimeout = 4000
        $resp = $r.GetResponse()
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $txt = $sr.ReadToEnd(); $sr.Close(); $resp.Close()
        if ($txt -eq "Microsoft Connect Test") { $script:Online = "yes"; return "yes" }
        $script:Online = "portal"; return "portal"
    } catch { Log ("NCSI probe failed: " + $_.Exception.Message) }
    # NCSI probing can be switched off on work PCs: fall back to a plain web request.
    try {
        $r = [System.Net.WebRequest]::Create("https://www.python.org/")
        $r.Method = "HEAD"; $r.Timeout = 4000
        $resp = $r.GetResponse(); $resp.Close()
        $script:Online = "yes"; return "yes"
    } catch { Log ("HTTPS fallback failed: " + $_.Exception.Message) }
    if ($verdict -eq "internet") { $script:Online = "yes"; return "yes" }
    $script:Online = "no"; return "no"
}

# ---------------------------------------------------------------- 1. Python
function Get-PyVersion([string]$exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $null }
    if ($exe -match '\\WindowsApps\\') { return $null }          # Microsoft Store stub, not a real Python
    try {
        $out = & $exe -c "import sys;print('%d.%d.%d' % sys.version_info[:3])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return [version]($out | Select-Object -Last 1).Trim() }
    } catch {}
    return $null
}

function Find-Python {
    $cands = New-Object System.Collections.Generic.List[string]
    $saved = Join-Path $Folder "python_path.txt"
    if (Test-Path $saved) { $p = (Get-Content $saved -TotalCount 1); if ($p) { $cands.Add($p.Trim()) } }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try { $exe = & $py.Source -3 -c "import sys;print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $exe) { $cands.Add(($exe | Select-Object -Last 1).Trim()) } } catch {}
    }
    foreach ($c in @(Get-Command python -All -ErrorAction SilentlyContinue)) { $cands.Add($c.Source) }
    foreach ($root in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}")) {
        if ($root -and (Test-Path $root)) {
            Get-ChildItem -Path $root -Directory -Filter "Python3*" -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending | ForEach-Object { $cands.Add((Join-Path $_.FullName "python.exe")) }
        }
    }
    foreach ($c in $cands) {
        $v = Get-PyVersion $c
        if ($v -and $v -ge $MIN_PY) { return @{ Exe = $c; Version = $v } }
        if ($v) { Log ("too old: " + $c + " " + $v) }
    }
    return $null
}

function Install-Python {
    # v1.1 (2026-11-08): nothing silent, nothing downloaded and run by this script, no Windows setting changed.
    # Python comes from Windows' own installer (winget), shown normally, and the user answers its questions.
    # Without winget: open python.org's download page and say what to click.
    $net = Test-Internet
    if ($net -ne "yes") {
        if ($net -eq "portal") { Bad "This Wi-Fi wants you to sign in first (open a web browser), then click again." }
        else { Bad "Python needs to be downloaded, and this computer has no internet right now. Connect, then click again." }
        return $false
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Installing Python with Windows' own installer (winget)." "Cyan"
        Say "  If it asks you to agree to the terms, type Y and press Enter. It can take several minutes -" "Yellow"
        Say "  Windows Defender may slow the PC while it checks the new files. Don't close this window." "Yellow"
        foreach ($id in @("Python.Python.3.14", "Python.Python.3.13")) {
            # run in this window, nothing captured, so its own questions and progress show normally
            $p = Start-Process -FilePath $winget.Source -ArgumentList "install --exact --id $id --scope user" -NoNewWindow -Wait -PassThru
            Log ("winget " + $id + " exit " + $p.ExitCode)
            if (Find-Python) { return $true }
        }
        Warn "Windows' installer did not finish the job."
    } else {
        Warn "This PC does not have Windows' own installer (winget) - older Windows 10."
    }
    Say "Opening python.org's download page for you:" "Cyan"
    Say "  1. Click the yellow 'Download Python' button and open the file it downloads." "Yellow"
    Say "  2. Click 'Install Now' (no admin needed), wait for 'Setup was successful', close it." "Yellow"
    Say "  3. Double-click this .bat again." "Yellow"
    try { Start-Process $PY_PAGE } catch {}
    return $false
}

# ---------------------------------------------------------------- 3-5. ArcGIS Earth
function Find-Earth {
    $saved = Join-Path $Folder "ArcGIS_Earth_path.txt"
    if (Test-Path $saved) { $p = (Get-Content $saved -TotalCount 1); if ($p -and (Test-Path $p.Trim())) { return $p.Trim() } }
    $known = @(
        "$env:ProgramFiles\ArcGIS\ArcGIS Earth\bin\ArcGISEarth.exe",
        "$env:ProgramFiles\ArcGIS\Earth\ArcGISEarth.exe",
        "$env:ProgramFiles\ArcGIS Earth\ArcGISEarth.exe",
        "$env:LOCALAPPDATA\Programs\ArcGIS\Earth\ArcGISEarth.exe",
        "$env:LOCALAPPDATA\ArcGIS\Earth\ArcGISEarth.exe")
    foreach ($k in $known) { if (Test-Path $k) { return $k } }
    $keys = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
              "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
              "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")
    foreach ($e in (Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "ArcGIS Earth*" })) {
        $dirs = @([string]$e.InstallLocation)
        $icon = ([string]$e.DisplayIcon).Split(',')[0].Trim('"')
        if ($icon) { try { $dirs += (Split-Path $icon -Parent) } catch {} }
        foreach ($dir in $dirs) {
            if ($dir -and (Test-Path $dir)) {
                $hit = Get-ChildItem -Path $dir -Filter "ArcGISEarth.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($hit) { return $hit.FullName }
            }
        }
    }
    Say "Looking for ArcGIS Earth - first time only, this can take a few minutes on an older PC..."
    foreach ($root in @("$env:ProgramFiles\ArcGIS", "$env:ProgramFiles", "$env:LOCALAPPDATA\Programs", "${env:ProgramFiles(x86)}")) {
        if ($root -and (Test-Path $root)) {
            $hit = Get-ChildItem -Path $root -Filter "ArcGISEarth.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

function Test-Api {
    try {
        $r = [System.Net.WebRequest]::Create($API)
        $r.Proxy = $null; $r.Timeout = 1500
        $resp = $r.GetResponse(); $resp.Close(); return $true
    } catch { return $false }
}

# ================================================================ main
try { $Host.UI.RawUI.WindowTitle = "Ready to Fly $VERSION - $Tool" } catch {}
Log ("==== Ready to Fly " + $VERSION + " for " + $Tool + " | PowerShell " + $PSVersionTable.PSVersion + " | " + [Environment]::OSVersion.VersionString)
Say ("Ready to Fly " + $VERSION + ": getting this computer ready for " + $Tool + "...") "Cyan"

if ($EarthOnly) {
    $earth = Find-Earth
    if (-not $earth) {
        Bad "ArcGIS Earth isn't installed. It's free from Esri (Windows)."
        if (Ask "Open Esri's ArcGIS Earth download page now?") { Start-Process $ESRI_PAGE }
        exit 1
    }
    Set-Content -Path (Join-Path $Folder "ArcGIS_Earth_path.txt") -Value $earth -Encoding ASCII
    Ok ("ArcGIS Earth: " + $earth)
    exit 0
}

# only one Ready to Fly at a time (an extra double-click on a slow PC must not start a second Python install)
$script:OneAtATime = New-Object System.Threading.Mutex($false, "Local\ReadyToFly_single_instance")
$got = $false
try { $got = $script:OneAtATime.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $got = $true }
if (-not $got) {
    Bad "Ready to Fly is already running in another window - let that one finish (it may be installing Python)."
    Say "  You can close this window." "Yellow"
    exit 1
}

# 0. internet heads-up (non-blocking)
$net = Test-Internet
if ($net -eq "yes") { Ok "Internet: connected." }
elseif ($net -eq "portal") { Warn "This Wi-Fi wants you to sign in (hotel/airport style). Open a web browser and sign in, or ArcGIS Earth's online maps won't load." }
else { Warn "No internet right now: ArcGIS Earth's online basemaps and imagery won't load. Your own offline maps (TPKX) still work - load them from My Data. Places without an offline map will look blank or white." }

# 1. Python
$py = Find-Python
if (-not $py) {
    Bad ("Python " + $MIN_PY + " or newer is not installed. " + $Tool + " is a Python program and needs it.")
    if (Ask "Install Python now? It's free; Windows' own installer (winget) puts it in just for you (no admin). Takes several minutes.") {
        if (-not (Install-Python)) {
            Say ("  On a work computer that blocks installs, ask IT to install Python 3 from " + $PY_PAGE) "Yellow"
            exit 1
        }
        $py = Find-Python
    } else {
        Say ("  OK - nothing changed. Get Python from " + $PY_PAGE + " (tick 'Add python.exe to PATH'), then click again.") "Yellow"
        exit 1
    }
}
Ok ("Python " + $py.Version + ": " + $py.Exe)
Set-Content -Path (Join-Path $Folder "python_path.txt") -Value $py.Exe -Encoding ASCII

if ($NeedTk) {
    & $py.Exe -c "import tkinter" 2>$null
    if ($LASTEXITCODE -ne 0) { Warn "This Python has no Tkinter (windows/overlays). Reinstall Python from python.org with 'tcl/tk and IDLE' ticked." }
}

# 2. libraries
if ($Packages) {
    $pk = @($Packages.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $im = @(if ($Imports) { $Imports.Split(",") | ForEach-Object { $_.Trim() } } else { $pk })
    for ($i = 0; $i -lt $pk.Count; $i++) {
        $mod = if ($i -lt $im.Count) { $im[$i] } else { $pk[$i] }
        & $py.Exe -c ("import " + $mod) 2>$null
        if ($LASTEXITCODE -eq 0) { Ok ("Library " + $pk[$i] + ": installed."); continue }
        if ((Test-Internet) -ne "yes") { Bad ("The library " + $pk[$i] + " needs to be downloaded, and there is no internet right now. Connect, then click again."); exit 1 }
        Say ("Installing the library " + $pk[$i] + "...") "Cyan"
        & $py.Exe -m pip install --user --disable-pip-version-check $pk[$i] 2>&1 | ForEach-Object { Log ("pip: " + $_) }
        & $py.Exe -c ("import " + $mod) 2>$null
        if ($LASTEXITCODE -ne 0) { Bad ("Could not install " + $pk[$i] + ". Try:  py -m pip install " + $pk[$i] + "   (work computer: ask IT)"); exit 1 }
        Ok ("Library " + $pk[$i] + ": installed now.")
    }
}

# 3-5. ArcGIS Earth
if ($NeedEarth -or $NeedApi) {
    $earth = Find-Earth
    if (-not $earth) {
        Bad "ArcGIS Earth isn't installed. It's free from Esri (Windows)."
        if (Ask "Open Esri's ArcGIS Earth download page now?") { Start-Process $ESRI_PAGE }
        Say "  After installing ArcGIS Earth, click this .bat again." "Yellow"
        exit 1
    }
    Set-Content -Path (Join-Path $Folder "ArcGIS_Earth_path.txt") -Value $earth -Encoding ASCII
    Ok ("ArcGIS Earth: " + $earth)
    $name = [IO.Path]::GetFileNameWithoutExtension($earth)
    if (-not (Get-Process -Name $name -ErrorAction SilentlyContinue)) {
        Say "Starting ArcGIS Earth..." "Cyan"
        Start-Process -FilePath $earth
    } else { Ok "ArcGIS Earth is already running." }

    if ($NeedApi) {
        Say "Waiting for ArcGIS Earth to answer (it takes a little while to start)..."
        $deadline = (Get-Date).AddSeconds($ApiWaitS)
        while (-not (Test-Api)) {
            if ((Get-Date) -gt $deadline) {
                if (-not (Get-Process -Name $name -ErrorAction SilentlyContinue)) {
                    Bad "ArcGIS Earth closed or did not start. Open it by hand, then click this .bat again."
                    exit 1
                }
                Bad "ArcGIS Earth is open, but its Automation API is switched off - so tools can't talk to it."
                Say "  Turn it on:  ArcGIS Earth  >  Settings  >  Advanced application settings  >  tick 'Enable Automation API'." "Yellow"
                Say "  (If it still doesn't connect after ticking it, close ArcGIS Earth, open it again, and wait for the globe.)" "Yellow"
                if ($Unattended) { exit 1 }
                Read-Host "  Press Enter when it's ticked, and I'll check again" | Out-Null
                $deadline = (Get-Date).AddSeconds(60)
            }
            Start-Sleep -Seconds 2
        }
        Ok "ArcGIS Earth is answering on its Automation API."
    }
}

Say ("Ready to fly. Starting " + $Tool + "...") "Green"
exit 0

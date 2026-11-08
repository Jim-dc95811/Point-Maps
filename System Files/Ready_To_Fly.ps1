<#
  Ready to Fly v1.0.1 - the shared "get this PC ready" step for ArcGIS Earth Unlocked tools.
  Called by a tool's one-click .bat. Windows PowerShell 5.1 compatible (no PS7-only syntax).

  Checks, in order, and fixes what it can, in plain words:
    0. Internet (Windows' own NCSI verdict + probe) - only a heads-up, never a stop:
       no internet = ArcGIS Earth's online basemaps won't load; captive Wi-Fi = sign in first.
    1. Python 3.9+ (py launcher, python on PATH - ignoring the Microsoft Store stub - and the usual
       install folders). Missing: asks, then installs it for this user only (winget, else the official
       python.org installer after checking its Python Software Foundation signature).
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
    [int]$WingetMinutes = 20,        # give winget this long, then use the python.org installer             # how long to wait for ArcGIS Earth to answer at start
    [switch]$EarthOnly,              # only find ArcGIS Earth and save its path (taskbar shortcut maker)
    [switch]$Unattended              # no questions (answers 'no' to installs); for scheduled/test runs
)

$ErrorActionPreference = "Continue"
$VERSION = "1.0.1"
$MIN_PY = [version]"3.9"
$PY_FALLBACK = "3.14.0"   # used only if winget is missing; any published 3.x installer works
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
    $net = Test-Internet
    if ($net -ne "yes") {
        if ($net -eq "portal") { Bad "This Wi-Fi wants you to sign in first (open a web browser), then click again." }
        else { Bad "Python needs to be downloaded, and this computer has no internet right now. Connect, then click again." }
        return $false
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Say "Installing Python with Windows' own installer (winget). This can take several minutes - the window may look stuck; let it run..." "Cyan"
        Say "  (Windows Defender checks every new file, so the PC may run slow and look frozen for a few minutes. That's normal - don't close this window.)" "Yellow"
        $ids = @("Python.Python.3.14", "Python.Python.3.13")
        foreach ($id in $ids) {
            $out = Join-Path $env:TEMP "ready_to_fly_winget.txt"
            $wargs = "install -e --id $id --scope user --silent --accept-package-agreements --accept-source-agreements"
            $p = Start-Process -FilePath $winget.Source -ArgumentList $wargs -NoNewWindow -PassThru -RedirectStandardOutput $out
            $limit = (Get-Date).AddMinutes($WingetMinutes); $tick = 0
            while (-not $p.HasExited -and (Get-Date) -lt $limit) {
                Start-Sleep -Seconds 5; $tick++
                if ($tick % 12 -eq 0) { Say ("  ...still installing (" + [int]($tick * 5 / 60) + " min). Don't close this window.") }
            }
            $timedOut = -not $p.HasExited
            if ($timedOut) {
                Log ("winget still running after " + $WingetMinutes + " min - stopping it")
                try { $p.Kill() } catch {}
                Start-Sleep -Seconds 3
            } else { Log ("winget " + $id + " exit " + $p.ExitCode) }
            if (Test-Path $out) { Get-Content $out -ErrorAction SilentlyContinue | Where-Object { $_ -match '\w' } | Select-Object -Last 15 | ForEach-Object { Log ("winget: " + $_) }; Remove-Item $out -ErrorAction SilentlyContinue }
            if (Find-Python) { return $true }
            if ($timedOut) { break }
        }
        Warn "winget did not finish the job - trying the installer from python.org instead."
    }
    $url = "https://www.python.org/ftp/python/$PY_FALLBACK/python-$PY_FALLBACK-amd64.exe"
    $dst = Join-Path $env:TEMP "python-$PY_FALLBACK-amd64.exe"
    Say ("Downloading Python " + $PY_FALLBACK + " from python.org (about 30 MB)...") "Cyan"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $r = [System.Net.WebRequest]::Create($url)
        $r.Timeout = 30000; $r.ReadWriteTimeout = 60000
        $resp = $r.GetResponse(); $in = $resp.GetResponseStream(); $fs = [System.IO.File]::Create($dst)
        try { $in.CopyTo($fs) } finally { $fs.Close(); $in.Close(); $resp.Close() }
    } catch { Bad ("The download failed: " + $_.Exception.Message); return $false }
    $sig = Get-AuthenticodeSignature $dst
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        Bad "The downloaded file is not signed by the Python Software Foundation - not running it."
        Log ("signature: " + $sig.Status + " " + $sig.SignerCertificate.Subject)
        Remove-Item $dst -ErrorAction SilentlyContinue
        return $false
    }
    Say "Installing Python for this user (no admin needed)..." "Cyan"
    Say "  (This can take several minutes, and Windows Defender may slow the PC while it checks the new files. That's normal - don't close this window.)" "Yellow"
    $p = Start-Process -FilePath $dst -ArgumentList "/quiet InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_tcltk=1" -PassThru
    $tick = 0
    while (-not $p.HasExited) { Start-Sleep -Seconds 5; $tick++; if ($tick % 12 -eq 0) { Say ("  ...still installing (" + [int]($tick * 5 / 60) + " min). Don't close this window.") } }
    Log ("python installer exit " + $p.ExitCode)
    Remove-Item $dst -ErrorAction SilentlyContinue
    return [bool](Find-Python)
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
    if (Ask "Install Python now? It's free, from python.org, installs just for you (no admin). Takes several minutes.") {
        if (-not (Install-Python)) {
            Bad "Python could not be installed automatically."
            Say ("  If this is a work computer, ask IT to install Python 3 from " + $PY_PAGE) "Yellow"
            Say ("  At home: download it from " + $PY_PAGE + " and tick 'Add python.exe to PATH'.") "Yellow"
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

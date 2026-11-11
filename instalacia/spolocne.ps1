# Spolocne funkcie pre instaluj.ps1 a aktualizuj.ps1.
# Len ASCII a len veci, ktore vie aj Windows PowerShell 5.1.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Base   = Split-Path -Parent $PSScriptRoot
$Repo   = Join-Path $Base "hey-claude"
$VenvPy = Join-Path $Repo ".venv\Scripts\python.exe"
$Cfg    = Join-Path $Repo "config.yaml"
$Patch  = Join-Path $Base "jarvis-ulohy-do-prace.patch"

function Say($m, $c = "Gray") { Write-Host $m -ForegroundColor $c }
function Head($m) { Say ""; Say ("=" * 66) "DarkYellow"; Say "  $m" "Yellow"; Say ("=" * 66) "DarkYellow" }
function Ok($m) { Say "  OK     $m" "Green" }
function Warn($m) { Say "  POZOR  $m" "Yellow" }
function Koniec($m) { Say ""; Say "  STOP   $m" "Red"; Say ""; exit 1 }

function Citaj-Text($path) { return [IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8) }
function Zapis-Text($path, $text) { [IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false)) }

function Citaj-Sha {
    $f = Join-Path $Base "VERZIA-HEY-CLAUDE.txt"
    $s = Get-Content $f | Where-Object { $_ -match "^[0-9a-f]{40}$" } | Select-Object -First 1
    if (-not $s) { Koniec "V subore VERZIA-HEY-CLAUDE.txt chyba cislo verzie." }
    return $s
}

function Git-Kod([string[]]$a) {
    $null = & git @a 2>$null
    return $LASTEXITCODE
}

function Git-Text([string[]]$a) {
    $o = & git @a 2>$null | Out-String
    return $o.Trim()
}

function Najdi-Python312 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $v = & py -3.12 -c "import sys;print(sys.executable)" 2>$null | Out-String
        if ($LASTEXITCODE -eq 0 -and $v.Trim()) { return $v.Trim() }
    }
    foreach ($n in @("python3.12", "python")) {
        $c = Get-Command $n -ErrorAction SilentlyContinue
        if ($c) {
            $v = & $c.Source -c "import sys;print(sys.version_info[0]*100+sys.version_info[1])" 2>$null | Out-String
            if ($v.Trim() -eq "312") { return $c.Source }
        }
    }
    return $null
}

# Vrati @{ Cmd = cim sa claude spusta; Exe = cesta pre config alebo $null }
function Najdi-Claude {
    $c = Get-Command claude.exe -ErrorAction SilentlyContinue
    if ($c) { return @{ Cmd = $c.Source; Exe = $c.Source } }
    $p = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
    if (Test-Path $p) { return @{ Cmd = $p; Exe = $p } }
    $c = Get-Command claude -ErrorAction SilentlyContinue
    if ($c) { return @{ Cmd = $c.Source; Exe = $null } }
    return $null
}

function Claude-Stav($cmd) {
    $raw = & $cmd auth status 2>$null | Out-String
    try { return ($raw | ConvertFrom-Json) } catch { return $null }
}

# Prepne hey-claude na pripnutu verziu. Vrati $true, ak sa verzia zmenila.
function Nastav-Verziu($sha) {
    $head = Git-Text @("-C", $Repo, "rev-parse", "HEAD")
    if ($head -eq $sha) { return $false }
    if ((Git-Kod @("-C", $Repo, "cat-file", "-e", ($sha + "^{commit}"))) -ne 0) {
        $null = Git-Kod @("-C", $Repo, "fetch", "-q", "origin")
    }
    if ((Git-Kod @("-C", $Repo, "-c", "advice.detachedHead=false", "checkout", "-q", $sha)) -ne 0) {
        Koniec "Neviem prepnut hey-claude na verziu $sha."
    }
    return $true
}

function Zapoj-Patch {
    if ((Git-Kod @("-C", $Repo, "apply", "--unidiff-zero", "--reverse", "--check", $Patch)) -eq 0) { Ok "slovenske upravy uz v hey-claude su"; return }
    if ((Git-Kod @("-C", $Repo, "apply", "--unidiff-zero", "--check", $Patch)) -ne 0) {
        Koniec "Slovenske upravy sa nedaju vlozit do hey-claude. Spusti AKTUALIZUJ.bat, a ak to nepomoze, daj vediet autorovi."
    }
    if ((Git-Kod @("-C", $Repo, "apply", "--unidiff-zero", $Patch)) -ne 0) { Koniec "Vlozenie slovenskych uprav zlyhalo." }
    Ok "slovenske upravy vlozene do hey-claude"
}

function Pip([string[]]$a, [int]$pokusy = 2) {
    # pypi.org obcas neodpovie vcas, preto dlhsi cas a opakovanie
    foreach ($pokus in 1..$pokusy) {
        & $VenvPy -m pip --disable-pip-version-check --default-timeout=30 --retries 2 @a | Out-Host
        if ($LASTEXITCODE -eq 0) { return 0 }
        if ($pokus -lt $pokusy) { Say "  nepodarilo sa, skusam este raz..." "Yellow"; Start-Sleep -Seconds 5 }
    }
    return $LASTEXITCODE
}

# Ked server balickov vrati pre niektory balik pokazenu stranku, spadne instalacia celeho zoznamu.
# Vtedy ideme po jednom a pokazeny balik vezmeme priamo cez adresu suboru z pypi.org/pypi/<meno>/json.
# Vrati zoznam balikov, ktore sa nepodarilo nainstalovat ani tak.
function Balicky-Po-Jednom($subor) {
    $zle = @()
    foreach ($r in (Get-Content $subor)) {
        $spec = ($r -split "#")[0].Trim()
        if (-not $spec) { continue }
        $meno = ($spec -split "[^A-Za-z0-9._-]")[0]
        if ((Pip @("install", "-q", $spec) 1) -eq 0) { continue }
        # adresu suboru hlada Python z prostredia: PowerShell 5.1 taky velky JSON nezvlada
        $py = "import json,sys,urllib.request as u; d=json.load(u.urlopen('https://pypi.org/pypi/'+sys.argv[1]+'/json',timeout=30)); w=[x['url'] for x in d['urls'] if x['packagetype']=='bdist_wheel' and x['filename'].endswith('-none-any.whl')]; print(w[0] if w else '')"
        $url = (& $VenvPy -c $py $meno 2>$null | Out-String).Trim()
        if ($url -and ((Pip @("install", "-q", $url) 1) -eq 0)) { Ok "$meno nainstalovany nahradnou cestou"; continue }
        $zle += $meno
    }
    return $zle
}

function Skopiruj-Cublas {
    $sp  = Join-Path $Repo ".venv\Lib\site-packages"
    $src = Join-Path $sp "nvidia\cublas\bin"
    $dst = Join-Path $sp "ctranslate2"
    foreach ($n in @("cublas64_12.dll", "cublasLt64_12.dll")) {
        $s = Join-Path $src $n
        if ((Test-Path $s) -and (Test-Path $dst)) { Copy-Item $s (Join-Path $dst $n) -Force }
        else { Warn "nenasiel som $n, prepis reci moze ist na procesore"; return }
    }
    Ok "prepis reci na grafike pripraveny (cuBLAS)"
}

function Nainstaluj-Balicky($py312) {
    if (-not (Test-Path $VenvPy)) {
        if (-not $py312) { Koniec "Chyba Python 3.12. Nainstaluj: winget install Python.Python.3.12" }
        Say "  vytvaram prostredie Pythonu..."
        & $py312 -m venv (Join-Path $Repo ".venv") | Out-Host
        if (-not (Test-Path $VenvPy)) { Koniec "Prostredie Pythonu sa nevytvorilo." }
    }
    Say "  instalujem balicky hey-claude. Prvykrat to trva 5 az 15 minut."
    $req = Join-Path $Repo "requirements.txt"
    if ((Pip @("install", "-q", "-r", $req)) -ne 0) {
        Warn "Instalacia celeho zoznamu zlyhala. Skusam balicky po jednom, chyby vyssie mozes ignorovat."
        $zle = @(Balicky-Po-Jednom $req)
        if ($zle.Count -gt 0) {
            Koniec "Nepodarilo sa nainstalovat: $($zle -join ', '). Ak vypis konci na Read timed out, server balickov prave neodpoveda: spusti INSTALUJ.bat o par minut znova, pokracuje tam, kde skoncil. Inak posli autorovi cely vypis."
        }
    }
    Ok "balicky hey-claude"
    Say "  instalujem slovensky hlas..."
    if ((Pip @("install", "-q", "--upgrade", "piper-tts", (Join-Path $Base "voice\edge-piper-pkg"))) -ne 0) {
        Warn "Slovensky hlas sa nenainstaloval. Jarvis bude hovorit hlasom Windows."
    } else { Ok "hlas Lukas (Edge TTS)" }
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        Say "  grafika NVIDIA: pridavam kniznicu pre rychly prepis reci..."
        if ((Pip @("install", "-q", "nvidia-cublas-cu12")) -eq 0) { Skopiruj-Cublas }
        else { Warn "cuBLAS sa nenainstaloval, prepis reci pojde na procesore." }
    } else {
        Say "  grafika NVIDIA sa nenasla. Prepis reci pojde na procesore, bude pomalsi a menej presny."
    }
}

function Stiahni-Lili {
    $d = Join-Path $Repo "state\models\piper"
    New-Item -ItemType Directory -Force $d | Out-Null
    $u = "https://huggingface.co/rhasspy/piper-voices/resolve/main/sk/sk_SK/lili/medium/"
    foreach ($n in @("sk_SK-lili-medium.onnx.json", "sk_SK-lili-medium.onnx")) {
        $t = Join-Path $d $n
        if ((Test-Path $t) -and ((Get-Item $t).Length -gt 1000)) { continue }
        # stahuje Python z prostredia: stary PowerShell sa s huggingface.co nevie dohodnut na sifrovani
        & $VenvPy -c "import sys,urllib.request as u; u.urlretrieve(sys.argv[1], sys.argv[2])" ($u + $n) $t 2>$null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $t) -or ((Get-Item $t).Length -lt 1000)) {
            Remove-Item $t -Force -ErrorAction SilentlyContinue
            Warn "zalozny hlas sa nestiahol. Bez internetu bude Jarvis hovorit hlasom Windows."
            return
        }
    }
    Ok "zalozny hlas lili (funguje aj bez internetu)"
}

# autopilot: $true = bez potvrdzovania. profil: "max" alebo "pro". claudeExe: cesta alebo $null.
function Vyrob-Config($autopilot, $profil, $claudeExe) {
    $t = Citaj-Text (Join-Path $Base "vzory\config.yaml")
    if ($claudeExe) { $exe = "'" + $claudeExe.Replace("'", "''") + "'" } else { $exe = "null" }
    if ($autopilot) { $tm = "bypassPermissions"; $am = "bypassPermissions" } else { $tm = "auto"; $am = "default" }
    if ($profil -eq "max") {
        $b = "opus"; $l2 = "{model: opus, effort: xhigh}"; $l3 = "{model: opus, effort: xhigh, planner: fable}"
    } else {
        $b = "sonnet"; $l2 = "{model: sonnet, effort: high}"; $l3 = "{model: sonnet, effort: high}"
    }
    $t = $t.Replace("{{CLAUDE_EXE}}", $exe).Replace("{{TASKS_MODE}}", $tm).Replace("{{AGENT_MODE}}", $am)
    $t = $t.Replace("{{BRAIN}}", $b).Replace("{{L2}}", $l2).Replace("{{L3}}", $l3)
    Zapis-Text $Cfg $t
}

function Zo-Vzoru($vzor, $ciel, $meno) {
    if (Test-Path $ciel) { Ok "$ciel uz existuje, nechavam ho tak"; return }
    $t = Citaj-Text (Join-Path $Base (Join-Path "vzory" $vzor))
    $t = $t.Replace("{{MENO}}", $meno).Replace("{{HOME}}", $env:USERPROFILE)
    Zapis-Text $ciel $t
    Ok "vytvorene: $ciel"
}

function Skopiruj-Skill {
    $src = Join-Path $Base "skills\slovenska-legislativa"
    $dst = Join-Path $env:USERPROFILE ".claude\skills\slovenska-legislativa"
    New-Item -ItemType Directory -Force (Join-Path $dst "scripts") | Out-Null
    Copy-Item (Join-Path $src "SKILL.md") $dst -Force
    Copy-Item (Join-Path $src "scripts\*") (Join-Path $dst "scripts") -Force
    if (-not (Test-Path (Join-Path $dst "SLEDOVANE.md"))) { Copy-Item (Join-Path $src "SLEDOVANE.md") $dst }
    Ok "skill na slovenske zakony a vladu"
}

# Odkaz na ploche s ikonou jadra. Spusta SPUSTIT-JARVIS.bat.
function Vyrob-Odkaz {
    try {
        $plocha = [Environment]::GetFolderPath("Desktop")
        $sh = New-Object -ComObject WScript.Shell
        $l = $sh.CreateShortcut((Join-Path $plocha "JARVIS.lnk"))
        $l.TargetPath = Join-Path $Base "SPUSTIT-JARVIS.bat"
        $l.WorkingDirectory = $Base
        $l.IconLocation = Join-Path $Base "dashboard\jarvis.ico"
        $l.Description = "Hlasovy asistent JARVIS"
        $l.Save()
        Ok "odkaz JARVIS na ploche"
    } catch { Warn "odkaz na ploche sa nevytvoril, Jarvisa spustis cez SPUSTIT-JARVIS.bat" }
}

function Ukaz-Tutorial {
    Head "Ako sa s Jarvisom rozprava"
    Say ""
    Say "  1. Spusti SPUSTIT-JARVIS.bat. Prvy start stahuje modely reci (asi 1,7 GB)," "White"
    Say "     dalsie starty trvaju par sekund. Hore na obrazovke sa objavi ostrovcek." "White"
    Say "  2. Povedz  Hey Jarvis  a pockaj, kym ostrovcek ukaze, ze pocuva." "White"
    Say "  3. Hovor po slovensky, normalne ako s kolegom." "White"
    Say "       Otazka:  Kolko je patnast percent z osemdesiat?" "Gray"
    Say "       Praca:   Najdi mi na ploche cennik a sprav z neho ponuku na sto kusov." "Gray"
    Say "     Pri praci sa najprv dopyta na detaily. Zacne, ked povies  chod  alebo  sprav to." "White"
    Say "  4. Ako to ide?  povie stav ulohy.  Prestan to robit  ju zastavi." "White"
    Say "  5. Po odpovedi par sekund pocuva dalej, vtedy netreba hovorit Hey Jarvis." "White"
    Say ""
    Say "  Cely navod je v README.md. Novinky a opravy stiahne AKTUALIZUJ.bat." "Gray"
    Say ""
}

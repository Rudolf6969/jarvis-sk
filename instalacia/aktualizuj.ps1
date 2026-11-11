# JARVIS SK - aktualizacia. Spusta sa cez AKTUALIZUJ.bat.
# Prvy beh stiahne novinky a spusti sam seba znova (-Od), aby zvysok bezal uz podla noveho kodu.
#   -Test   skusobny beh: nic nestahuje, na nic sa nepyta, nemeni balicky ani nastavenia
param([string]$Od = "", [switch]$Test)
. (Join-Path $PSScriptRoot "spolocne.ps1")

if (-not $Od) {
    Head "JARVIS SK - aktualizacia"
    if (-not (Test-Path (Join-Path $Base ".git"))) { Koniec "Tento priecinok nie je stiahnuty cez git clone, aktualizacia nema odkial brat." }
    if (-not (Test-Path (Join-Path $Repo ".git"))) { Koniec "Jarvis este nie je nainstalovany. Spusti INSTALUJ.bat." }
    if (-not $Test) {
        $bezi = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | Where-Object { $_.CommandLine -match "heyclaude" }
        if ($bezi) { Koniec "Jarvis bezi. Zavri jeho okno a spusti AKTUALIZUJ.bat znova." }
    }
    $stare = Git-Text @("-C", $Base, "rev-parse", "HEAD")
    if (-not $Test) {
        Say "  stahujem novinky..."
        if ((Git-Kod @("-C", $Base, "pull", "-q", "--ff-only")) -ne 0) {
            Koniec "Stiahnutie noviniek zlyhalo. Ak si menil subory z repozitara, pozri: git -C $Base status"
        }
    }
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath, "-Od", $stare)
    if ($Test) { $a += "-Test" }
    & powershell @a
    exit $LASTEXITCODE
}

$nove = Git-Text @("-C", $Base, "rev-parse", "HEAD")
$zmenene = @()
if ($Od -ne $nove) {
    $zmenene = @((Git-Text @("-C", $Base, "diff", "--name-only", $Od, $nove)) -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    Ok "stiahnute zmeny: $($zmenene.Count) suborov"
} else { Ok "ziadne novinky, kontrolujem len stav" }

Head "1/3  hey-claude a slovenske upravy"
$Sha = Citaj-Sha
$head = Git-Text @("-C", $Repo, "rev-parse", "HEAD")
$sedi = ($head -eq $Sha) -and ((Git-Kod @("-C", $Repo, "apply", "--unidiff-zero", "--reverse", "--check", $Patch)) -eq 0)
$zmenaVerzie = $false
if ($sedi) { Ok "hey-claude je aktualny" }
else {
    $spina = Git-Text @("-C", $Repo, "status", "--porcelain", "--untracked-files=no")
    if ($spina) {
        $zd = Join-Path $Base "zalohy"
        New-Item -ItemType Directory -Force $zd | Out-Null
        $zf = Join-Path $zd ("hey-claude-" + (Get-Date -Format "yyyy-MM-dd-HHmm") + ".patch")
        $null = Git-Kod @("-C", $Repo, "diff", "--output=$zf")
        Ok "doterajsie upravy v hey-claude odlozene: $zf"
        if ((Git-Kod @("-C", $Repo, "checkout", "-q", "--", ".")) -ne 0) { Koniec "Neviem vratit hey-claude do povodneho stavu." }
    }
    $zmenaVerzie = Nastav-Verziu $Sha
    if ($zmenaVerzie) { Ok "hey-claude prepnuty na verziu $($Sha.Substring(0, 7))" }
    Zapoj-Patch
}

Head "2/3  Balicky a nastavenia"
$hlas = @($zmenene | Where-Object { $_ -like "voice/*" }).Count -gt 0
if ($Test) { Warn "balicky preskocene (-Test)" }
elseif ($zmenaVerzie -or $hlas) {
    Nainstaluj-Balicky (Najdi-Python312)
    Stiahni-Lili
} else { Ok "balicky netreba menit" }

if ($zmenene -contains "vzory/config.yaml") {
    Say ""
    Say "  Zmenil sa vzor nastaveni. Nove nastavenia nahradia tvoj config.yaml," "White"
    Say "  stary sa odlozi do priecinka zalohy. Vlastne zmeny (skratka, mesto) si potom dopln znova." "White"
    $ano = -not $Test
    if (-not $Test) {
        $x = Read-Host "  Nahradit nastavenia novym vzorom? (A/n)"
        if ($x.Trim() -match "^[nN]") { $ano = $false }
    }
    if ($ano) {
        $stary = ""
        if (Test-Path $Cfg) {
            $stary = Citaj-Text $Cfg
            $zd = Join-Path $Base "zalohy"
            New-Item -ItemType Directory -Force $zd | Out-Null
            Copy-Item $Cfg (Join-Path $zd ("config-" + (Get-Date -Format "yyyy-MM-dd-HHmm") + ".yaml")) -Force
        }
        $autopilot = (-not $stary) -or ($stary -match "(?m)^\s+permission_mode:\s*bypassPermissions")
        if ($stary -match "(?m)^\s+cli_model:\s*sonnet") { $profil = "pro" } else { $profil = "max" }
        $cl = Najdi-Claude
        $exe = $null
        if ($cl) { $exe = $cl.Exe }
        Vyrob-Config $autopilot $profil $exe
        Ok "config.yaml nahradeny novym vzorom"
    } else { Warn "nastavenia ostali stare. Co sa zmenilo, pise ZMENY.md." }
} else { Ok "nastavenia netreba menit" }
if (-not $Test) { Skopiruj-Skill }

Head "3/3  Co je nove"
$z = Join-Path $Base "ZMENY.md"
if (Test-Path $z) {
    $n = 0
    foreach ($r in ((Citaj-Text $z) -split "`n")) {
        if ($r -match "^## ") { $n++; if ($n -gt 1) { break } }
        if ($n -eq 1) { Say ("  " + $r.TrimEnd()) "White" }
    }
}
Say ""
Say "  Hotovo. Spusti SPUSTIT-JARVIS.bat." "Green"
Say ""

# JARVIS SK - instalacia. Spusta sa cez INSTALUJ.bat.
#   -Test            skusobny beh: bez otazok, nic mimo tohto priecinka, priecinok nemusi byt C:\JARVIS
#   -BezBalickov     preskoci prostredie Pythonu a stahovanie hlasu
#   -Zdroj <adresa>  odkial sa stiahne hey-claude
param([switch]$Test, [switch]$BezBalickov, [string]$Zdroj = "https://github.com/kamol1dn/hey-claude")
. (Join-Path $PSScriptRoot "spolocne.ps1")

Head "JARVIS SK - instalacia"

if (-not $Test -and ($Base.TrimEnd("\") -ine "C:\JARVIS")) {
    Koniec "Priecinok sa musi volat presne C:\JARVIS, teraz je to $Base. Presun ho a spusti INSTALUJ.bat znova."
}

Head "1/6  Kontrola pocitaca"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Koniec "Chyba Git. Nainstaluj: winget install Git.Git   a otvor nove okno." }
Ok "Git"
$py = Najdi-Python312
if (-not $py -and -not $BezBalickov) { Koniec "Chyba Python 3.12. Nainstaluj: winget install Python.Python.3.12   a otvor nove okno." }
if ($py) { Ok "Python 3.12" }
$cl = Najdi-Claude
if (-not $cl) {
    Say ""
    Say "  Chyba Claude Code. Jarvis bezi na TVOJOM predplatnom Claude." "Yellow"
    Say "  1. V PowerShelli spusti:  irm https://claude.ai/install.ps1 | iex" "White"
    Say "  2. Otvor nove okno a prihlas sa:  claude auth login" "White"
    Say "  3. Spusti INSTALUJ.bat znova." "White"
    Koniec "Bez Claude Code sa neda pokracovat."
}
$stav = Claude-Stav $cl.Cmd
if (-not $stav -or -not $stav.loggedIn) {
    Koniec "Claude Code nie je prihlaseny. Spusti:  claude auth login   a potom INSTALUJ.bat znova."
}
$plan = [string]$stav.subscriptionType
Ok "Claude Code, prihlaseny, predplatne: $plan"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { Ok "grafika NVIDIA" }
else { Warn "bez grafiky NVIDIA pojde prepis reci na procesore (pomalsie, menej presne)" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Warn "chyba Node.js: nepojde pocasie a citanie parlamentu. Da sa doplnit neskor: winget install OpenJS.NodeJS.LTS"
}

Head "2/6  Par otazok"
$meno = $env:USERNAME
$autopilot = $true
if ($plan -match "max|team|enterprise") { $profil = "max" } else { $profil = "pro" }
if (-not $Test) {
    $x = Read-Host "  Ako ta ma Jarvis volat? (Enter = $meno)"
    if ($x.Trim()) { $meno = $x.Trim() }
    Say ""
    Say "  Autopilot: Jarvis robi ulohy bez jedineho potvrdenia. Moze citat, menit aj mazat" "White"
    Say "  subory a spustat prikazy na tomto pocitaci. Takto to ma nastavene autor." "White"
    Say "  Bez autopilota sa pri citlivych krokoch pyta a cast veci odmietne." "White"
    $x = Read-Host "  Zapnut autopilot? (A/n)"
    if ($x.Trim() -match "^[nN]") { $autopilot = $false }
    Say ""
    Say "  Model: profil max = Opus na vsetko (pre predplatne Max)." "White"
    Say "         profil pro = Sonnet (setri limit pri predplatnom Pro)." "White"
    $x = Read-Host "  Ktory profil? (Enter = $profil)"
    if ($x.Trim() -match "^(max|pro)$") { $profil = $x.Trim().ToLower() }
}
Ok "meno: $meno, autopilot: $autopilot, profil: $profil"

Head "3/6  hey-claude a slovenske upravy"
$Sha = Citaj-Sha
if (-not (Test-Path (Join-Path $Repo ".git"))) {
    if (Test-Path $Repo) { Koniec "Priecinok hey-claude existuje, ale nie je to stiahnuty repozitar. Premenuj ho a spusti INSTALUJ.bat znova." }
    Say "  stahujem hey-claude..."
    $null = Git-Kod @("clone", "-q", $Zdroj, $Repo)
    if (-not (Test-Path (Join-Path $Repo ".git"))) { Koniec "Stiahnutie hey-claude zlyhalo. Skontroluj internet." }
    $null = Nastav-Verziu $Sha
    Ok "hey-claude stiahnuty, verzia $($Sha.Substring(0, 7))"
} else {
    $head = Git-Text @("-C", $Repo, "rev-parse", "HEAD")
    if ($head -ne $Sha) { Koniec "hey-claude je v inej verzii, nez caka tento navod. Spusti AKTUALIZUJ.bat." }
    Ok "hey-claude uz je stiahnuty"
}
Zapoj-Patch

Head "4/6  Balicky a hlas"
if ($BezBalickov) { Warn "preskocene (-BezBalickov)" }
else {
    Nainstaluj-Balicky $py
    Stiahni-Lili
}

Head "5/6  Nastavenia"
if (Test-Path $Cfg) { Ok "config.yaml uz existuje, nechavam ho tak" }
else {
    Vyrob-Config $autopilot $profil $cl.Exe
    Ok "config.yaml vytvoreny (budiace slovo hey jarvis, slovencina, hlas Lukas)"
}
Zo-Vzoru "OSOBNOST.md" (Join-Path $Base "OSOBNOST.md") $meno
Zo-Vzoru "PROJEKTY.md" (Join-Path $Base "PROJEKTY.md") $meno

Head "6/6  Pracovny priecinok a skill"
if ($Test) { Warn "preskocene (-Test): C:\PRACA a skill v profile" }
else {
    New-Item -ItemType Directory -Force "C:\PRACA" | Out-Null
    if (-not (Test-Path "C:\PRACA")) { Koniec "Neviem vytvorit C:\PRACA. Vytvor ho rucne a spusti INSTALUJ.bat znova." }
    Zo-Vzoru "PRACA-CLAUDE.md" "C:\PRACA\CLAUDE.md" $meno
    Skopiruj-Skill
    Vyrob-Odkaz
}

Head "Hotovo"
Ukaz-Tutorial

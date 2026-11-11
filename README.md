# JARVIS SK

Hlasový asistent pre Windows, ktorý rozumie a hovorí po slovensky. Povieš „Hey Jarvis", povieš, čo chceš, a on odpovie alebo tú prácu na počítači spraví: nájde súbor, pripraví ponuku z cenníka, preskúma niečo na webe, zistí stav zákona.

Beží na **tvojom vlastnom predplatnom Claude**. Nič sa nezdieľa s autorom ani s nikým ďalším, každý si pripája svoj účet.

Základ je projekt [hey-claude](https://github.com/kamol1dn/hey-claude) od kamol1dn. Tento repozitár k nemu pridáva slovenčinu, slovenský hlas, prácu na pozadí bez klikania, dashboard a inštalátor, ktorý to celé poskladá.

## Čo potrebuješ

| | |
|---|---|
| Windows 10 alebo 11 | s mikrofónom a reproduktormi |
| Predplatné Claude | Pro alebo Max, prihlásené v Claude Code |
| Git a Python 3.12 | inštalátor ich skontroluje a povie, čo chýba |
| Grafika NVIDIA | odporúčaná. Bez nej ide prepis reči na procesore, je pomalší a menej presný |
| Miesto na disku | asi 8 GB |
| Internet | hlas Lukáš a Claude idú cez internet |

## Inštalácia

Otvor PowerShell a spusti postupne:

```powershell
winget install Git.Git
winget install Python.Python.3.12
irm https://claude.ai/install.ps1 | iex
```

Zavri okno, otvor nové a prihlás sa do Claude svojím účtom:

```powershell
claude auth login
```

Stiahni Jarvisa. Priečinok sa musí volať presne `C:\JARVIS`:

```powershell
git clone https://github.com/Rudolf6969/jarvis-sk C:\JARVIS
```

V priečinku `C:\JARVIS` spusti dvojklikom **INSTALUJ.bat**. Opýta sa na tri veci (ako ťa má volať, autopilot, model) a potom 5 až 15 minút sťahuje a inštaluje.

Nakoniec spusti **SPUSTIT-JARVIS.bat**. Prvý štart sťahuje modely reči (asi 1,7 GB), ďalšie trvajú pár sekúnd.

## Prvý rozhovor

1. Po štarte počkaj na riadok `[ready]` v čiernom okne. Hore na obrazovke sa objaví malý ostrovček.
2. Povedz **„Hey Jarvis"**. Ostrovček ukáže, že počúva.
3. Hovor po slovensky, normálne ako s kolegom. Keď dohovoríš, odpovie nahlas.
4. Po odpovedi ešte pár sekúnd počúva. Vtedy môžeš pokračovať bez „Hey Jarvis".

Skús najprv niečo jednoduché, napríklad „Hey Jarvis… koľko je pätnásť percent z osemdesiat?"

### Čo mu môžeš povedať

| Povieš | Čo sa stane |
|---|---|
| „Koľko je hodín v Tokiu?" | odpovie hneď |
| „Nájdi mi na ploche cenník a daj mi ho do stiahnutých." | spraví to na pozadí a ohlási, keď je hotovo |
| „Potrebujem ponuku pre klienta z nášho cenníka." | najprv sa dopýta na detaily, začne až keď povieš „choď" alebo „sprav to" |
| „Ako to ide?" | povie, na čom práve robí |
| „Prestaň to robiť." / „Zastav to." / „Vykašli sa na to." | zastaví rozbehnutú úlohu |
| „Čo bolo naposledy na rokovaní vlády?" | pozrie oficiálne stránky a odpovie s dátumom |

Bez hlasu: klikni na ostrovček alebo stlač `Ctrl+Shift+Space` a hovor, prípadne píš.

Výsledky úloh ukladá do priečinka `C:\PRACA`, každú do vlastného podpriečinka s dátumom.

### Ako z neho dostať dobrú prácu

Z jednej vety dobrý výsledok nebýva. Pri práci sa Jarvis pýta po jednej otázke, kým nemá všetko. Povedz mu, kde sú podklady, pre koho to je a kam to má uložiť. Keď chceš, aby začal hneď, povedz „hneď" alebo „bez otázok".

## Dashboard

So štartom Jarvisa sa otvorí okno s prehľadom: čo práve robí, rozhovor, bežiace úlohy s tlačidlom ZASTAVIŤ, čo dobehlo a denník. Beží len na tvojom počítači (`127.0.0.1:8642`). Podrobnosti sú v `dashboard\CITAJ.txt`.

## Autopilot a bezpečnosť

Toto si prečítaj skôr, než povieš áno.

**Autopilot** znamená, že Jarvis robí úlohy bez jediného potvrdenia. Môže čítať, meniť aj mazať súbory a spúšťať príkazy na celom počítači, pod tvojím účtom. Tak to používa autor. Je to pohodlné a je to aj riziko: zle pochopená veta alebo podvrhnutý text na webovej stránke môže spôsobiť škodu, ktorú nikto nezastaví.

Ak si nie si istý, pri inštalácii autopilot vypni. Jarvis sa potom pri citlivých krokoch pýta alebo ich odmietne. Prepnúť sa dá aj neskôr v `C:\JARVIS\hey-claude\config.yaml`:

| | `tasks: permission_mode` | `agent: permission_mode` |
|---|---|---|
| autopilot | `bypassPermissions` | `bypassPermissions` |
| s brzdou | `auto` | `default` |

Ďalšie veci, ktoré je fér vedieť:

- Reč sa prepisuje na tvojom počítači. Prepísaný text ide do Claude (Anthropic) a text odpovede do služby Microsoft Edge TTS, ktorá z neho robí hlas.
- Každá veta míňa tvoj limit Claude. Profil `max` používa Opus aj na rozhovor, takže míňa citeľne. Pri predplatnom Pro zvoľ profil `pro`.
- Jarvis nič neposiela a nič nekupuje, kým mu to výslovne nepovieš. Je to pravidlo v jeho pokynoch, nie technická zábrana.

## Prispôsob si ho

| Súbor | Na čo je |
|---|---|
| `C:\JARVIS\OSOBNOST.md` | ako sa Jarvis správa a rozpráva |
| `C:\JARVIS\PROJEKTY.md` | mapa tvojich projektov a priečinkov. Čím je presnejšia, tým lepšie nájde, čo myslíš |
| `C:\PRACA\CLAUDE.md` | pravidlá pre úlohy: kam ukladať, čo nikdy nerobiť, postupy |
| `C:\JARVIS\hey-claude\config.yaml` | budiace slovo, klávesová skratka, modely, hlas, mesto pre počasie |

Tieto súbory vytvorí inštalátor zo vzorov v priečinku `vzory` a aktualizácia ich neprepisuje. Po zmene Jarvisa reštartuj.

## Aktualizácie

Repozitár sa priebežne opravuje. Keď autor ohlási novú verziu:

1. Zavri Jarvisa.
2. Spusti **AKTUALIZUJ.bat**.

Stiahne novinky, znova vloží úpravy do hey-claude a vypíše, čo je nové. Zoznam zmien je v [ZMENY.md](ZMENY.md). Ak niektorá zmena potrebuje ručný krok, je tam napísaný.

## Keď niečo nejde

| Problém | Čo skúsiť |
|---|---|
| Nereaguje na „Hey Jarvis" | Skontroluj, či je vo Windows nastavený správny mikrofón. Klik na ostrovček funguje aj bez budiaceho slova, tak zistíš, či ide o mikrofón alebo o budiace slovo. |
| Rozumie zle alebo po anglicky | Bez grafiky NVIDIA, alebo keď je grafika vyťažená hrou či videom, beží slabší model prepisu. V čiernom okne to píše riadok `stt:`. |
| Hovorí iným, ženským hlasom | Vypadol internet, hovorí záložný hlas. |
| Hovorí „run claude auth login" | Vypršalo prihlásenie. Spusti `claude auth login`. |
| Úloha skončila bez výsledku | Pozri dashboard, panel Dobehlo. Najčastejšie chýbal detail v zadaní. |
| Po aktualizácii nenabehne | Spusti AKTUALIZUJ.bat ešte raz. Ak to nepomôže, pošli autorovi výpis z čierneho okna. |

Inštalátor je zatiaľ vyskúšaný na jednom počítači: Windows 11, grafika NVIDIA, predplatné Max. Profil `pro` a počítač bez grafiky NVIDIA vyskúšané nie sú. Čo sa pokazí, daj vedieť, opravíme to tu.

## Čo je čie

- [hey-claude](https://github.com/kamol1dn/hey-claude) je dielo kamol1dn a všetky práva k nemu patria jemu. Autor k nemu neuviedol licenciu, preto ho tento repozitár neobsahuje a ďalej nešíri: inštalátor si ho sťahuje priamo od autora v pripnutej verzii. Tu je len súbor s našimi úpravami (`jarvis-ulohy-do-prace.patch`), v ktorom je z pôvodného kódu iba pár desiatok riadkov, ktoré nahrádzame. Tento doplnok je nekomerčný a s autorom nie je spojený. Ak si autor a niečo ti tu prekáža, napíš a upravíme to alebo stiahneme.
- Budiace slovo „hey jarvis" je model z projektu openWakeWord s licenciou CC BY-NC-SA 4.0. Je len na nekomerčné použitie.
- Hlas Lukáš je služba Microsoft Edge TTS, používa sa cez knižnicu edge-tts. Záložný hlas lili je z projektu Piper.
- Claude a Claude Code sú produkty spoločnosti Anthropic. Tento projekt s ňou nie je spojený.

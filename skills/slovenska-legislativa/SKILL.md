---
name: slovenska-legislativa
description: Zisťovanie stavu slovenských zákonov, noviel, rokovaní vlády, uznesení a pripomienkových konaní z oficiálnych zdrojov (rokovania.gov.sk, Slov-Lex, NR SR). Použi vždy, keď sa zadanie pýta na zákon, novelu, vládu, legislatívu, pripomienkové konanie, Zbierku zákonov alebo reguláciu na Slovensku, napríklad "prešla novela o omamných látkach", "čo bolo dnes na vláde", "je kratom už zakázaný".
---

# Slovenská legislatíva

Cieľ: povedať, v akom stave je konkrétny predpis alebo návrh, s dátumom a zdrojom. Nikdy nehádaj.
Čo sa nedá overiť z oficiálneho zdroja, povedz ako neoverené.

## Nástroj

`python "%USERPROFILE%\.claude\skills\slovenska-legislativa\scripts\render.py" <url>`

- Stránku najprv stiahne priamo, pri prázdnej kostre alebo ochrane proti robotom skúsi skrytý prehliadač.
- `--find <slovo>` vypíše len riadky so slovom a okolie. `--links` pridá zoznam odkazov. `--render` vynúti prehliadač.
- Prvý riadok na chybovom výstupe hovorí, ako sa stránka načítala. `POZOR: stranka nevydala obsah` znamená,
  že zdroj sa prečítať nepodarilo a treba ísť inou cestou.

## Kde čo je

| Otázka | Zdroj | Číta sa |
|---|---|---|
| Kedy rokovala vláda, čo mala na programe | `https://rokovania.gov.sk/RVL/Negotiation` (zoznam), `https://rokovania.gov.sk/RVL/Negotiation/<id>` (program s bodmi a odkazmi na materiály) | priamo, overené |
| Čo vláda schválila | `https://rokovania.gov.sk/RVL/Resolution` (uznesenia) | priamo, overené |
| Materiály predložené na vládu | `https://rokovania.gov.sk/RVL/Material` | priamo, overené |
| Poradné orgány (Legislatívna rada, tripartita) | `https://rokovania.gov.sk/RPO/Negotiation`, `https://rokovania.gov.sk/RPO/Material` | priamo |
| Platné znenie zákona a všetky jeho novely | `https://static.slov-lex.sk/static/SK/ZZ/<rok>/<číslo>/` (napr. `.../ZZ/1998/139/`). Stránka má zoznam časových verzií: každý riadok je obdobie účinnosti a pod ním číslo novely, ktorá ho spôsobila. Posledné riadky ukazujú aj BUDÚCE znenia (už vyhlásené, ešte neúčinné). | priamo, overené |
| Čo vyšlo v Zbierke zákonov v danom roku | `https://static.slov-lex.sk/static/SK/ZZ/<rok>/` (zoznam všetkých predpisov roka, hľadaj cez `--find`) | priamo, overené |
| Pripomienkové konanie (MPK), legislatívny proces, predbežné informácie | `https://www.slov-lex.sk/elegislativa/legislativne-procesy?hladanyVyraz=<text>` (zoznam procesov: číslo LP/rok/číslo, typ, názov, štádium aj s termínom), `https://www.slov-lex.sk/elegislativa/predbezne-informacie` | LEN cez `prehliadac.mjs`, overené |
| Stav v parlamente (tlač, čítania, výbory) | `https://www.nrsr.sk/web/Default.aspx?sid=zakony/sslp&Text=<text>&CisObdobia=9&FullText=False` (návrhy zákonov: názov, číslo tlače, stav, dátumy). `CisObdobia` je volebné obdobie. | LEN cez `prehliadac.mjs`, overené |

## Druhý nástroj: prehliadac.mjs

`node "%USERPROFILE%\.claude\skills\slovenska-legislativa\scripts\prehliadac.mjs" <url> [--find slovo] [--links] [--hladaj text] [--klik text] [--wait ms]`

- Otvorí bežné okno Chrome mimo obrazovky s čistým dočasným profilom, načíta stránku vrátane vnorených
  rámcov (Slov-Lex má obsah v rámci) a prejde aj ochranou proti robotom na nrsr.sk. Potom okno zavrie.
- Hľadaný text daj radšej priamo do adresy (vzory vyššie, text zakóduj pre URL). `--hladaj` je záloha.
- `--klik "LP/2026/603"` alebo názov otvorí detail; `--links` vypíše odkazy na detaily.
- Funguje LEN na stránkach štátu a legislatívy (slov-lex.sk, nrsr.sk, *.gov.sk, prezident.sk, ustavnysud.sk,
  eur-lex.europa.eu). Inú adresu odmietne. Nepoužívaj ho na nič iné a zoznam nerozširuj.
- Trvá 15 až 30 sekúnd na stránku, preto ním čítaj len to, čo `render.py` neprečíta.

Ak aj tento nástroj vráti `POZOR: stranka nevydala obsah`, použi WebSearch, ber len oficiálne stránky alebo
veľké spravodajstvo, pri každom tvrdení uveď zdroj a dátum a povedz, že fázu si neoveril priamo v registri.

## Postup

1. Urči, o čo ide: číslo zákona (napr. 139/1998 Z. z.), názov, alebo téma. Pozri `SLEDOVANE.md` v tomto
   priečinku, či to nie je sledovaná téma s už známymi číslami.
2. Najprv tvrdé fakty zo Zbierky: otvor stránku zákona na `static.slov-lex.sk` s `--links` a pozri posledné
   časové verzie. Tak zistíš, ktorá novela je posledná vyhlásená a odkedy platí. Čo tam nie je, ešte
   nebolo vyhlásené. V ročnom zozname over cez `--find`, či nevyšiel nový predpis k téme.
3. Vláda: otvor zoznam rokovaní, nájdi rokovanie podľa dátumu, otvor jeho program a hľadaj návrh podľa
   čísla zákona aj podľa kľúčových slov (`--find`). Ak dnešné rokovanie v zozname ešte nie je, povedz to
   a uveď dátum posledného zverejneného. Schválenie potvrď v uzneseniach.
4. Predchádzajúce a ďalšie fázy: pripomienkové konanie, parlament, podpis prezidenta, Zbierka zákonov.
   Ku každej fáze napíš, či je overená a odkiaľ.
5. Ak sa niečo zmenilo oproti `SLEDOVANE.md`, dopíš tam riadok s dátumom.

## Fázy slovenského legislatívneho procesu

predbežná informácia → medzirezortné pripomienkové konanie (MPK) → Legislatívna rada vlády →
rokovanie vlády (uznesenie) → NR SR prvé, druhé a tretie čítanie → podpis prezidenta →
vyhlásenie v Zbierke zákonov → účinnosť (často neskorší dátum než vyhlásenie).

Schválené vládou neznamená platné. Vždy rozlíš schválené vládou, schválené parlamentom, vyhlásené a účinné.

## Odpoveď

- Prvá veta: aktuálny stav a dátum, ku ktorému platí.
- Potom: čo je overené z oficiálneho zdroja (s odkazom) a čo nie.
- Výstup ulož ako `vysledok.md` do podpriečinka úlohy s odkazmi na zdroje.
- Do hovoreného zhrnutia daj stav, dátum a jednu vetu o tom, čo sa nepodarilo overiť.

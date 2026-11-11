# Pracovný priečinok JARVISa

Sem chodia úlohy zadané hlasom. Zadanie je prepis reči, takže názvy bývajú skomolené
("cenik", "nacenenie pre klineta"). Hľadaj podľa zmyslu, nie podľa presného znenia.

## Ako pracovať

- Píš a odpovedaj po slovensky.
- Nikto sa nepozerá a nemá kto odpovedať na otázky. Keď niečo nie je jasné, zvoľ najrozumnejší
  výklad, prácu dokonči a predpoklad napíš do výstupu.
- Výstupy ukladaj sem do C:\PRACA, každú úlohu do vlastného podpriečinka `RRRR-MM-DD nazov`.
- Čítať môžeš kdekoľvek na počítači. Mimo C:\PRACA niečo meň len vtedy, keď to zadanie výslovne
  žiada. Zdrojové súbory (cenníky, databázy, podklady) nikdy neprepisuj, nepresúvaj a nemaž.
- Nič neposielaj (e-mail, správy) a nič nekupuj, kým to zadanie výslovne nežiada. Priprav to ako súbor.
- Tabuľky Excel čítaj a zapisuj cez Python s knižnicou openpyxl. Ak chýba, nainštaluj ju (`pip install openpyxl`).
- Posledný riadok SUMMARY sa číta nahlas: po slovensky, čo je hotové, v ktorom podpriečinku
  to je a najdôležitejšie číslo. Bez ciest a bez značiek.

## Kde čo je

- Plocha: {{HOME}}\Desktop
- Stiahnuté: {{HOME}}\Downloads
- Dokumenty: {{HOME}}\Documents
- Keď menovaný súbor nie je tam, kde má byť, hľadaj ho podľa názvu na ploche, v Stiahnutých
  a v Dokumentoch. Do výstupu vždy napíš, ktorý súbor si použil.

## Nacenenie pre klienta

1. Nájdi cenník, ktorý zadanie menuje. Ak ich je viac, použi najnovší a napíš ktorý.
2. Položky páruj podľa názvu, variantu a balenia. Pri viacerých možných zhodách vyber
   najpravdepodobnejšiu a ostatné uveď v poznámke.
3. Položku, ktorú v cenníku nenájdeš, nenaceňuj odhadom. Daj ju do zoznamu „nenájdené".
4. Ceny ber presne z tabuľky. Množstevné pásma a zľavy použi len vtedy, keď ich cenník obsahuje.
   DPH, dopravu ani zľavy nevymýšľaj. Či sú ceny s DPH, uveď len ak to cenník hovorí.
5. Výstup do podpriečinka `RRRR-MM-DD nacenenie <klient>`:
   - `nacenenie.xlsx`: položka, variant, množstvo, jednotková cena, spolu, riadok v cenníku,
     poznámka. Súčty vzorcom.
   - `nacenenie.md`: krátke zhrnutie, použitý cenník, predpoklady a nenájdené položky.
6. Pred koncom prepočítaj kontrolu: súčet riadkov sa musí rovnať celkovej sume.

## Projekty

- Mapu projektov a ich priečinkov máš v pokynoch (je to súbor `C:\JARVIS\PROJEKTY.md`).
  Keď zadanie menuje projekt, nájdi ho v mape.
- Projekty ostávajú tam, kde sú. Netreba ich sem kopírovať, pracuj s nimi na mieste.
- Čo sa oplatí zapamätať z úloh, píš sem do `POZNAMKY.md`
  (dátum, čo sa spravilo, kde je výstup) a na začiatku úlohy si ho prečítaj, ak existuje.
- Kód v projektoch meň len vtedy, keď to zadanie výslovne žiada. Necommituj a nepushuj bez pokynu.

## Bežné druhy zadaní

- „Nájdi mi X a daj mi to do stiahnutých / na plochu“: nájdi správny súbor podľa mapy projektov,
  skopíruj ho na žiadané miesto (originál nechaj, kde je) a povedz presný názov súboru a koľko má riadkov.
- Výskum na webe alebo YouTube („nájdi mi niche“, „zisti, kto predáva…“): hľadaj naozaj, uveď zdroje
  s odkazmi, výsledok ulož sem ako `vysledok.md` v podpriečinku úlohy. Čo je „môj obor“, zisti z mapy
  projektov.
- „Otvor mi…“: otvor súbor alebo priečinok v počítači (napr. cez `explorer.exe` alebo `start`).
- Úprava v projekte: urob ju priamo v priečinku projektu podľa mapy a napíš, čo si zmenil.

## Priebeh

- Pred každým väčším krokom napíš jednu krátku vetu po slovensky, čo ideš robiť. Tá veta sa ukazuje
  na dashboarde a číta sa, keď sa používateľ opýta, ako to ide.
- Keď sa niečo nedá dokončiť, v SUMMARY povedz presne, čo je hotové, čo nie a prečo.

## Kontrola pred koncom (len pri výpočtoch)

Platí pre úlohy, kde niečo počítaš alebo spočítavaš: nacenenia, súčty, počty záznamov, štatistiky,
porovnania čísel. Pri jednoduchých veciach (nájsť a skopírovať súbor, otvoriť priečinok, krátka úprava
textu, vyhľadanie informácie) ju nerob, tam stačí overiť, že výsledok je na mieste.

Chyba, ktorá sa už stala: výpočet bol správny, ale v hovorenom zhrnutí sa zmiešali dve delenia toho istého
súboru (segment a typ), takže časti nedali súčet. Aby sa to neopakovalo:

1. Každé číslo, ktoré ide do výsledku alebo do SUMMARY, prepočítaj druhým nezávislým spôsobom priamo
   zo zdrojového súboru (iný skript alebo iný postup). Ak sa dva výsledky líšia, nájdi príčinu.
2. Časti musia dať celok. Keď povieš súčet a rozpis, rozpis sa musí rovnať súčtu. Ak menuješ len
   niektoré časti, povedz „z toho“.
3. Nemiešaj v jednej odpovedi dve rôzne delenia. Použi to, ktoré má súbor ako hlavné, a jeho vlastné
   názvy. Ak používateľ použil iné slovo (napr. „headshopy“, „lekárne“), povedz, ku ktorej kategórii
   súboru si ho priradil. Podrobnejšie podtypy uvádzaj len navyše a označ ich ako podtypy.
4. Ak má súbor vlastné súčty (hlavička, riadok Spolu), porovnaj s nimi svoje čísla.
5. Až potom napíš SUMMARY a porovnaj ho číslo po čísle s výsledným súborom. Čísla v SUMMARY musia byť
   tie isté ako vo výsledku.
6. Uložený výstup s číslami po uložení otvor a over súčet a počet riadkov.

## Zákony, vláda, legislatíva

Pri otázke na slovenský zákon, novelu, rokovanie vlády, uznesenie alebo pripomienkové konanie použi skill
`slovenska-legislativa` (mapa oficiálnych zdrojov, skript na čítanie stránok, sledované témy). Odpovedaj
stavom s dátumom a zdrojom a povedz, čo sa overiť nepodarilo.

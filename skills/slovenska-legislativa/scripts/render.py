"""Vykresli stranku v skrytom Edge (aj tie, co sa skladaju skriptom) a vypise jej text.

    python render.py <url>                 text stranky (najprv obycajne stiahnutie, pri prazdnej
                                           kostre alebo ochrane proti robotom skryty prehliadac)
    python render.py <url> --render        vzdy cez skryty prehliadac
    python render.py <url> --links         text + zoznam odkazov (text -> adresa)
    python render.py <url> --html          surove HTML po vykresleni
    python render.py <url> --wait 12000    dlhsie cakanie na skripty (ms, predvolene 8000)
    python render.py <url> --find kratom   len riadky so slovom (a 2 riadky okolo)

Nepotrebuje nic okrem Pythonu a Edge. Nic neuklada.
"""
import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from urllib.parse import urljoin

EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
SKIP = {"script", "style", "noscript", "svg", "head", "template"}
BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "table", "section", "article", "ul", "ol", "dd", "dt"}


class Text(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.out, self.links, self.skip, self.href, self.atext = base, [], [], 0, None, []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        if tag == "a" and not self.skip:
            self.href, self.atext = dict(attrs).get("href"), []

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        elif tag in BLOCK:
            self.out.append("\n")
        if tag == "a" and self.href:
            t = " ".join("".join(self.atext).split())
            if t and not self.href.startswith(("javascript:", "#", "mailto:", "tel:")):
                self.links.append((t, urljoin(self.base, self.href)))
            self.href = None

    def handle_data(self, data):
        if self.skip:
            return
        self.out.append(data)
        if self.href is not None:
            self.atext.append(data)


def render(url, wait):
    exe = next((e for e in EDGE if os.path.exists(e)), None)
    if not exe:
        sys.exit("Nenasiel som Edge ani Chrome.")
    prof = tempfile.mkdtemp(prefix="render-")
    try:
        r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars", "--lang=sk-SK",
                            f"--user-data-dir={prof}", f"--virtual-time-budget={wait}", "--dump-dom", url],
                           capture_output=True, timeout=90)
        return r.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return ""          # stranka sa nedocitala (ochrana proti robotom alebo zaseknuty skript)
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def plain(url):
    """Obycajne stiahnutie s hlavickou prehliadaca. Vrati HTML alebo prazdny retazec."""
    import urllib.request
    try:
        rq = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                  "(KHTML, like Gecko) Chrome/131.0 Safari/537.36", "Accept-Language": "sk,cs;q=0.8"})
        with urllib.request.urlopen(rq, timeout=30) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
        return raw.decode(enc, "replace")
    except Exception:
        return ""


def usable(doc):
    """Ma stranka skutocny obsah? Kostra aplikacie a ochrana proti robotom sa neratuju."""
    if not doc or "Bot Detection" in doc[:3000]:
        return False
    p = Text("")
    p.feed(doc)
    return len(" ".join("".join(p.out).split())) > 700


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--wait", type=int, default=8000)
    ap.add_argument("--links", action="store_true")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--find")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    doc = "" if a.render else plain(a.url)
    how = "priamo"
    if not usable(doc):
        doc, how = render(a.url, a.wait), "cez prehliadac"
    print(f"[zdroj: {a.url} | nacitane {how}" + ("" if usable(doc) else " | POZOR: stranka nevydala obsah (kostra alebo ochrana proti robotom)") + "]", file=sys.stderr)
    if a.html:
        print(doc)
        return
    p = Text(a.url)
    p.feed(doc)
    lines = [" ".join(l.split()) for l in html.unescape("".join(p.out)).splitlines()]
    lines = [l for l in lines if l and l != "|"]
    if a.find:
        rx = re.compile(re.escape(a.find), re.I)
        hit = sorted({j for i, l in enumerate(lines) if rx.search(l) for j in range(max(0, i - 2), min(len(lines), i + 3))})
        lines = [lines[i] for i in hit] or ["(nic so slovom '%s')" % a.find]
    print("\n".join(lines))
    if a.links:
        print("\n--- ODKAZY ---")
        seen = set()
        for t, h in p.links:
            if h not in seen:
                seen.add(h)
                print(f"{t[:90]} -> {h}")


if __name__ == "__main__":
    main()

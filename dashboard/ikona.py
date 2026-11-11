"""Ziva ikona JARVISa na paneli uloh.

Prehliadac vie ikonu okna menit len asi 4-krat za sekundu, co vyzera sekane. Preto ikonu okna
dashboardu nastavuje priamo tento modul (sprava WM_SETICON) z vopred vykreslenych zaberov:
vonkajsi prstenec emblemu sa otaca, luce pomaly opacne, stred dycha. Rychlost a farba idu
podla stavu JARVISa. Cierne okno JARVISa si ikonu zmenit neda (skusene), preto ho nechavame tak.

Spusta ho server.py vo vlastnom vlakne. Skuska bez servera:
    python ikona.py [sekundy] [stav]        napr.  python ikona.py 10 thinking
"""
from __future__ import annotations

import ctypes
import io
import math
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "ikona.png"            # emblem na ciernom podklade, stred v strede obrazka
SPLIT = 0.770                       # hranica medzi lucmi a vonkajsim prstencom (podiel polomeru)
ORB = 0.320                         # polomer svietiaceho stredu
FRAMES = 72                         # zaberov v slucke: prstenec sa otoci o 120 stupnov, luce o 60 opacne
TITLE = "JARVIS"
BROWSER_CLASSES = ("Chrome_WidgetWin_1",)

# Zabery slucky za sekundu podla stavu (0 = stoji). Jeden zaber = 1,67 stupna prstenca.
# Panel uloh prekresli ikonu najviac asi 12-krat za sekundu (zmerane), preto su rychlosti mierne:
# pri vyssich by boli kroky medzi dvoma prekresleniami velke a pohyb by skakal.
SPEED = {"offline": 0, "muted": 0, "starting": 24, "idle": 11, "listening": 17, "thinking": 30, "speaking": 20, "approval": 12}
BUSY_SPEED = 24                     # ked bezi uloha alebo pracuje relacia
SEND_HZ = 30                        # kolkokrat za sekundu ikonu posielame oknu
LOOKS = {"offline": "gray", "muted": "dim", "listening": "light", "approval": "red"}

WM_SETICON, ICON_SMALL, ICON_BIG, SMTO_ABORTIFHUNG = 0x0080, 0, 1, 0x0002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_ENUMPROC, wintypes.LPARAM]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.CreateIconFromResourceEx.argtypes = [ctypes.c_char_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
                                             ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.CreateIconFromResourceEx.restype = wintypes.HICON
_user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
_user32.SendMessageTimeoutW.restype = wintypes.LPARAM
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]


def find_windows():
    """Viditelne okna dashboardu (okno prehliadaca s nazvom JARVIS)."""
    browser = []
    buf = ctypes.create_unicode_buffer(256)

    def cb(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True
        _user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value != TITLE:
            return True
        _user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in BROWSER_CLASSES:
            browser.append(hwnd)
        return True

    _user32.EnumWindows(_ENUMPROC(cb), 0)
    return browser


class Renderer:
    """Kresli zabery slucky a robi z nich ikony Windows. Zabery sa pocitaju az ked ich treba."""

    def __init__(self):
        from PIL import Image, ImageDraw
        self.Image = Image
        self.W = W = 256                                    # pracovna velkost, zmensuje sa az hotovy zaber
        src = Image.open(SRC).convert("RGB").resize((W, W), Image.LANCZOS)
        self.src = src
        c = (W - 1) / 2

        def disc(r):
            m = Image.new("L", (W * 2, W * 2), 0)
            ImageDraw.Draw(m).ellipse((W - 2 * r, W - 2 * r, W + 2 * r, W + 2 * r), fill=255)
            return m.resize((W, W), Image.LANCZOS)

        self.m_inner = disc(c * SPLIT)
        self.m_all = disc(c - 1)
        self.bg = Image.new("RGB", (W, W), (9, 6, 4))
        # ziara stredu: kruhovy prechod, sila sa meni pocas slucky
        glow = Image.new("L", (W, W), 0)
        px = glow.load()
        rr = c * ORB * 1.9
        for y in range(W):
            for x in range(W):
                d = math.hypot(x - c, y - c) / rr
                if d < 1:
                    px[x, y] = int(255 * (1 - d) ** 2)
        self.glow = glow
        self.cache: dict[tuple, int] = {}

    def frame(self, i: int, look: str):
        Image = self.Image
        a = 120.0 * i / FRAMES
        ring = self.src.rotate(-a, resample=Image.BICUBIC)                # v smere hodinovych ruciciek
        core = self.src.rotate(a / 2, resample=Image.BICUBIC)             # luce pomaly opacne
        im = Image.composite(core, ring, self.m_inner)
        beat = 0.5 - 0.5 * math.cos(2 * math.pi * i / FRAMES)             # 0..1..0 pocas slucky
        warm = Image.new("RGB", im.size, (255, 236, 190))
        from PIL import ImageChops, ImageEnhance
        lit = ImageChops.screen(im, Image.composite(warm, Image.new("RGB", im.size, 0), self.glow.point(lambda v: int(v * (0.15 + 0.5 * beat)))))
        im = lit
        if look == "gray":
            im = ImageEnhance.Brightness(im.convert("L").convert("RGB")).enhance(0.55)
        elif look == "dim":
            im = ImageEnhance.Brightness(ImageEnhance.Color(im).enhance(0.3)).enhance(0.8)
        elif look == "light":
            im = ImageEnhance.Brightness(ImageEnhance.Color(im).enhance(0.72)).enhance(1.15)
        elif look == "red":
            r, g, b = im.split()
            im = Image.merge("RGB", (r, g.point(lambda v: int(v * 0.42)), b.point(lambda v: int(v * 0.5))))
        im = Image.composite(im, self.bg, self.m_all).convert("RGBA")
        im.putalpha(self.m_all)
        return im

    def icon(self, i: int, look: str, size: int) -> int:
        key = (i, look, size)
        h = self.cache.get(key)
        if h:
            return h
        im = self.frame(i, look).resize((size, size), self.Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="ICO", sizes=[(size, size)], bitmap_format="bmp")
        data = buf.getvalue()[22:]                                         # za hlavickou suboru je uz samotna ikona
        h = _user32.CreateIconFromResourceEx(data, len(data), True, 0x00030000, size, size, 0)
        if h:
            self.cache[key] = h
        return h or 0


def _set(hwnd, which, hicon):
    res = ctypes.c_size_t(0)
    _user32.SendMessageTimeoutW(hwnd, WM_SETICON, which, hicon, SMTO_ABORTIFHUNG, 60, ctypes.byref(res))


def run(state_fn, stop: threading.Event | None = None, seconds: float | None = None, log=None, force_big: int = 0):
    """state_fn() -> (stav, pracuje_sa). Bezi, kym nenastane stop alebo neuplynu sekundy."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)                     # nech dostaneme skutocne velkosti ikon
    except Exception:                                                      # noqa: BLE001
        pass
    small = max(16, _user32.GetSystemMetrics(49))                          # SM_CXSMICON
    big = force_big or max(16, _user32.GetSystemMetrics(11))              # SM_CXICON
    rnd = Renderer()
    t_end = time.time() + seconds if seconds else None
    phase, last, shown, t_find, t_state = 0.0, time.time(), None, 0.0, 0.0
    browser, state, busy, sent = [], "idle", False, 0
    while not (stop and stop.is_set()) and not (t_end and time.time() > t_end):
        now = time.time()
        if now - t_find > 2.0:
            t_find = now
            browser = find_windows()
            shown = None                                                   # nove okno alebo obnovena stranka: nastav znova
        if now - t_state > 0.5:
            t_state = now
            try:
                state, busy = state_fn()
            except Exception:                                              # noqa: BLE001
                state, busy = "offline", False
        look = LOOKS.get(state, "normal")
        speed = SPEED.get(state, 9)
        if busy and speed:
            speed = max(speed, BUSY_SPEED)
        phase = (phase + (now - last) * speed) % FRAMES
        last = now
        key = (int(phase), look)
        if browser and key != shown:
            hb, hs = rnd.icon(key[0], look, big), rnd.icon(key[0], look, small)
            for w in browser:
                if hb:
                    _set(w, ICON_BIG, hb)
                if hs:
                    _set(w, ICON_SMALL, hs)
            shown = key
            sent += 1
        time.sleep(1 / SEND_HZ if (browser and speed) else 0.25)
    if log:
        log(f"ikona: {sent} zmien, okna dashboardu {len(browser)}, velkosti {big}/{small}")
    return sent


def start(state_fn, log=None):
    """Spusti animaciu vo vlakne. Chyba ikony nesmie zhodit dashboard."""
    def body():
        try:
            run(state_fn)
        except Exception as e:                                             # noqa: BLE001
            if log:
                log(f"ikona: {e!r}")
    t = threading.Thread(target=body, daemon=True, name="ikona")
    t.start()
    return t


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    st = sys.argv[2] if len(sys.argv) > 2 else "idle"
    print("okna dashboardu:", len(find_windows()))
    t0 = time.time()
    n = run(lambda: (st, False), seconds=secs, log=print, force_big=int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    print("zmien za sekundu: %.1f" % (n / (time.time() - t0)))

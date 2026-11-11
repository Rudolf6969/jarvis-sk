# -*- coding: utf-8 -*-
"""JARVIS dashboard: lokalny server, ktory len CITA stav JARVISa a Claude Code.

Nic nezapisuje do hey-claude, nic neposiela von a pocuva len na 127.0.0.1.

  pythonw server.py            spusti server a otvori okno dashboardu
  python  server.py --no-open  len server (http://127.0.0.1:8642/)

Odkial berie data:
  hey-claude/state/logs/app.log     stav JARVISa, udalosti, upozornenia
  hey-claude/state/latency.csv      rozhovor a odozva
  hey-claude/state/tasks.json       hlasove ulohy
  ~/.claude/projects/*/*.jsonl      relacie Claude Code (na com pracuje, co dobehlo)
  ~/.claude/cache/jarvis-dashboard-limits.json   limity planu (zapisuje statusline)
  psutil + NVML                     CPU, RAM, GPU, siet
"""
from __future__ import annotations

import collections
import hashlib
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8642
HERE = Path(__file__).resolve().parent
JARVIS = HERE.parent / "hey-claude"
STATE = JARVIS / "state"
LOG_DIR = STATE / "logs"
APP_LOG = LOG_DIR / "app.log"
LATENCY = STATE / "latency.csv"
TASKS = STATE / "tasks.json"
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
PROJECTS = CLAUDE_DIR / "projects"
LIMITS_FILE = CLAUDE_DIR / "cache" / "jarvis-dashboard-limits.json"
OWN_LOG = HERE / "dashboard.log"

SESSION_WINDOW_S = 36 * 3600      # relacie starsie nez toto sa necitaju
MAX_SESSION_FILES = 40


def own_log(text: str) -> None:
    try:
        if OWN_LOG.exists() and OWN_LOG.stat().st_size > 512_000:
            OWN_LOG.unlink()
        with open(OWN_LOG, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
    except OSError:
        pass


def short(text, n: int) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def iso_ts(value) -> float | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def local_ts(value: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> float | None:
    try:
        return time.mktime(time.strptime(value, fmt))
    except (ValueError, TypeError, OverflowError):
        return None


# ---------------------------------------------------------------------------------------
# System: CPU, RAM, GPU, disk, siet, proces JARVISa
# ---------------------------------------------------------------------------------------
class System:
    def __init__(self):
        self.psutil = None
        self.nvml = None
        self.gpu = None
        self.gpu_name = ""
        try:
            import psutil
            psutil.cpu_percent(None)
            self.psutil = psutil
        except Exception as e:                                   # noqa: BLE001
            own_log(f"psutil chyba: {e}")
        try:
            import pynvml
            pynvml.nvmlInit()
            self.gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(self.gpu)
            self.gpu_name = name.decode() if isinstance(name, bytes) else str(name)
            self.nvml = pynvml
        except Exception:                                        # noqa: BLE001
            self.gpu = None
        self.hist = {k: collections.deque(maxlen=90) for k in ("cpu", "gpu", "ram", "vram")}
        self._net = None
        self._proc = None
        self._proc_scan = 0.0
        self.data: dict = {}
        self.jarvis: dict = {"running": False}

    def _find_jarvis(self):
        ps = self.psutil
        best = None
        for p in ps.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (p.info["name"] or "").lower()
                if not name.startswith("python"):
                    continue
                cmd = " ".join(p.info["cmdline"] or []).replace("\\", "/")
                if "-m heyclaude" not in cmd and "heyclaude/__main__" not in cmd:
                    continue
                rss = p.memory_info().rss
                if best is None or rss > best[0]:
                    best = (rss, p)
            except Exception:                                    # noqa: BLE001
                continue
        return best[1] if best else None

    def sample(self):
        ps = self.psutil
        now = time.time()
        d: dict = {"gpu_name": self.gpu_name}
        if ps is not None:
            try:
                d["cpu"] = ps.cpu_percent(None)
                vm = ps.virtual_memory()
                d["ram"] = vm.percent
                d["ram_used_gb"] = round((vm.total - vm.available) / 2**30, 1)
                d["ram_total_gb"] = round(vm.total / 2**30, 1)
                du = ps.disk_usage("C:\\")
                d["disk"] = du.percent
                d["disk_free_gb"] = round(du.free / 2**30)
                io = ps.net_io_counters()
                if self._net is not None:
                    dt = max(0.2, now - self._net[0])
                    d["net_down"] = max(0, (io.bytes_recv - self._net[1]) / dt)
                    d["net_up"] = max(0, (io.bytes_sent - self._net[2]) / dt)
                self._net = (now, io.bytes_recv, io.bytes_sent)
            except Exception as e:                               # noqa: BLE001
                own_log(f"system sample: {e}")
        if self.gpu is not None:
            try:
                nv = self.nvml
                d["gpu"] = float(nv.nvmlDeviceGetUtilizationRates(self.gpu).gpu)
                mem = nv.nvmlDeviceGetMemoryInfo(self.gpu)
                d["vram"] = round(100.0 * mem.used / mem.total, 1)
                d["vram_used_gb"] = round(mem.used / 2**30, 1)
                d["vram_total_gb"] = round(mem.total / 2**30, 1)
                d["gpu_temp"] = int(nv.nvmlDeviceGetTemperature(self.gpu, nv.NVML_TEMPERATURE_GPU))
            except Exception:                                    # noqa: BLE001
                pass
        for k in self.hist:
            if k in d:
                self.hist[k].append(round(d[k], 1))
        d["hist"] = {k: list(v) for k, v in self.hist.items()}
        self.data = d
        self._sample_jarvis(now)

    def _sample_jarvis(self, now: float):
        ps = self.psutil
        if ps is None:
            return
        alive = False
        if self._proc is not None:
            try:
                alive = self._proc.is_running() and self._proc.status() != ps.STATUS_ZOMBIE
            except Exception:                                    # noqa: BLE001
                alive = False
        if not alive and now - self._proc_scan > 3:
            self._proc_scan = now
            self._proc = self._find_jarvis()
            if self._proc is not None:
                try:
                    self._proc.cpu_percent(None)
                except Exception:                                # noqa: BLE001
                    pass
            alive = self._proc is not None
        if not alive:
            self._proc = None
            self.jarvis = {"running": False}
            return
        p = self._proc
        try:
            info = {"running": True, "pid": p.pid, "started": p.create_time(),
                    "rss_mb": round(p.memory_info().rss / 2**20),
                    "cpu": round(p.cpu_percent(None) / max(1, ps.cpu_count() or 1), 1)}
            kids = p.children(recursive=True)
            info["children"] = len(kids)
            rss = 0
            names = collections.Counter()
            for k in kids:
                try:
                    rss += k.memory_info().rss
                    names[(k.name() or "?").lower().replace(".exe", "")] += 1
                except Exception:                                # noqa: BLE001
                    continue
            info["children_rss_mb"] = round(rss / 2**20)
            info["children_names"] = dict(names.most_common(5))
            self.jarvis = info
        except Exception:                                        # noqa: BLE001
            self._proc = None
            self.jarvis = {"running": False}


# ---------------------------------------------------------------------------------------
# app.log: stav JARVISa, udalosti, upozornenia
# ---------------------------------------------------------------------------------------
LINE_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ (\w+)\s+(.*?): (.*)$")
TAG_RE = re.compile(r"^\[([a-z][a-z0-9\-]*)(?: ([\w\-]+))?\] ?(.*)$", re.S)
ALERT_WORDS = re.compile(r"fail|error|couldn't|could not|crash|not registered|traceback|exception|"
                         r"timed out|timeout|unavailable|refused", re.I)
NO_ALERT_TAGS = {"heard", "typed", "latency", "approval", "widget", "followup", "continuation"}


class JarvisLog:
    def __init__(self):
        self.offset = 0
        self.carry = b""
        self.lines = collections.deque(maxlen=400)
        self.events = collections.deque(maxlen=60)   # dolezite momenty (prikazy, ulohy, povolenia)
        self._reset_run(None)

    def _reset_run(self, ts):
        self.run = {"version": None, "started": ts, "ready": None, "wake": None, "agent": None,
                    "stt": None, "voice": None}
        self.state = "starting"
        self.state_ts = ts or time.time()
        self.mic = False
        self.listening_on = True
        self.heard = None
        self.reply_ts = None
        self.tasks_running: dict = {}
        self.approval = None
        self.alerts: dict = {}

    def _set(self, state: str, ts: float):
        if state != self.state:
            self.state = state
            self.state_ts = ts

    def poll(self):
        try:
            size = APP_LOG.stat().st_size
        except OSError:
            return
        if size < self.offset:                                   # log sa otocil
            self.offset, self.carry = 0, b""
        if size == self.offset:
            return
        first = self.offset == 0 and size > 700_000
        try:
            with open(APP_LOG, "rb") as fh:
                fh.seek(size - 700_000 if first else self.offset)
                data = fh.read()
                self.offset = fh.tell()
        except OSError:
            return
        if first:
            data = data.split(b"\n", 1)[-1]
        parts = (self.carry + data).split(b"\n")
        self.carry = parts.pop()
        for raw in parts:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            if line.strip():
                self._line(line)

    def _line(self, line: str):
        m = LINE_RE.match(line)
        if not m:                                                # pokracovanie (traceback)
            if self.lines:
                last = self.lines[-1]
                if len(last["msg"]) < 1200:
                    last["msg"] += "\n" + line
            return
        ts = local_ts(m.group(1)) or time.time()
        level, thread, msg = m.group(2), m.group(3), m.group(4)
        tag, arg, rest = "", "", msg
        tm = TAG_RE.match(msg)
        if tm:
            tag, arg, rest = tm.group(1), tm.group(2) or "", tm.group(3)
        self.lines.append({"ts": ts, "level": level, "tag": tag or thread, "msg": msg})
        try:
            self._feed(ts, level, tag, arg, rest, msg)
        except Exception:                                        # noqa: BLE001
            own_log("feed: " + traceback.format_exc())

    def _alert(self, ts, key, text, level="warn", detail=""):
        a = self.alerts.get(key)
        if a is None:
            a = self.alerts[key] = {"key": key, "first": ts, "count": 0}
        a.update(text=text, last=ts, level=level)
        if detail:
            a["detail"] = detail
        a["count"] += 1

    def _event(self, ts, kind, text):
        self.events.append({"ts": ts, "kind": kind, "text": short(text, 220)})

    def _feed(self, ts, level, tag, arg, rest, msg):
        run = self.run
        if msg.startswith("---- hey-claude"):
            self._reset_run(ts)
            vm = re.search(r"hey-claude ([\w.\-]+)", msg)
            self.run["version"] = vm.group(1) if vm else None
            self._event(ts, "start", "JARVIS štartuje")
            return
        if tag == "ready":
            body, _, _load = rest.partition(" [")
            info = {}
            for part in body.split("; "):
                k, _, v = part.partition(": ")
                info[k.strip()] = v.strip()
            run["ready"] = info
            run["ready_ts"] = ts
            stt = info.get("stt", "")
            if "fallback" in stt or "cpu" in stt.split("(")[0]:
                self._alert(ts, "stt-cpu", "Prepis reči beží na CPU: " + stt, "warn")
            self._set("idle", ts)
            self._event(ts, "ready", "Pripravený: " + body)
        elif tag == "wake":
            if "threshold" in rest and "(" in rest:
                run["wake"] = rest
            elif "couldn't load" in rest or "failed" in rest:
                self._alert(ts, "wake", "Budiace slovo: " + rest, "warn")
        elif tag == "hotkey" and "not registered" in rest:
            key = rest.replace("not registered:", "").replace(": already in use by another app", "").strip()
            self._alert(ts, "hotkey", "Klávesová skratka " + key + " je obsadená inou aplikáciou", "warn")
        elif tag == "agent" and rest.startswith("model"):
            am = re.match(r"model ([\w.\-]+), (\d+) tools(?:, MCP: (.*))?", rest)
            if am:
                mcp = []
                for item in (am.group(3) or "").split(", "):
                    mm = re.match(r"(.+?)\(([\w\- ]+)\)$", item.strip())
                    if mm:
                        mcp.append({"name": mm.group(1), "status": mm.group(2)})
                    elif item.strip():
                        mcp.append({"name": item.strip(), "status": "ok"})
                run["agent"] = {"model": am.group(1), "tools": int(am.group(2)), "mcp": mcp}
        elif tag == "stt" and " on " in rest:
            run["stt"] = rest
        elif tag == "tts" and rest.startswith("voice:"):
            run["voice"] = rest.split(":", 1)[1].strip()
        elif tag == "mic":
            self.mic = rest.startswith("open")
            if self.mic and self.state in ("starting", "muted"):
                self._set("idle", ts)
        elif tag == "listen" and rest[:3].strip() in ("on", "off"):
            self.listening_on = rest.startswith("on")
            self._set("idle" if self.listening_on else "muted", ts)
        elif tag in ("heard", "typed"):
            if "only the wake word" in rest:
                self._set("listening", ts)
                return
            hm = re.match(r"(['\"])(.*)\1(.*)$", rest, re.S)
            text = hm.group(2) if hm else rest
            tail = hm.group(3) if hm else ""
            how = "napísané" if tag == "typed" else ("pokračovanie" if "(follow-up)" in tail else "hlas")
            self.heard = {"ts": ts, "text": text.replace("\\'", "'"), "how": how}
            self._set("thinking", ts)
        elif tag == "latency":
            self.reply_ts = ts
            self._set("speaking", ts)
        elif tag == "followup":
            self._set("listening" if rest.startswith("listening") else "idle", ts)
        elif tag == "barge-in":
            self._set("listening", ts)
        elif tag == "hush":
            self._set("idle", ts)
        elif tag == "instant":
            if " matched in " in rest:
                self._event(ts, "instant", "Okamžitý príkaz: " + rest.split(" matched in ")[0])
                self._set("idle", ts)
            elif "failed" in rest:
                self._alert(ts, "instant", "Okamžitý príkaz zlyhal: " + rest, "warn")
        elif tag == "task":
            tid = arg
            if rest.startswith("started in"):
                self.tasks_running[tid] = ts
                self._event(ts, "task", f"Úloha {tid} spustená: " + rest.split(": ", 1)[-1])
            else:
                st = rest.split(":", 1)[0].strip().split(" ")[0]
                if st in ("done", "failed", "stopped"):
                    self.tasks_running.pop(tid, None)
                    what = rest.split(":", 1)[-1].split("(resume:")[0].strip() if ":" in rest else ""
                    self._event(ts, "task-ok" if st == "done" else "task-bad", f"Úloha {tid} {st}: {what}")
        elif tag == "approval":
            if "listening" in rest or " · " in rest:
                self.approval = {"ts": ts, "text": rest}
                self._set("approval", ts)
                if " · " in rest:
                    self._event(ts, "approval", "Žiada povolenie: " + rest)
            else:
                self.approval = None
                if self.state == "approval":
                    self._set("idle", ts)
        elif tag == "crash":
            self._alert(ts, "crash", "Pád vlákna asistenta: " + rest, "bad")
            self._event(ts, "crash", rest)
        elif tag == "sessions" and ("failed" in rest or "another hey-claude" in rest):
            self._alert(ts, "sessions", "Sledovanie relácií: " + rest, "warn")
        elif tag and "connection failed" in rest:
            n = re.search(r"connection failed \((\d+)\)", rest)
            self._alert(ts, "conn-" + tag, f"{tag}: pripojenie zlyháva" + (f" · pokus {n.group(1)}" if n else ""),
                        "warn", stderr_hint(tag))
        elif (level in ("WARNING", "ERROR", "CRITICAL") or ALERT_WORDS.search(msg)) and tag not in NO_ALERT_TAGS:
            key = re.sub(r"\d+", "#", (tag + ":" + rest)[:70])
            self._alert(ts, key, short(msg, 260), "bad" if level in ("ERROR", "CRITICAL") else "warn")

    def snapshot(self, running: bool) -> dict:
        now = time.time()
        state, since = self.state, self.state_ts
        if state == "thinking" and now - since > 180:
            state, since = "idle", since + 180
        if state == "speaking" and now - since > 45:
            state, since = "idle", since + 45
        if state == "listening" and now - since > 60:
            state, since = "idle", since + 60
        if not running:
            state = "offline"
        return {"state": state, "state_since": since, "mic": self.mic and running,
                "listening_on": self.listening_on, "heard": self.heard, "reply_ts": self.reply_ts,
                "approval": self.approval if running else None,
                "tasks_running": len(self.tasks_running) if running else 0,
                "run": self.run,
                "alerts": sorted(self.alerts.values(), key=lambda a: -a["last"])[:12],
                "events": list(self.events)[-25:],
                "log": [{"ts": ln["ts"], "tag": ln["tag"], "level": ln["level"], "msg": short(ln["msg"], 300)}
                        for ln in list(self.lines)[-70:]]}


def stderr_hint(name: str) -> str:
    """Prve riadky poslednej chyby zo state/logs/<name>.stderr.log (preco sa nieco nepripaja)."""
    f = LOG_DIR / f"{name}.stderr.log"
    try:
        size = f.stat().st_size
        with open(f, "rb") as fh:
            fh.seek(max(0, size - 6000))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    block = re.split(r"^--- .*$", text, flags=re.M)[-1].strip().splitlines()
    block = [b.strip() for b in block if b.strip() and "complete log of this run" not in b]
    return short(" · ".join(block[:3]), 240)


# ---------------------------------------------------------------------------------------
# latency.csv: rozhovor
# ---------------------------------------------------------------------------------------
def _num(row: dict, key: str):
    try:
        return round(float(row.get(key) or ""), 2)
    except ValueError:
        return None


class Conversation:
    def __init__(self):
        self.sig = None
        self.rows: list = []
        self.today = 0

    def poll(self):
        try:
            st = LATENCY.stat()
        except OSError:
            self.rows, self.today = [], 0
            return
        sig = (st.st_mtime_ns, st.st_size)
        if sig == self.sig:
            return
        self.sig = sig
        rows = []
        try:
            with open(LATENCY, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    rows.append({"ts": local_ts(r.get("when", "")), "route": r.get("route", ""),
                                 "source": r.get("source", ""), "text": r.get("text", ""),
                                 "reply": r.get("reply", ""), "first_audio": _num(r, "speech_end_to_first_audio"),
                                 "lookup": _num(r, "speech_end_to_lookup_answer"),
                                 "effect": _num(r, "speech_end_to_effect"), "stt": _num(r, "stt"),
                                 "first_token": _num(r, "first_token"), "audio_s": _num(r, "audio_s"),
                                 "device": r.get("stt_device", ""), "intent": r.get("intent", "")})
        except (OSError, csv.Error) as e:
            own_log(f"latency.csv: {e}")
            return
        day = time.strftime("%Y-%m-%d")
        self.today = sum(1 for r in rows if r["ts"] and time.strftime("%Y-%m-%d", time.localtime(r["ts"])) == day)
        self.rows = rows[-40:]


# ---------------------------------------------------------------------------------------
# Relacie Claude Code (~/.claude/projects/*/*.jsonl)
# ---------------------------------------------------------------------------------------
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
PASTE_RE = re.compile(r"<pasted_content[^>]*>.*?(?:</pasted_content[^>]*>|$)", re.S)
SKIP_PREFIX = (b'{"type":"api-request', b'{"type":"file-history', b'{"type":"atis-latch',
               b'{"type":"mode"', b'{"type":"tools-used"', b'{"type":"queue-operation"')
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def clean_prompt(text: str):
    """Text od pouzivatela -> citatelna poziadavka; None = nie je to poziadavka."""
    t = REMINDER_RE.sub("", text or "").strip()
    # hlasova uloha: JARVIS za zadanie prilepi rozhovor, ktory k nej viedol; na dashboarde staci zadanie
    t = re.split(r"\s+This task was asked for by voice\.", t, maxsplit=1)[0].strip()
    if not t:
        return None
    if t.startswith("<local-command-") or t.startswith("Caveat: The messages below"):
        return None
    if t.startswith("This session is being continued from a previous conversation"):
        return None
    if "<task-notification>" in t[:200]:
        sm = re.search(r"<summary>(.*?)</summary>", t, re.S)
        return "↻ " + (short(sm.group(1), 160) if sm else "výsledok úlohy na pozadí")
    cm = re.search(r"<command-name>(.*?)</command-name>", t, re.S)
    if cm:
        am = re.search(r"<command-args>(.*?)</command-args>", t, re.S)
        return (cm.group(1).strip() + " " + (am.group(1).strip() if am else "")).strip()
    t = PASTE_RE.sub(" [vložený text] ", t)
    t = re.sub(r"\[Image #\d+\]", "[obrázok]", t)
    return t.strip() or None


def tool_detail(inp: dict) -> str:
    for k in ("description", "file_path", "command", "pattern", "url", "query", "skill", "path", "prompt", "subject"):
        v = inp.get(k)
        if v:
            if k in ("file_path", "path"):
                v = re.split(r"[\\/]", str(v))[-1] or v
            return short(v, 110)
    return ""


def tool_label(name: str) -> str:
    if name.startswith("mcp__"):
        parts = name.split("__")
        if len(parts) > 2:
            return parts[1].replace("claude_ai_", "").replace("-", " ").replace("_", " ") + " · " + parts[-1]
    return name


def plain(text: str, n: int) -> str:
    t = re.sub(r"```.*?```", " [kód] ", text or "", flags=re.S)
    t = re.sub(r"^\s*\|?[\s:\-|]+\|\s*$", " ", t, flags=re.M)          # oddelovace tabuliek
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"\s*\|\s*", " · ", t)
    return short(t, n)


class Sess:
    def __init__(self, path: Path):
        self.path = path
        self.id = path.stem
        self.slug = path.parent.name
        self.offset = 0
        self.carry = b""
        self.mtime = 0.0
        self.title = ""
        self.custom_title = ""
        self.last_prompt = ""
        self.cwd = ""
        self.branch = ""
        self.model = ""
        self.entry = ""
        self.mode = ""
        self.first_ts = None
        self.last_ts = None
        self.turn = None
        self.turns = collections.deque(maxlen=8)
        self.pending: dict = {}
        self.last_tool = None
        self.ctx = 0
        self.out_hours = collections.defaultdict(int)
        self._msg = (None, 0)
        self.recap = ""
        self.compactions = 0
        self.prompts = 0
        self.last_error = None
        self.root = None

    # -- citanie ---------------------------------------------------------------------
    def poll(self) -> None:
        try:
            st = self.path.stat()
        except OSError:
            return
        if st.st_size < self.offset:
            self.__init__(self.path)
        self.mtime = st.st_mtime
        if st.st_size == self.offset:
            return
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self.offset)
                data = fh.read()
                self.offset = fh.tell()
        except OSError:
            return
        parts = (self.carry + data).split(b"\n")
        self.carry = parts.pop()
        for raw in parts:
            if not raw or raw.startswith(SKIP_PREFIX):
                continue
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            if isinstance(e, dict):
                try:
                    self.feed(e)
                except Exception:                                # noqa: BLE001
                    own_log("sess.feed: " + traceback.format_exc())

    def _start_turn(self, prompt: str, ts: float, implicit: bool = False):
        tr = self.turn
        if tr is not None:
            if tr["end"] is None:
                if not implicit and ts - tr["last"] < 1800:      # doplnenie pocas behu
                    tr["extra"] += 1
                    tr["last"] = ts
                    return
                tr["end"] = tr["last"]
                tr["interrupted"] = True
            self.turns.append(tr)
        self.turn = {"prompt": prompt, "start": ts, "last": ts, "end": None, "end_mid": None, "dur": None,
                     "text": "", "tools": 0, "errors": 0, "files": set(), "agents": 0, "extra": 0,
                     "interrupted": False, "error": "", "implicit": implicit, "stop": ""}
        if not implicit:
            self.prompts += 1

    def feed(self, e: dict):
        t = e.get("type")
        if t == "ai-title":
            self.title = e.get("aiTitle") or self.title
            return
        if t == "custom-title":
            self.custom_title = e.get("customTitle") or e.get("title") or self.custom_title
            return
        if t == "last-prompt":
            self.last_prompt = e.get("lastPrompt") or self.last_prompt
            return
        if t == "permission-mode":
            self.mode = e.get("permissionMode") or ""
            return
        if t not in ("user", "assistant", "system") or e.get("isSidechain"):
            return
        ts = iso_ts(e.get("timestamp")) or self.last_ts or self.mtime
        if self.first_ts is None:
            self.first_ts = ts
        self.last_ts = ts
        if e.get("cwd"):
            self.cwd = e["cwd"]
        if e.get("gitBranch"):
            self.branch = e["gitBranch"]
        if e.get("entrypoint"):
            self.entry = e["entrypoint"]
        tr = self.turn
        if t == "system":
            sub = e.get("subtype")
            if sub == "turn_duration" and tr is not None:
                tr["dur"] = e.get("durationMs")
                if tr["end"] is None:
                    tr["end"] = ts
            elif sub == "away_summary":
                self.recap = short(str(e.get("content") or "").replace("(disable recaps in /config)", ""), 420)
            elif sub == "compact_boundary":
                self.compactions += 1
            elif sub == "api_error" or e.get("level") == "error":
                self.last_error = {"ts": ts, "text": short(e.get("content") or e.get("error") or sub, 200)}
            return
        msg = e.get("message") if isinstance(e.get("message"), dict) else {}
        content = msg.get("content")
        if t == "user":
            if e.get("isMeta") or e.get("isCompactSummary"):
                return
            if isinstance(content, list):
                results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
                if results:
                    for b in results:
                        self.pending.pop(b.get("tool_use_id"), None)
                        if b.get("is_error") and tr is not None:
                            tr["errors"] += 1
                    if tr is not None:
                        tr["last"] = ts
                    return
                text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                if any(isinstance(b, dict) and b.get("type") == "image" for b in content) and "[Image" not in text:
                    text += " [obrázok]"
            else:
                text = str(content or "")
            if text.lstrip().startswith("[Request interrupted"):
                if tr is not None and tr["end"] is None:
                    tr["end"] = ts
                    tr["interrupted"] = True
                self.pending.clear()
                return
            prompt = clean_prompt(text)
            if prompt is None:
                return
            self._start_turn(short(prompt, 600), ts, implicit=prompt.startswith("↻ "))
            return
        # assistant
        mid = msg.get("id")
        model = msg.get("model") or ""
        if model and not model.startswith("<"):
            self.model = model
        usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
        if usage and not model.startswith("<"):
            ctx = sum(int(usage.get(k) or 0) for k in
                      ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if ctx:
                self.ctx = ctx
            out = int(usage.get("output_tokens") or 0)
            prev_id, prev_out = self._msg
            if mid != prev_id:
                prev_out = 0
            if out > prev_out:
                self.out_hours[int(ts // 3600)] += out - prev_out
            self._msg = (mid, max(out, prev_out))
        if tr is None or (tr["end"] is not None and (mid is None or mid != tr["end_mid"])):
            self._start_turn("", ts, implicit=True)
            tr = self.turn
        tr["last"] = ts
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text" and (b.get("text") or "").strip():
                tr["text"] = b["text"]
            elif bt == "tool_use":
                name = b.get("name") or "?"
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                self.pending[b.get("id")] = ts
                self.last_tool = {"name": tool_label(name), "detail": tool_detail(inp), "ts": ts}
                tr["tools"] += 1
                if name in EDIT_TOOLS and inp.get("file_path"):
                    tr["files"].add(re.split(r"[\\/]", str(inp["file_path"]))[-1])
                if name in ("Agent", "Task"):
                    tr["agents"] += 1
        if e.get("isApiErrorMessage"):
            tr["error"] = short(tr["text"], 240)
            tr["end"], tr["end_mid"] = ts, mid
            self.last_error = {"ts": ts, "text": tr["error"]}
            return
        stop = msg.get("stop_reason")
        if stop and stop != "tool_use":
            tr["end"], tr["end_mid"], tr["stop"] = ts, mid, stop
            self.pending.clear()

    # -- vystup ----------------------------------------------------------------------
    def project(self) -> str:
        """Priecinok, v ktorom relacia vznikla (cwd sa pocas prace meni, slug priecinka nie)."""
        if self.root is None and self.cwd:
            p = Path(self.cwd)
            for cand in (p, *p.parents):
                if re.sub(r"[^A-Za-z0-9]", "-", str(cand)) == self.slug:
                    self.root = cand
                    break
        root = self.root or (Path(self.cwd) if self.cwd else None)
        if root is None:
            return self.slug
        if root == Path.home():
            return "domovský priečinok"
        return root.name or str(root)

    def status(self, now: float):
        last = max(self.last_ts or 0, self.mtime)
        age = now - last
        tr = self.turn
        if tr is None:
            return "idle", age
        if tr["end"] is None:
            if age < 120:
                return "working", age
            if age < 1200:
                return "quiet", age          # dlhy krok alebo caka na povolenie
            return "stalled", age
        if tr["error"]:
            return "error", age
        return ("done" if now - tr["end"] < 900 else "idle"), age

    def turn_view(self, tr: dict) -> dict:
        dur = tr["dur"] / 1000.0 if tr["dur"] else ((tr["end"] or tr["last"]) - tr["start"])
        return {"sid": self.id, "title": self.display_title(), "project": self.project(),
                "prompt": short(tr["prompt"], 260), "result": plain(tr["text"], 520),
                "start": tr["start"], "end": tr["end"], "dur": round(max(0, dur)),
                "tools": tr["tools"], "errors": tr["errors"], "files": sorted(tr["files"])[:6],
                "nfiles": len(tr["files"]), "agents": tr["agents"], "interrupted": tr["interrupted"],
                "error": tr["error"], "stop": tr["stop"], "extra": tr["extra"]}

    def display_title(self) -> str:
        return short(self.custom_title or self.title or self.last_prompt
                     or (self.turn or {}).get("prompt") or self.id[:8], 80)

    def out_since(self, since: float) -> int:
        h = int(since // 3600)
        return sum(v for k, v in self.out_hours.items() if k >= h)


class Sessions:
    def __init__(self):
        self.items: dict = {}
        self.scan_ts = 0.0
        self.paths: list = []

    def _scan(self, now: float):
        found = []
        try:
            for d in PROJECTS.iterdir():
                if not d.is_dir():
                    continue
                try:
                    for f in d.iterdir():
                        if f.suffix == ".jsonl":
                            try:
                                mt = f.stat().st_mtime
                            except OSError:
                                continue
                            if now - mt < SESSION_WINDOW_S:
                                found.append((mt, f))
                except OSError:
                    continue
        except OSError:
            pass
        found.sort(reverse=True)
        self.paths = [f for _, f in found[:MAX_SESSION_FILES]]
        keep = {str(p) for p in self.paths}
        for k in [k for k in self.items if k not in keep]:
            del self.items[k]

    def poll(self):
        now = time.time()
        if now - self.scan_ts > 10:
            self.scan_ts = now
            self._scan(now)
        for p in self.paths:
            s = self.items.get(str(p))
            if s is None:
                s = self.items[str(p)] = Sess(p)
            s.poll()

    @staticmethod
    def _agents(s: Sess, now: float) -> list:
        out = []
        d = s.path.parent / s.id / "subagents"
        try:
            for f in d.iterdir():
                if f.name.endswith(".jsonl") and now - f.stat().st_mtime < 60:
                    meta = {}
                    try:
                        meta = json.loads((d / (f.stem + ".meta.json")).read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        pass
                    out.append({"type": meta.get("agentType") or "agent",
                                "what": short(meta.get("description") or "", 80)})
        except OSError:
            pass
        return out[:6]

    def snapshot(self, tasks: list) -> dict:
        now = time.time()
        voice = {t.get("session_id"): t for t in tasks if t.get("session_id")}
        midnight = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
        rows, done = [], []
        out_5h = out_day = 0
        for s in list(self.items.values()):
            if s.first_ts is None:
                continue
            out_5h += s.out_since(now - 5 * 3600)
            out_day += s.out_since(midnight)
            status, age = s.status(now)
            vt = voice.get(s.id)
            if vt and vt.get("status") not in ("starting", "running") and status in ("working", "quiet", "stalled"):
                status = "done" if vt.get("status") == "done" else "idle"   # JARVIS ulohu ukoncil alebo zastavil
            tr = s.turn
            for t in list(s.turns) + ([tr] if tr is not None and tr["end"] is not None else []):
                if t["end"] is None or (not t["text"] and not t["tools"] and not t["error"]):
                    continue
                v = s.turn_view(t)
                task = voice.get(s.id)
                if task:
                    v["voice"] = True
                    if task.get("summary"):
                        v["result"] = short(task["summary"], 520)
                done.append(v)
            if status == "idle" and age > 8 * 3600:
                continue
            ctx_pct = None
            try:
                b = json.loads((Path(tempfile.gettempdir()) / f"claude-ctx-{s.id}.json").read_text(encoding="utf-8"))
                if now - float(b.get("timestamp") or 0) < 6 * 3600:
                    ctx_pct = b.get("used_pct")
            except (OSError, ValueError, TypeError):
                pass
            open_turn = tr is not None and tr["end"] is None
            rows.append({
                "id": s.id, "title": s.display_title(), "project": s.project(), "cwd": s.cwd,
                "branch": s.branch if s.branch and s.branch != "HEAD" else "", "model": s.model,
                "entry": s.entry, "mode": s.mode, "status": status, "age": round(age),
                "last": max(s.last_ts or 0, s.mtime), "started": s.first_ts,
                "prompt": short(tr["prompt"], 300) if tr else "", "turn_start": tr["start"] if tr else None,
                "turn_end": tr["end"] if tr else None,
                "turn_tools": tr["tools"] if tr else 0, "turn_errors": tr["errors"] if tr else 0,
                "turn_extra": tr["extra"] if tr else 0,
                "tool": s.last_tool if open_turn else None,
                "pending": len(s.pending) if open_turn else 0,
                "said": plain(tr["text"], 260) if tr else "",
                "error": (tr or {}).get("error") or "",
                "ctx": s.ctx, "ctx_pct": ctx_pct, "recap": s.recap, "prompts": s.prompts,
                "compactions": s.compactions,
                "voice": s.id in voice or s.custom_title.startswith("voice:"),
                "task": (voice.get(s.id) or {}).get("id")
                if (voice.get(s.id) or {}).get("status") in ("starting", "running") else None,
                "agents": self._agents(s, now) if status in ("working", "quiet") else []})
        known = {s.id for s in self.items.values()}
        for t in tasks:
            if t.get("session_id") in known:
                mine = [v for v in done if v["sid"] == t.get("session_id")]
                for v in mine:
                    if t.get("cost_usd"):
                        v["cost"] = t["cost_usd"]
                if mine or t.get("status") in ("starting", "running"):
                    continue        # zastavena uloha bez dokonceneho tahu pokracuje nizsie do zoznamu Dobehlo
            started = float(t.get("started") or now)
            name = "hlasová úloha" + (f" {t.get('id')}" if t.get("id") else "")
            if t.get("status") in ("starting", "running"):
                rows.append({"id": str(t.get("id")), "title": short(t.get("prompt"), 80), "project": t.get("project") or "",
                             "cwd": t.get("path") or "", "branch": "", "model": "", "entry": "", "mode": "",
                             "status": "working", "age": 0, "last": now, "started": started,
                             "prompt": short(t.get("prompt"), 300), "turn_start": started, "turn_end": None,
                             "turn_tools": 0, "turn_errors": 0, "turn_extra": 0,
                             "tool": {"name": "krok", "detail": short(t.get("activity"), 110), "ts": now}
                             if t.get("activity") else None,
                             "pending": 0, "said": "", "error": "", "ctx": 0, "ctx_pct": None, "recap": "",
                             "prompts": 1, "compactions": 0, "voice": True, "task": str(t.get("id")),
                             "agents": []})
            elif t.get("ended"):
                ended = float(t["ended"])
                if now - ended < SESSION_WINDOW_S:
                    bad = t.get("status") == "failed"
                    done.append({"sid": str(t.get("id")), "title": name, "project": t.get("project") or "",
                                 "prompt": short(t.get("prompt"), 260), "result": short(t.get("summary"), 520),
                                 "start": started, "end": ended, "dur": round(max(0, ended - started)),
                                 "tools": 0, "errors": 0, "files": [], "nfiles": 0, "agents": 0,
                                 "interrupted": t.get("status") == "stopped",
                                 "error": short(t.get("summary") or "Úloha zlyhala.", 240) if bad else "",
                                 "title": short(t.get("prompt"), 80) or name,
                                 "stop": t.get("status") or "", "extra": 0, "voice": True,
                                 "cost": t.get("cost_usd")})
        order = {"working": 0, "quiet": 1, "error": 2, "done": 3, "stalled": 4, "idle": 5}
        rows.sort(key=lambda r: (order.get(r["status"], 9), -r["last"]))
        done.sort(key=lambda v: -(v["end"] or 0))
        return {"sessions": rows[:10], "done": done[:24],
                "working": sum(1 for r in rows if r["status"] in ("working", "quiet")),
                "tokens": {"out_5h": out_5h, "out_today": out_day},
                "done_today": sum(1 for v in done if (v["end"] or 0) >= midnight)}


# ---------------------------------------------------------------------------------------
# Limity planu a hlasove ulohy
# ---------------------------------------------------------------------------------------
def _reset_epoch(v):
    if isinstance(v, (int, float)):
        return float(v) / (1000.0 if v > 1e11 else 1.0)
    return iso_ts(v) if isinstance(v, str) else None


def read_limits() -> dict:
    """Najnovsie znamy stav limitov: zo statusline alebo z rate_limit_event hlasovych uloh."""
    best = None
    try:
        d = json.loads(LIMITS_FILE.read_text(encoding="utf-8"))
        win = {}
        for name, w in (d.get("rate_limits") or {}).items():
            if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
                win[name] = {"pct": float(w["used_percentage"]), "resets": _reset_epoch(w.get("resets_at"))}
        if win:
            best = {"ts": float(d.get("ts") or LIMITS_FILE.stat().st_mtime), "source": "Claude Code",
                    "windows": win, "model": d.get("model") or ""}
    except (OSError, ValueError, TypeError):
        pass
    try:
        logs = sorted(LOG_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:3]
    except OSError:
        logs = []
    for f in logs:
        try:
            st = f.stat()
            if best and st.st_mtime <= best["ts"]:
                break
            with open(f, "rb") as fh:
                fh.seek(max(0, st.st_size - 200_000))
                lines = fh.read().split(b"\n")
        except OSError:
            continue
        found = None
        for raw in reversed(lines):
            if b"rate_limit_event" not in raw:
                continue
            try:
                info = json.loads(raw).get("rate_limit_info") or {}
            except ValueError:
                continue
            win = {}
            for name, w in (info.get("unifiedWindows") or {}).items():
                if isinstance(w, dict) and isinstance(w.get("utilization"), (int, float)):
                    win[name] = {"pct": float(w["utilization"]) * 100.0, "resets": _reset_epoch(w.get("resetsAt"))}
            if win:
                found = {"ts": st.st_mtime, "source": "hlasová úloha", "windows": win,
                         "status": info.get("status") or ""}
                break
        if found:
            best = found
            break
    return best or {}


def read_tasks() -> list:
    try:
        data = json.loads(TASKS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for t in data if isinstance(data, list) else []:
        if isinstance(t, dict):
            out.append({k: t.get(k) for k in ("id", "project", "path", "prompt", "status", "session_id",
                                              "started", "ended", "activity", "summary", "cost_usd")})
    return out[-30:]


# ---------------------------------------------------------------------------------------
# Zber a HTTP
# ---------------------------------------------------------------------------------------
class Hub:
    def __init__(self):
        self.system = System()
        self.log = JarvisLog()
        self.conv = Conversation()
        self.sessions = Sessions()
        self.limits: dict = {}
        self.tasks: list = []
        self.payload = b"{}"
        self.boot = time.time()
        self.last_client = 0.0
        self.tick = 0

    def step(self):
        self.tick += 1
        self.system.sample()
        self.log.poll()
        if self.tick % 2 == 1:
            self.sessions.poll()
        if self.tick % 3 == 1:
            self.conv.poll()
            self.tasks = read_tasks()
            self.limits = read_limits() or self.limits
        running = self.system.jarvis.get("running", False)
        snap = {"now": time.time(), "boot": self.boot, "ui": ui_version(), "system": self.system.data, "proc": self.system.jarvis,
                "jarvis": self.log.snapshot(running), "conversation": self.conv.rows,
                "turns_today": self.conv.today, "limits": self.limits, "tasks": self.tasks,
                "cleared": dict(CLEARED)}
        snap.update(self.sessions.snapshot(self.tasks))
        # pre zivu ikonu okna (ikona.py): stav a ci sa prave pracuje
        self.icon = (snap["jarvis"].get("state") or "idle", bool(snap.get("working") or snap["jarvis"].get("tasks_running")))
        self.payload = json.dumps(snap, ensure_ascii=False, default=str).encode("utf-8")

    def run(self):
        while True:
            t0 = time.time()
            try:
                self.step()
            except Exception:                                    # noqa: BLE001
                own_log("step: " + traceback.format_exc())
            # JARVIS je vypnuty a nikto sa nepozera: skonci, nech nic nevisi na pozadi.
            now = time.time()
            if (not self.system.jarvis.get("running") and now - self.boot > 240
                    and now - max(self.last_client, self.boot) > 120):
                own_log("JARVIS nebezi a okno je zavrete: koncim")
                os._exit(0)
            time.sleep(max(0.05, 1.0 - (time.time() - t0)))


HUB: Hub | None = None
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}


CLEARED_FILE = HERE / "vycistene.json"
CLEAR_KEYS = ("conv", "done", "log")


def read_cleared() -> dict:
    """Od kedy ma ktory panel ukazovat zaznamy (cas vycistenia). Subory JARVISa sa nemenia."""
    try:
        d = json.loads(CLEARED_FILE.read_text(encoding="utf-8"))
        return {k: float(d.get(k) or 0) for k in CLEAR_KEYS}
    except (OSError, ValueError, TypeError, AttributeError):
        return {k: 0.0 for k in CLEAR_KEYS}


CLEARED = read_cleared()


def set_cleared(what: str, restore: bool) -> dict:
    now = 0.0 if restore else time.time()
    for k in (CLEAR_KEYS if what == "all" else (what,)):
        CLEARED[k] = now
    try:
        CLEARED_FILE.write_text(json.dumps(CLEARED), encoding="utf-8")
    except OSError:
        pass
    return dict(CLEARED)


STATIC_FILES = {"/jadro.mp4": "video/mp4", "/jadro.png": "image/png"}      # jadro: video slucka a jej prvy zaber


def ui_version() -> int:
    """Cas poslednej zmeny stranky: otvorene okno sa po zmene samo nacita znova."""
    try:
        return int((HERE / "index.html").stat().st_mtime)
    except OSError:
        return 0


def poke_jarvis(msg: str):
    """Posle spravu beziacemu JARVISovi jeho kanalom pre druhu instanciu (pomenovana rura).
    Jedina vec, ktorou dashboard do JARVISa zasahuje: zastavenie hlasovej ulohy."""
    key = "hey-claude-" + hashlib.sha1(str(JARVIS.resolve()).lower().encode("utf-8")).hexdigest()[:12]
    try:
        with open("//./pipe/" + key, "wb", buffering=0) as f:
            f.write((msg + chr(10)).encode("utf-8"))
        return True, ""
    except OSError as e:
        return False, str(e)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):                                # pythonw nema stderr
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, fp: Path, ctype: str):
        """Staticky subor jadra, aj po castiach (Range), aby sa video dalo prehravat v slucke."""
        try:
            size = fp.stat().st_size
        except OSError:
            self._send(404, b"not found", "text/plain")
            return
        start, end, code = 0, size - 1, 200
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(fp, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(262144, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_POST(self):                                           # noqa: N802
        # akcie: zastavit hlasovu ulohu, vycistit panel. Len z vlastnej stranky (hlavicka X-Jarvis + Origin).
        origin = self.headers.get("Origin", "")
        if (self.headers.get("Host", "") not in ALLOWED_HOSTS or self.headers.get("X-Jarvis") != "1"
                or (origin and origin not in ALLOWED_ORIGINS)):
            self._send(403, b"forbidden", "text/plain")
            return
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 1000)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
                data = data if isinstance(data, dict) else {}
            except ValueError:
                data = {}
            path = self.path.split("?", 1)[0]
            if path == "/api/clear":
                what = str(data.get("what") or "")
                if what not in CLEAR_KEYS + ("all",):
                    self._send(400, b"bad request", "text/plain")
                    return
                body = json.dumps({"ok": True, "cleared": set_cleared(what, bool(data.get("restore")))}).encode()
                self._send(200, body, "application/json")
                return
            tid = str(data.get("id") or "")
            if path != "/api/stop" or not re.fullmatch("all|[0-9a-f-]{6,40}", tid):
                self._send(400, b"bad request", "text/plain")
                return
            ok, err = poke_jarvis("stop-task " + tid)
            body = json.dumps({"ok": ok, "error": err}).encode()
            self._send(200 if ok else 502, body, "application/json")
        except (ConnectionError, OSError):
            pass

    def do_GET(self):                                            # noqa: N802
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:    # len lokalne, ziadny DNS rebinding
            self._send(403, b"forbidden", "text/plain")
            return
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/state":
                HUB.last_client = time.time()
                self._send(200, HUB.payload, "application/json; charset=utf-8")
            elif path == "/api/ping":
                body = json.dumps({"app": "jarvis-dashboard",
                                   "clients": time.time() - HUB.last_client < 6}).encode()
                self._send(200, body, "application/json")
            elif path in STATIC_FILES:
                self._send_file(HERE / path[1:], STATIC_FILES[path])
            elif path in ("/", "/index.html"):
                self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")
        except (ConnectionError, OSError):
            pass


def open_window():
    url = f"http://127.0.0.1:{PORT}/"
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    local = os.environ.get("LOCALAPPDATA", "")
    for exe in (Path(pf86) / "Microsoft/Edge/Application/msedge.exe",
                Path(pf) / "Microsoft/Edge/Application/msedge.exe",
                Path(pf) / "Google/Chrome/Application/chrome.exe",
                Path(local) / "Google/Chrome/Application/chrome.exe"):
        if exe.is_file():
            try:
                subprocess.Popen([str(exe), f"--app={url}", "--window-size=1760,1010"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)
                return
            except OSError as e:
                own_log(f"okno: {e}")
    import webbrowser
    webbrowser.open(url)


def already_running():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ping", timeout=1.5) as r:
            d = json.loads(r.read().decode())
            return d if d.get("app") == "jarvis-dashboard" else None
    except Exception:                                            # noqa: BLE001
        return None


def main():
    global HUB
    want_window = "--no-open" not in sys.argv
    other = already_running()
    if other is not None:
        if want_window and not other.get("clients"):
            open_window()
        return
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        own_log(f"port {PORT} je obsadeny: {e}")
        return
    httpd.daemon_threads = True
    HUB = Hub()
    try:
        HUB.step()
    except Exception:                                            # noqa: BLE001
        own_log("prvy krok: " + traceback.format_exc())
    threading.Thread(target=HUB.run, daemon=True, name="hub").start()
    try:                                                         # ziva ikona okna na paneli uloh; bez nej dashboard bezi dalej
        import ikona
        ikona.start(lambda: getattr(HUB, "icon", ("idle", False)), own_log)
    except Exception as e:                                       # noqa: BLE001
        own_log(f"ikona: {e!r}")
    own_log(f"server bezi na http://127.0.0.1:{PORT}/")
    if want_window:
        open_window()
    httpd.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except Exception:                                            # noqa: BLE001
        own_log("main: " + traceback.format_exc())

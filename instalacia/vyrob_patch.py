"""Vyrobi jarvis-ulohy-do-prace.patch zo ziveho kodu v hey-claude.

Len pre spravcu repozitara, pri instalacii sa nepouziva. Patch obsahuje iba zmenene riadky:
ziadny okolity kod autora hey-claude a ziadne nazvy jeho funkcii v hlavickach.

    hey-claude\\.venv\\Scripts\\python.exe instalacia\\vyrob_patch.py
"""
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REPO = BASE / "hey-claude"
PATCH = BASE / "jarvis-ulohy-do-prace.patch"

raw = subprocess.run(["git", "-C", str(REPO), "diff", "-U0"], capture_output=True, check=True).stdout
text = re.sub(rb"(?m)^(@@ [^@\n]* @@).*$", rb"\1", raw)
if not text.strip():
    sys.exit("V hey-claude nie su ziadne zmeny, patch by bol prazdny. Nic som neprepisal.")
PATCH.write_bytes(text)
ok = subprocess.run(["git", "-C", str(REPO), "apply", "--unidiff-zero", "--reverse", "--check", str(PATCH)]).returncode == 0
plus = sum(1 for l in text.splitlines() if l.startswith(b"+") and not l.startswith(b"+++"))
minus = sum(1 for l in text.splitlines() if l.startswith(b"-") and not l.startswith(b"---"))
print(f"patch: {plus} nasich riadkov, {minus} povodnych riadkov, ktore nahradzame")
print("sedi so zivym kodom" if ok else "POZOR: patch nesedi so zivym kodom")
sys.exit(0 if ok else 1)

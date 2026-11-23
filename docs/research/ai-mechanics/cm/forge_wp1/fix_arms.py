"""AI FORGE WP1: the runner's arms under names free on the stand (FO was taken), a dry check of the arm on rabota before the ledger, the failed start of P1 out of the ledger with a note."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
F = Path(__file__).parent
p = F / "AIForgeReplayRunner.py"
s = p.read_text(encoding="utf-8")
for a, b in (('("FS", "L8"', '("FGS", "L8"'), ('("FO", "M3"', '("FGO", "M3"'), ('("FS", "M3"', '("FGS", "M3"'), ('("FR", "M3"', '("FGR", "M3"'),
             ('("FO", "L8"', '("FGO", "L8"'), ('("FT", "L8"', '("FGT", "L8"')):
    assert a in s, a
    s = s.replace(a, b)
old = '''FO - off; FS, FR - shadow, replay; FT - replay to event N (forge_stop.txt) and stop
        "FO": ("env_FG.txt", [], COMMON_D0), "FS": ("env_FG.txt", ["OXCE_AI_FORGE=1"], COMMON_D0), "FR": ("env_FG.txt", ["OXCE_AI_FORGE=1"], COMMON_D0),
        "FT": ("env_FG.txt", '''
new = '''FGO - off; FGS, FGR - shadow, replay; FGT - replay to event N (forge_stop.txt) and stop
        "FGO": ("env_FG.txt", [], COMMON_D0), "FGS": ("env_FG.txt", ["OXCE_AI_FORGE=1"], COMMON_D0), "FGR": ("env_FG.txt", ["OXCE_AI_FORGE=1"], COMMON_D0),
        "FGT": ("env_FG.txt", '''
assert old in s
s = s.replace(old, new)
s = s.replace("""if '"FO"' not in run:""", """if '"FGO"' not in run:""")
s = s.replace('''if arm == "FT":''', '''if arm == "FGT":''')
s = s.replace('''raise SystemExit("FT needs --stop N")''', '''raise SystemExit("FGT needs --stop N")''')
old = '''    st = ps("(Get-ScheduledTask oxce_cmrun).State").strip()
    if st == "Running":
        raise SystemExit("the task is running")
    with open(LEDGER'''
new = '''    st = ps("(Get-ScheduledTask oxce_cmrun).State").strip()
    if st == "Running":
        raise SystemExit("the task is running")
    # no battle starts here: an unknown scenario stops run_cm after the arm has been accepted
    dry = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, f"cd /d {R} && C:\\\\OXCE_AIWorker\\\\python\\\\python.exe -u run_cm.py --arms {arm} --pairs ZZ:1 --prefix dry"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    if "unknown scenario" not in dry:
        raise SystemExit(f"arm {arm} is not accepted on rabota: {dry[-300:]}")
    with open(LEDGER'''
assert old in s
s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
led = F / "ledger.tsv"
lines = led.read_text(encoding="utf-8").splitlines()
assert len(lines) == 1 and lines[0].startswith("P1\t")
(F / "ledger_notes.txt").write_text("14:46 P1, first try: not a battle. Arm FO was taken by an old series on the stand, the arms patch skipped itself, run_cm refused --arms FS, the task ended with code 1. No game process, no log, no work folder. Taken off the ledger; names changed to FGO, FGS, FGR, FGT.\n", encoding="utf-8")
led.unlink()
print("ok")

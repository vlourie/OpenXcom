"""Stage 0B: one run (GO Vitali 27.10, AI BASELINE ALIGNMENT). Started by b0run.py with the run's environment.

  b0one.py fx <name> <id> <seed> <mission> <race> <campaign> <turn>   - fixture: bot battle, saved at player turn <turn>
  b0one.py harness <name> <fixture>                                   - DEV stand: one AI turn (ai_probe.run), after.sav
  b0one.py release <name> <fixture> [key=value ...]                   - player exe: HdControl ends the turn, autosave
  b0one.py u0 <name> <fixture>                                        - v8.7.1 + driver (OXCE_U0_SAVE): end turn, save

Output: OUT/<name>/ (after.sav or fixture.sav, openxcom.log, run.txt). The game runs on the hidden desktop with SDL dummy
drivers, below normal priority (ai_probe.Hidden)."""
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "stand"))
import ai_probe

OUT = HERE / "out"


def fresh(name):
    """The run's output folder, emptied: only this attempt's files end up there."""
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for f in d.iterdir():
        if f.is_file():
            f.unlink()
    return d


def note(d, text):
    with open(d / "run.txt", "a", encoding="utf-8") as f:
        f.write(text + "\n")


def keep(d, *files):
    for f in files:
        if f and Path(f).is_file():
            shutil.copyfile(f, d / Path(f).name)


def fx(name, sid, seed, mission, race, campaign, turn):
    d = fresh(name)
    os.environ["OXCE_AI_FIXTURE_TURN"] = turn
    os.environ["OXCE_AI_RACE"] = race
    r = ai_probe.run(None, 60, save_as="fixture.sav", name=name, timeout=3600, bot=True, seed=int(seed),
                     campaign=str(HERE / "saves" / campaign), mission=mission, squad=8)
    keep(d, r.saved, r.log)
    res = r.tagged("[AIRESULT]")
    note(d, f"fx {sid} seed={seed} mission={mission} race={race} campaign={campaign} turn={turn} saved={bool(r.saved)} "
            f"seconds={r.seconds:.0f} result={res[0] if res else '-'}")
    return 0 if r.saved else 3


def harness(name, fixture):
    d = fresh(name)
    # OXCE_AI_AUTOSAVE=1 (exe AL): the player's turn autosave as well - the snapshot the player exe writes
    auto = ai_probe.WORK / name / "piratez" / "_autobattle_.asav"
    if auto.exists():
        auto.unlink()
    r = ai_probe.run(Path(fixture), 1, save_as="after.sav", name=name, timeout=1800)
    keep(d, r.saved, r.log)
    if auto.is_file():
        shutil.copyfile(auto, d / "auto.sav")
    note(d, f"harness fixture={fixture} saved={bool(r.saved)} auto={auto.is_file()} finished={r.finished} seconds={r.seconds:.0f}")
    return 0 if r.saved else 3


def options(work, extra):
    """options.cfg of the stand (ai_probe.prepare_user) with the autosave every turn and the run's own keys."""
    cfg = work / "options.cfg"
    t = cfg.read_text(encoding="utf-8")
    keys = {"autosave": "true", "autosaveFrequency": "1", "autosaveSlots": "1", "skipNextTurnScreen": "true"}
    keys.update(extra)
    added = []
    for k, v in keys.items():
        t, n = re.subn(rf"(?m)^(\s*){k}: .*$", rf"\g<1>{k}: {v}", t)
        if not n:
            added.append(f"  {k}: {v}")
    if added:
        t = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), t, count=1)
    cfg.write_bytes(t.encode("utf-8"))


def launch(name, fixture, extra, env_add):
    work = ai_probe.WORK / name
    if work.exists():
        for f in ("openxcom.log",):
            if (work / f).exists():
                (work / f).unlink()
        pz = work / "piratez"
        if pz.exists():
            for f in pz.iterdir():
                if f.is_file():
                    f.unlink()
    ai_probe.prepare_user(work)
    options(work, extra)
    shutil.copyfile(fixture, work / "piratez" / "fixture.sav")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OXCE_HD_", "OXCE_AI_", "OXCE_U0_"))}
    if os.environ.get("OXCE_AI_DLL"):
        env["PATH"] = os.environ["OXCE_AI_DLL"] + os.pathsep + env.get("PATH", "")
    env["SDL_AUDIODRIVER"] = "dummy"
    env["SDL_VIDEODRIVER"] = "dummy"
    env.update(env_add)
    args = [str(ai_probe.EXE), "-data", str(ai_probe.GAME), "-user", str(work), "-load", "fixture.sav", "-cfg", str(work),
            "-fullscreen", "false", "-borderless", "false", "-displayWidth", "1280", "-displayHeight", "720",
            "-soundVolume", "0", "-musicVolume", "0", "-uiVolume", "0"]
    return work, ai_probe.Hidden(args, str(ai_probe.EXE.parent), env)


def kill(p):
    if p.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        p.wait()


class Ctl:
    def __init__(self, d, p):
        self.d, self.p, self.n = d, p, 0

    def send(self, lines, timeout):
        self.n += 1
        tmp = self.d / "cmd.tmp"
        tmp.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        os.replace(tmp, self.d / "cmd.txt")
        done = self.d / f"done.{self.n}"
        t0 = time.time()
        while True:
            if done.exists():
                try:
                    text = done.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    text = []
                if text and text[-1] == "end":
                    return text[:-1]
            if self.p.poll() is not None:
                raise RuntimeError(f"game exited {self.p.returncode} during {lines}")
            if time.time() - t0 > timeout:
                raise TimeoutError(f"no answer to {lines} in {timeout} s")
            ai_probe.hide_windows(self.p.pid)
            time.sleep(0.1)


def release(name, fixture, kv):
    d = fresh(name)
    extra = dict(x.split("=", 1) for x in kv)
    ctl_dir = ai_probe.WORK / name / "ctl"
    if ctl_dir.exists():
        shutil.rmtree(ctl_dir)
    ctl_dir.mkdir(parents=True)
    work, p = launch(name, fixture, extra, {"OXCE_HD_CONTROL": str(ctl_dir)})
    auto = work / "piratez" / "_autobattle_.asav"
    t0 = time.time()
    code = 3
    try:
        c = Ctl(ctl_dir, p)
        r = c.send(["waitstate BattlescapeState 300000"], 330)
        note(d, f"loaded {r} {time.time() - t0:.0f}s")
        r = c.send(["wait 1500", "state"], 60)
        note(d, f"before {r}")
        m = re.search(r"side=player turn=(\d+)", " ".join(r))
        if not m:
            raise RuntimeError(f"not the player's turn: {r}")
        turn = int(m.group(1))
        c.send(["key 8"], 60)
        note(d, f"end turn {turn} sent {time.time() - t0:.0f}s")
        last, seen = "", 0
        while True:
            r = c.send(["wait 700", "state"], 120)
            line = " ".join(r)
            if f"side=player turn={turn + 1}" in line and "state BattlescapeState" in line and auto.is_file():
                note(d, f"after {r} {time.time() - t0:.0f}s")
                break
            m = re.search(r"state (\S+)", line)
            top = m.group(1) if m else ""
            seen = seen + 1 if top == last else 1
            if top != last:
                note(d, f"top {line} {time.time() - t0:.0f}s")
                last = top
            # the player's OK on a message of the enemy turn ("has panicked", "lost consciousness"): the stand closes them
            # itself (AiProbe::autoClose); the next turn screen with a message waits for a key the same way
            if top == "InfoboxOKState" or (top == "NextTurnState" and seen >= 3):
                c.send(["key 13"], 60)
                note(d, f"ok pressed on {top}")
                last, seen = "", 0
            if time.time() - t0 > 2400:
                raise TimeoutError(f"no player turn {turn + 1}: {line}")
        keep(d, auto)
        if (d / auto.name).is_file():
            os.replace(d / auto.name, d / "auto.sav")
            code = 0
        try:
            c.send(["quit"], 30)
        except Exception:
            pass
        for _ in range(100):
            if p.poll() is not None:
                break
            time.sleep(0.1)
    except Exception as e:
        note(d, f"error {e}")
    finally:
        kill(p)
    keep(d, work / "openxcom.log")
    note(d, f"release fixture={fixture} extra={extra} code={code} seconds={time.time() - t0:.0f}")
    return code


def u0(name, fixture):
    d = fresh(name)
    work, p = launch(name, fixture, {}, {"OXCE_U0_SAVE": "after.sav"})
    t0 = time.time()
    while p.poll() is None and time.time() - t0 < 2400:
        ai_probe.hide_windows(p.pid)
        time.sleep(0.3)
    kill(p)
    keep(d, work / "piratez" / "after.sav", work / "openxcom.log")
    if (work / "piratez" / "_autobattle_.asav").is_file():
        shutil.copyfile(work / "piratez" / "_autobattle_.asav", d / "auto.sav")
    code = 0 if (d / "after.sav").is_file() and (d / "auto.sav").is_file() else 3
    note(d, f"u0 fixture={fixture} code={code} seconds={time.time() - t0:.0f}")
    return code


def main():
    kind, name = sys.argv[1], sys.argv[2]
    if kind == "fx":
        return fx(name, *sys.argv[3:9])
    if kind == "harness":
        return harness(name, sys.argv[3])
    if kind == "release":
        return release(name, sys.argv[3], sys.argv[4:])
    if kind == "u0":
        return u0(name, sys.argv[3])
    raise SystemExit(f"unknown kind {kind}")


if __name__ == "__main__":
    sys.exit(main())

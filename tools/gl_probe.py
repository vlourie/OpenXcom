# Замер ЦП процесса с OpenGL и без (docs/research/gpu-render-plan-2026-10-27.md, п. 2).
#   py -3.13 tools/gl_probe.py gl0 gl1 gl1nv gl0fps30
# Геоскейп с сейва на скрытом рабочем столе, видео windib (не dummy: с ним OpenGL не поднимается).
# Меряет ЦП процесса (ядер в среднем) за окно и грузится ли ICD видеокарты (nvoglv64 / atio / ig*icd).
# Строка лога HD frame - обороты цикла, а не нарисованные кадры (R-513).
import re, sys, tempfile, time, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import psutil, ai_probe, hidden_game
from hidden_game import EXE, unthrottle
hidden_game.utf8_streams()

LOAD, WINDOW = 100, 30
runs = sys.argv[1:] or ["gl0", "gl1"]
CASES = {
    "gl0": "useOpenGL=false",
    "gl1": "useOpenGL=true;vSyncForOpenGL=true",
    "gl1nv": "useOpenGL=true;vSyncForOpenGL=false",
    "gl0fps30": "useOpenGL=false;FPS=30;FPSInactive=30",
    "gpu": "useOpenGL=false;oxceHdGpu=true;vSyncForOpenGL=true",     # этап 0: вывод мира через FBO (HdGpu)
    "gpunv": "useOpenGL=false;oxceHdGpu=true;vSyncForOpenGL=false",
    "thr4": "useOpenGL=false;oxceHdThreads=4",       # сколько стоит будить 22 потока рендера на каждый кусок кадра
    "thr2": "useOpenGL=false;oxceHdThreads=2",
    "thr1": "useOpenGL=false;oxceHdThreads=1",
}
for name in runs:
    u = Path(tempfile.gettempdir()) / f"oxce_gl_probe_{name}"
    hidden_game.prepare_user(u, "", CASES[name], "", "NoCodexCatZ.sav", "")
    env = hidden_game.game_env(gl=True)
    args = hidden_game.game_args(EXE, u, load=True)
    if "FPSInactive=30" in CASES[name]:
        args[args.index("-FPSInactive") + 1] = "30"
    p = hidden_game.launch(EXE, args, env)
    print(name, "pid", p.pid, "троттлинг:", unthrottle(p.pid), flush=True)
    t0 = time.time()
    while time.time() - t0 < LOAD and p.poll() is None:
        ai_probe.hide_windows(p.pid); time.sleep(0.5)
    if p.poll() is not None:
        print(name, "вышла раньше, код", p.returncode); continue
    pr = psutil.Process(p.pid)
    c0 = sum(pr.cpu_times()[:2]); w0 = time.time()
    while time.time() - w0 < WINDOW:
        ai_probe.hide_windows(p.pid); time.sleep(0.5)
    c1 = sum(pr.cpu_times()[:2]); w1 = time.time()
    dlls = sorted({Path(m.path).name.lower() for m in pr.memory_maps() if re.search(r"(nvogl|opengl32|atio|ig[0-9a-z]*icd)", m.path, re.I)})
    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    time.sleep(1)
    log = (u / "openxcom.log").read_text(encoding="utf-8", errors="replace").splitlines()
    loops = [int(m.group(1)) for l in log if (m := re.search(r"HD frame: (\d+) fr", l))][-10:]
    print(f"{name}: ЦП {(c1-c0)/(w1-w0):.2f} ядра, оборотов цикла/с ~{sum(loops) / (2 * len(loops)) if loops else 0:.0f}, GL-модули {dlls}")
    for l in log:
        if re.search(r"HD setup|HD render:|HD GPU|OpenGL|shader|\[FATAL\]", l):
            print("   ", l[:200])
    print(flush=True)

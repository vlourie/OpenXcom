"""Проверка списка tools/gpu_scripts.txt по КЛАССАМ скриптов (Pipeline v2, P1-B).

Список читают gpu-guard (не даёт запустить мимо очереди) и gpuq.py (видит чужой запуск). Скрипт,
которого в списке нет, запускается мимо очереди и делит карту с идущим заданием (R-073). Формат списка
прежний - имя на строку, классы считает эта проверка.

Классы:
  GPU_MODEL_SCRIPT - запускаемый (питон с __main__, .sh/.ps1/.cmd), и по графу вызовов доходит до загрузки
                     модели: from_pretrained / from_single_file / build_pipe-подобное через цепочку модулей
                     (obj_series -> probe_object -> gen_fire -> gen_hd.Qwen21Painter -> from_pretrained),
                     запрос к Ollama с промптом, torch.load, .cuda(), accelerate; или запускает другой
                     GPU_MODEL_SCRIPT (subprocess, .sh, .ps1). Обязан быть в списке;
  CPU_SCRIPT       - запускаемый, до загрузки модели не доходит (выгрузка Ollama с keep_alive 0 - не
                     загрузка). В списке - ошибка: останавливает безобидную работу;
  UTILITY          - библиотека без __main__ и тесты test_*: сами не запускаются. В списке - ошибка;
  LEGACY           - лежит в attic: не проверяется, в списке может быть (запустить его всё ещё можно).
Имя из списка, которого нет в дереве, законно только как внешняя программа, которую запускает наш
GPU_MODEL_SCRIPT (train.py DiffSynth из train_lora.ps1). Исключений по именам файлов нет.

Запуск: python tools/test_gpu_scripts.py [--show]   (код 0 - всё верно; --show - классы всех скриптов)
"""
import ast
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
LIST = os.path.join(ROOT, "tools", "gpu_scripts.txt")
WHERE = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "art", "maps", "paint")]

# загрузка весов в коде питона
LOAD = re.compile(r"\.from_pretrained\s*\(|\.from_single_file\s*\(|\btorch\.load\s*\(|\.cuda\s*\(\s*\)|"
                  r"\.to\(\s*[\"']cuda|\bStableAudioModel\s*\(|\bsnapshot_download\s*\(|\btorch\.cuda\.")
OLLAMA = re.compile(r"/api/(generate|chat)")
OLLAMA_WORK = re.compile(r"[\"'](prompt|messages|images)[\"']|\bprompt\s*=")
# загрузка в шелле: запуск тренера (accelerate launch, в том числе через переменную), ollama run;
# pip install accelerate - не загрузка
SHELL_LOAD = re.compile(r"(?i)accelerate\.exe|\baccelerate\s+launch\b|\bollama\s+run\b")
# строка шелла, которая модель не грузит: сообщение человеку или ключ без модели (как в gpu-guard)
SHELL_QUIET = re.compile(r"(?i)^\s*(write-host|echo|printf|#|::|rem\s)|(\s|^)(--help|-h|--dry-run|-DryRun|"
                         r"--download-only|--check)(\s|$)|gpuq")
LAUNCHERS = {"run", "Popen", "call", "check_call", "check_output", "system", "spawnv", "execv"}


def read(path):
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def files():
    for top in WHERE:
        for dirpath, dirnames, names in os.walk(top):
            dirnames[:] = [d for d in dirnames if not d.startswith(".venv") and d != "__pycache__"]
            for n in names:
                if n.endswith((".py", ".sh", ".ps1", ".cmd")):
                    yield n, os.path.join(dirpath, n)


def seeds(src):
    """Грузит ли сам этот кусок кода модель (без учёта вызовов)."""
    if LOAD.search(src):
        return True
    # запрос к Ollama: с промптом - работа модели, с одним keep_alive - выгрузка (диспетчер очереди)
    return bool(OLLAMA.search(src) and OLLAMA_WORK.search(src))


class Module:
    """Единицы модуля: функции и классы верхнего уровня и <module> (остальной код, включая __main__)."""

    def __init__(self, name, path, text):
        self.name, self.path, self.text = name, path, text
        self.units = {}          # имя -> (исходник, [ast-узлы])
        self.aliases = {}        # имя в модуле -> модуль (import m as a)
        self.names = {}          # имя в модуле -> (модуль, имя) (from m import f)
        self.main = "__main__" in text and re.search(r"__name__\s*==\s*[\"']__main__", text) is not None
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        self.tree = tree
        if tree is None:
            self.units["<module>"] = (text, [])
            return
        top = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.units[node.name] = (ast.get_source_segment(text, node) or "", [node])
            else:
                top.append(node)
        self.units["<module>"] = ("\n".join(ast.get_source_segment(text, n) or "" for n in top), top)
        for node in ast.walk(tree):          # импорты где угодно, в том числе внутри функций
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.aliases[a.asname or a.name.split(".")[0]] = a.name.split(".")[-1] if a.asname else a.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    self.names[a.asname or a.name] = (node.module.split(".")[-1], a.name)

    def calls(self, unit):
        """Куда ведут вызовы единицы: (модуль, единица)."""
        out = set()
        for root in self.units[unit][1]:
            for node in ast.walk(root):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                if isinstance(f, ast.Name):
                    if f.id in self.units:
                        out.add((self.name, f.id))
                    elif f.id in self.names:
                        out.add(self.names[f.id])
                elif isinstance(f, ast.Attribute):
                    chain = []
                    v = f
                    while isinstance(v, ast.Attribute):
                        chain.insert(0, v.attr)
                        v = v.value
                    if isinstance(v, ast.Name):
                        t = self.resolve([v.id] + chain)
                        if t:
                            out.add(t)
        return out

    def resolve(self, chain):
        """a.b.c -> (модуль, единица): a - модуль этого файла, b - модуль, импортированный в a, и т.д.
        (po.gen_hd.Qwen21Painter -> gen_hd.Qwen21Painter; m.Class.method -> m.Class)."""
        head = chain[0]
        mod = self.aliases.get(head) or (self.names[head][1] if head in self.names else None)
        if head in self.units:                    # Class.method(...) своего модуля
            return self.name, head
        if not mod:
            return None
        rest = chain[1:]
        while rest:
            m = MODS.get(mod)
            if m is None:
                return None
            if rest[0] in m.units:
                return mod, rest[0]
            nxt = m.aliases.get(rest[0]) or (m.names[rest[0]][1] if rest[0] in m.names else None)
            if not nxt:
                return None
            mod, rest = nxt, rest[1:]
        return None

    def launches(self):
        """Строки в вызовах запуска (subprocess.run, Popen, os.system): что этот питон запускает сам.
        Постановка в очередь (в вызове есть gpuq) - не запуск. Запускатель, переданный параметром
        (def run(..., spawn=subprocess.call) - подмена в тестах), тоже запуск; команда у него собрана из
        данных, поэтому что он запускает - строки всего модуля (acceptance_run: MODEL_SCRIPTS)."""
        out = []
        if self.tree is None:
            return out
        injected = set()
        for fn in ast.walk(self.tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = fn.args
                pairs = list(zip(a.args[len(a.args) - len(a.defaults):], a.defaults)) + list(zip(a.kwonlyargs, a.kw_defaults))
                for arg, d in pairs:
                    dn = d.attr if isinstance(d, ast.Attribute) else d.id if isinstance(d, ast.Name) else ""
                    if dn in LAUNCHERS:
                        injected.add(arg.arg)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
                if name in injected and isinstance(f, ast.Name):
                    strs = [c.value for c in ast.walk(self.tree) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
                    out += [s for s in strs if "gpuq" not in s]
                    continue
                if name not in LAUNCHERS:
                    continue
                strs = [c.value for c in ast.walk(node) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
                if not any("gpuq" in s for s in strs):
                    out += strs
        return out


MODS = {}


def classify():
    found = {}
    for n, p in files():
        found.setdefault(n, p)
    MODS.clear()
    MODS.update({os.path.splitext(n)[0]: Module(os.path.splitext(n)[0], p, read(p))
                 for n, p in found.items() if n.endswith(".py")})
    mods = MODS
    loads = {(m.name, u) for m in mods.values() for u, (src, _n) in m.units.items() if seeds(src)}
    edges = {(m.name, u): m.calls(u) for m in mods.values() for u in m.units}
    changed = True
    while changed:                                   # до неподвижной точки: кто зовёт загрузчика, тот грузит
        changed = False
        for k, cs in edges.items():
            if k not in loads and cs & loads:
                loads.add(k)
                changed = True
    cls, why = {}, {}

    def legacy(p):
        return "attic" in os.path.relpath(p, ROOT).replace("\\", "/").split("/")

    for n, p in found.items():
        base = os.path.splitext(n)[0]
        if legacy(p):
            cls[n] = "LEGACY"
        elif n.endswith(".py"):
            # код верхнего уровня (с блоком __main__) доходит до загрузки - запуск файла грузит модель
            top = (base, "<module>") in loads
            if n.startswith("test_") or (not mods[base].main and not top):
                cls[n] = "UTILITY"
            elif top:
                cls[n], why[n] = "GPU_MODEL_SCRIPT", "загрузка модели по графу вызовов"
            else:
                cls[n] = "CPU_SCRIPT"
        else:
            cls[n] = "CPU_SCRIPT"
            if SHELL_LOAD.search(read(p)):
                cls[n], why[n] = "GPU_MODEL_SCRIPT", "запускает тренер или ollama"
    # запускатели: питон через subprocess, .sh/.ps1/.cmd - по имени запускаемого GPU-скрипта
    changed = True
    while changed:
        changed = False
        gpu = [x for x, c in cls.items() if c == "GPU_MODEL_SCRIPT" and x.endswith(".py")]
        for n, p in found.items():
            if cls[n] != "CPU_SCRIPT":
                continue
            if n.endswith(".py"):
                text = "\n".join(MODS[os.path.splitext(n)[0]].launches())
            else:
                text = "\n".join(l for l in read(p).splitlines() if not SHELL_QUIET.search(l))
            hit = next((g for g in gpu if re.search(r"(?<![A-Za-z0-9_.-])%s\b" % re.escape(g), text)), None)
            if hit:
                cls[n], why[n] = "GPU_MODEL_SCRIPT", "запускает " + hit
                changed = True
    return found, cls, why


def main():
    # --list <файл> - другой список, для контрольного опыта (список без GPU-скрипта обязан упасть)
    path = sys.argv[sys.argv.index("--list") + 1] if "--list" in sys.argv else LIST
    listed = [l.strip() for l in read(path).splitlines() if l.strip() and not l.strip().startswith("#")]
    found, cls, why = classify()
    gpu = sorted(n for n, c in cls.items() if c == "GPU_MODEL_SCRIPT")
    # внешняя программа: её имя стоит в нашем GPU-запускателе
    external = {n for n in listed if n not in found and any(
        re.search(r"(?<![A-Za-z0-9_.-])%s\b" % re.escape(n), read(found[g])) for g in gpu if not g.endswith(".py"))}
    bad = 0
    for n in gpu:
        if n not in listed:
            bad += 1
            print(f"ОШИБКА GPU_MODEL_SCRIPT нет в списке: {n}  ({why.get(n, '')}; {os.path.relpath(found[n], ROOT)})")
    for n in listed:
        c = cls.get(n)
        if c is None and n not in external:
            bad += 1
            print(f"ОШИБКА в списке, но на диске нет и ни один GPU-запускатель его не зовёт: {n}")
        elif c in ("CPU_SCRIPT", "UTILITY"):
            bad += 1
            print(f"ОШИБКА в списке, но это {c}: {n}  (модель не грузит - {os.path.relpath(found[n], ROOT)})")
    if "--show" in sys.argv:
        for n in sorted(found):
            print(f"{cls[n]:17s} {n:32s} {why.get(n, '')}")
    count = {c: sum(1 for x in cls.values() if x == c) for c in ("GPU_MODEL_SCRIPT", "CPU_SCRIPT", "UTILITY", "LEGACY")}
    print("классы: " + ", ".join(f"{c} {k}" for c, k in count.items()) +
          f"; в списке {len(listed)}, из них внешних {len(external)}, LEGACY "
          f"{sum(1 for n in listed if cls.get(n) == 'LEGACY')}")
    print("всё верно" if bad == 0 else f"ошибок: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

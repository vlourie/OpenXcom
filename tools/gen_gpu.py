#!/usr/bin/env python3
"""
Мост к локальному бэкенду генерации изображений (ComfyUI / A1111-Forge).

Агент gpu-forge вызывает этот скрипт. Скрипт сам определяет, какой бэкенд поднят.

    python tools/gen_gpu.py --check
    python tools/gen_gpu.py --spec docs/assets/raider.spec.md --out assets/10_generated/raider --count 6

Пока бэкенд не установлен, --check честно скажет, что ставить.
"""
from __future__ import annotations

import argparse, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

BACKENDS = {
    "comfyui": {"url": "http://127.0.0.1:8188", "probe": "/system_stats"},
    "a1111":   {"url": "http://127.0.0.1:7860", "probe": "/sdapi/v1/sd-models"},
}


def probe(url: str, path: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(url + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def detect():
    for name, cfg in BACKENDS.items():
        info = probe(cfg["url"], cfg["probe"])
        if info is not None:
            return name, cfg["url"], info
    return None, None, None


def cmd_check() -> int:
    name, url, info = detect()
    if name:
        print(f"OK: бэкенд '{name}' отвечает на {url}")
        if name == "comfyui" and isinstance(info, dict):
            for dev in info.get("devices", []):
                free = dev.get("vram_free", 0) / 2**30
                total = dev.get("vram_total", 0) / 2**30
                print(f"  GPU: {dev.get('name','?')}  VRAM {free:.1f}/{total:.1f} ГБ свободно")
        return 0

    print("Бэкенд генерации не найден. Ни один из адресов не отвечает:")
    for n, c in BACKENDS.items():
        print(f"  - {n}: {c['url']}")
    print()
    print("Что поставить на RTX 5090 (Blackwell, нужен свежий CUDA-билд PyTorch):")
    print("  ComfyUI  — рекомендуется: нодовый пайплайн, стабильный HTTP API, легко")
    print("             воспроизводить генерацию по manifest.json.")
    print("             https://github.com/comfyanonymous/ComfyUI")
    print("  Forge/A1111 — если привычнее WebUI.")
    print()
    print("Важно: для 50-й серии ставь PyTorch с cu128 или новее,")
    print("сборки под cu121 на Blackwell не заведутся.")
    return 1


def parse_spec(path: Path) -> dict:
    """Достаёт промпт, негатив и размер из docs/assets/<имя>.spec.md."""
    text = path.read_text(encoding="utf-8")
    out = {"prompt": "", "negative": "", "width": 1024, "height": 1024}
    section = None
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("## промпт") or low.startswith("## prompt"):
            section = "prompt"; continue
        if low.startswith("## негативный") or low.startswith("## negative"):
            section = "negative"; continue
        if line.startswith("## "):
            section = None; continue
        if low.startswith("размер:"):
            import re
            m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", line)
            if m:
                out["target_w"], out["target_h"] = int(m.group(1)), int(m.group(2))
            continue
        if section and line.strip():
            out[section] += line.strip() + " "
    out["prompt"] = out["prompt"].strip()
    out["negative"] = out["negative"].strip()
    if not out["prompt"]:
        raise SystemExit(f"В спеке {path} нет раздела '## Промпт'")
    return out


def cmd_generate(args) -> int:
    name, url, _ = detect()
    if not name:
        print("Бэкенд не запущен — сначала `python tools/gen_gpu.py --check`", file=sys.stderr)
        return 1

    spec_path = Path(args.spec)
    spec = parse_spec(spec_path)
    outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)

    manifest_path = outdir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"runs": []}

    run = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "backend": name,
        "spec": str(spec_path),
        "prompt": spec["prompt"],
        "negative": spec["negative"],
        "count": args.count,
        "seed_base": args.seed,
        "width": args.width, "height": args.height,
        "steps": args.steps, "cfg": args.cfg,
        "target_size": [spec.get("target_w"), spec.get("target_h")],
        "images": [],
        "status": "not_implemented",
        "note": (
            "Отправка задания в бэкенд зависит от твоего workflow. "
            "Для ComfyUI: POST /prompt с графом workflow в формате API "
            "(в ComfyUI: Settings -> Enable dev mode -> Save (API format)). "
            "Положи свой workflow в tools/workflows/<имя>.json и подставь сюда "
            "поля prompt/negative/seed/steps/cfg перед отправкой."
        ),
    }
    manifest["runs"].append(run)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Заготовка запуска записана в {manifest_path}")
    print("Дальше: подключить свой workflow (см. поле note в манифесте).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Мост к локальной GPU-генерации")
    p.add_argument("--check", action="store_true", help="проверить, поднят ли бэкенд")
    p.add_argument("--spec", help="путь к docs/assets/<имя>.spec.md")
    p.add_argument("--out", default="assets/10_generated/out")
    p.add_argument("--count", type=int, default=6)
    p.add_argument("--seed", type=int, default=-1)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=1024)
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--cfg", type=float, default=6.0)
    a = p.parse_args()

    if a.check or not a.spec:
        return cmd_check()
    return cmd_generate(a)


if __name__ == "__main__":
    sys.exit(main())

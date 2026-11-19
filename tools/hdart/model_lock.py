#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Замок модели генератора (R-145): какие байты весов, LoRA, конфигов и какие библиотеки рисуют.

До 30.09 obj_photo грузил Qwen/Qwen-Image-2.1 и LoRA Viggle веткой main, и generator_rev о весах не знал:
апстрим сдвинул main (правка README) - утверждённый прогон стал качать 43 ГБ заново, а сменись веса -
партия нарисовалась бы другой моделью под тем же утверждением. Замок - файл art/models/<генератор>.lock.json:
коммит репозитория модели и LoRA, sha256 каждого файла слепка, параметры выполнения, версии torch,
diffusers, transformers и прочих. obj_gen_spec считает generator_rev по замку, obj_photo грузит ровно
этот коммит без сети (local_files_only) и перед загрузкой сверяет с замком файлы и библиотеки.

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\model_lock.py make      (снять замок: 43 ГБ sha256, пара минут)
    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\model_lock.py verify    (быстро: размеры, мелкие файлы, LoRA, библиотеки)
    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\model_lock.py verify --full

make снимается интерпретатором модели (.venv-qwen21): версии библиотек берутся у того, кто рисует. С сетью
make сверяет каждый файл ещё и с метаданными HF той же ревизии (LFS sha256, у мелких - git blob sha1).
"""
import argparse
import hashlib
import importlib.metadata as md
import json
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HUB = os.environ.get("HF_HUB_CACHE") or os.path.join("E:" + os.sep, "models", "hub")
LOCK = os.path.join(ROOT, "art", "models", "qwen21_turbo_rgba.lock.json")
ENC = "utf-8-sig"

MODEL_REPO = "Qwen/Qwen-Image-2.1"
# main на 30.09 (02:14 UTC, правка README); с ним рисовала приёмка acc-5e9f63c421c0 (gpuq #278).
# Веса этого коммита побайтно равны b3179ad3 и 790c9263 (сверка LFS sha256, scratchpad hfq/verify_snap.py)
MODEL_COMMIT = "d26bb61231c349cf6b7896fa83353113880e1ba3"
LORA_REPO = "Viggle/Qwen-Image-2.1-viggle-turbo"
LORA_COMMIT = "bb26a0f38e5fe6c124aaccc9187a87eed5d9ed13"
LORA_FILE = "Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors"
LORA_FILES = (LORA_FILE, "scheduler/scheduler_config.json")
LIBRARIES = ("torch", "diffusers", "transformers", "accelerate", "peft", "safetensors", "tokenizers",
             "huggingface_hub", "numpy", "pillow")
SMALL = 64 << 20              # verify без --full: sha256 файлов меньше этого, у больших - размер
RUNTIME = {
    "pipeline": "QwenImage21Pipeline",
    "dtype": "bfloat16",
    "offload": "enable_model_cpu_offload",
    "attention_slicing": False,
    "vae_tiling": False,
    "scheduler": "FlowMatchEulerDiscreteScheduler из репозитория LoRA, subfolder scheduler",
    "lora": "load_lora_weights: репозиторий LoRA, weight_name = файл LoRA, вес 1.0",
    "sigmas": [1.0, 0.9375, 0.875, 0.75, 0.5, 0.25],
    "num_inference_steps": 6,
    "true_cfg_scale": 1.0,
    "negative_prompt": None,
    "mp": 2.0,
    "size": "gen_hd.qwen21_size(w*zoom, h*zoom, mp)",
    "output_resolution": "32 * round(sqrt(W * H) / 32)",
    "generator": "torch.Generator('cuda').manual_seed(seed), seed задания",
    "local_files_only": True,
}


def snapshot(repo, commit, hub=HUB):
    return os.path.join(hub, "models--" + repo.replace("/", "--"), "snapshots", commit)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path):
    with open(path, "rb") as f:
        data = f.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def list_files(snap):
    out = []
    for d, _dirs, files in os.walk(snap):
        for fn in files:
            out.append(os.path.relpath(os.path.join(d, fn), snap).replace(os.sep, "/"))
    return sorted(out)


def library_versions():
    """Версии у ТЕКУЩЕГО интерпретатора, без импорта torch и без CUDA."""
    got = {"python": platform.python_version()}
    for name in LIBRARIES:
        try:
            got[name] = md.version(name)
        except md.PackageNotFoundError:
            got[name] = None
    try:                                    # diffusers из git: версия dev одна на много коммитов
        du = json.loads(md.distribution("diffusers").read_text("direct_url.json") or "{}")
        vcs = du.get("vcs_info", {})
        if vcs.get("commit_id"):
            got["diffusers_git"] = vcs["commit_id"]
    except (md.PackageNotFoundError, ValueError):
        pass
    return got


def hardware():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        return {"gpu": r.stdout.strip()}
    except (OSError, subprocess.SubprocessError):
        return {"gpu": None}


def load(path=LOCK):
    if not os.path.exists(path):
        return None
    with open(path, encoding=ENC) as f:
        return json.load(f)


def pin(lock):
    """Что передать from_pretrained/load_lora_weights: коммиты из замка и запрет сети."""
    return {"model_repo": lock["model"]["repo"], "model_revision": lock["model"]["commit"],
            "lora_repo": lock["lora"]["repo"], "lora_revision": lock["lora"]["commit"],
            "lora_file": lock["lora"]["file"], "local_files_only": bool(lock["runtime"]["local_files_only"])}


def check_files(part, full=False, hub=HUB):
    """Файлы одной части замка против слепка на диске: размер всех, sha256 мелких (или всех при full)."""
    bad = []
    snap = snapshot(part["repo"], part["commit"], hub)
    if not os.path.isdir(snap):
        return ["нет слепка %s@%s в %s" % (part["repo"], part["commit"][:8], hub)]
    for rel, want in part["files"].items():
        p = os.path.join(snap, rel)
        if not os.path.exists(p):
            bad.append("%s: нет файла %s" % (part["repo"], rel))
        elif os.path.getsize(p) != want["size"]:
            bad.append("%s: %s размер %d, в замке %d" % (part["repo"], rel, os.path.getsize(p), want["size"]))
        elif (full or want["size"] < SMALL or rel == part.get("file")) and sha256_file(p) != want["sha256"]:
            bad.append("%s: %s sha256 не тот, что в замке" % (part["repo"], rel))
    return bad


def check_runtime(lock, full=False, hub=HUB):
    """Список расхождений того, что сейчас нарисует, с замком: файлы слепков и версии библиотек."""
    bad = check_files(lock["model"], full, hub) + check_files(lock["lora"], full, hub)
    now = library_versions()
    for k, v in lock["libraries"].items():
        if now.get(k) != v:
            bad.append("библиотека %s: %s, в замке %s" % (k, now.get(k), v))
    return bad


def hf_meta(repo, commit):
    """{путь: (lfs sha256 или None, git blob sha1)} из метаданных HF этой ревизии; None - нет сети."""
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(repo, revision=commit, files_metadata=True)
    except Exception as e:                                          # noqa: BLE001 - сеть, токен, что угодно
        print("   метаданные HF недоступны (%s) - сверка только локальная" % type(e).__name__, flush=True)
        return None
    return {s.rfilename: (s.lfs.sha256 if s.lfs else None, s.blob_id) for s in info.siblings}


def part(repo, commit, files, hub=HUB, main_file=None):
    snap = snapshot(repo, commit, hub)
    if not os.path.isdir(snap):
        raise SystemExit("нет слепка %s@%s в %s - сначала скачать эту ревизию" % (repo, commit[:8], hub))
    meta = hf_meta(repo, commit)
    got, checked = {}, 0
    for rel in files:
        p = os.path.join(snap, rel)
        t = time.time()
        h = sha256_file(p)
        got[rel] = {"size": os.path.getsize(p), "sha256": h}
        if meta is not None:
            if rel not in meta:
                raise SystemExit("%s: %s нет в ревизии %s на HF" % (repo, rel, commit[:8]))
            lfs, blob = meta[rel]
            if (lfs and lfs != h) or (not lfs and blob != git_blob_sha1(p)):
                raise SystemExit("%s: %s на диске не равен файлу ревизии %s на HF" % (repo, rel, commit[:8]))
            checked += 1
        print("   %s %s  %.1f с" % (h[:16], rel, time.time() - t), flush=True)
    out = {"repo": repo, "commit": commit, "files": got}
    if main_file:
        out["file"] = main_file
    return out, checked, meta is not None


def make(path=LOCK, hub=HUB):
    import obj_gen_spec as ogs
    print("модель %s@%s" % (MODEL_REPO, MODEL_COMMIT[:8]), flush=True)
    model, n1, net1 = part(MODEL_REPO, MODEL_COMMIT, list_files(snapshot(MODEL_REPO, MODEL_COMMIT, hub)), hub)
    print("LoRA %s@%s" % (LORA_REPO, LORA_COMMIT[:8]), flush=True)
    lora, n2, net2 = part(LORA_REPO, LORA_COMMIT, LORA_FILES, hub, LORA_FILE)
    lock = {
        "lock": "qwen21_turbo_rgba",
        "format": 1,
        "model": model,
        "lora": lora,
        "runtime": RUNTIME,
        "libraries": library_versions(),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "created_by": "tools/hdart/model_lock.py make",
        "source_run": "acc-5e9f63c421c0/run2 (gpuq #278): грузил main = %s из кэша, без загрузки" % MODEL_COMMIT[:8],
        "code": {"rev": ogs.code_rev(), "parts": [[f, list(n)] for f, n in ogs.CODE_PARTS]},
        "hardware": hardware(),
        "verified": {"hf_metadata": bool(net1 and net2), "files_checked": n1 + n2,
                     "files": len(model["files"]) + len(lora["files"])},
        "notes": "веса %s побайтно равны b3179ad3 и 790c9263 (LFS sha256, 30.09); в lock_rev не входят "
                 "created*, source_run, code, hardware, verified, notes" % MODEL_COMMIT[:8],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        json.dump(lock, f, ensure_ascii=False, indent=1)
    print("замок %s: %d файлов, сверено с HF %d, lock_rev %s, code_rev %s"
          % (path, lock["verified"]["files"], n1 + n2, ogs.lock_rev(lock), lock["code"]["rev"]))
    return lock


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["make", "verify"])
    ap.add_argument("--lock", default=LOCK)
    ap.add_argument("--full", action="store_true", help="verify: sha256 всех файлов, не только мелких")
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.lock)
        return
    lock = load(a.lock)
    if lock is None:
        raise SystemExit("нет замка %s" % a.lock)
    bad = check_runtime(lock, a.full)
    for b in bad:
        print("  ", b)
    print("замок %s: %s" % (os.path.basename(a.lock), "совпадает" if not bad else "РАСХОЖДЕНИЙ %d" % len(bad)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Перепись графики юнитов боя: брони, листы спрайтов, трупы, куклы инвентаря, HANDOB.

Только читает игру. Две игры: X-Piratez (установка Пиратки/Dioxine_XPiratez, активные моды из
user/options.cfg в порядке загрузки) и ванильный UFO (bin/UFO + bin/standard/xcom1).

    set PYTHONIOENCODING=utf-8
    py -3.13 tools/unit_census.py                 # обе игры, census/units/*.tsv
    py -3.13 tools/unit_census.py --games piratez

Как движок собирает лист юнита (сверено с кодом):
  * UNITS/<имя>.PCK из слоёв данных (UFO, мастер, моды - позже кто, тот и прав), кадры подряд,
    из TAB только число кадров (SurfaceSet::loadPck, R-075);
  * поверх - extraSprites с тем же type в порядке загрузки (ExtraSprites::loadSurfaceSet):
    files {номер: путь}, subX/subY режут картинку width x height построчно; путь с '/' на
    конце - папка, кадры по естественному порядку имён; заменённый кадр очищается;
  * сдвиг номера мода (Mod::getOffset, 1000 x reservedSpace) действует только для общих
    наборов BIGOBS/FLOOROB/HANDOB (Mod.cpp setMaxSharedFrames): номер >= числа ванильных кадров
    получает смещение мода, который его задал. Листы юнитов создаются с INT_MAX общих кадров -
    у них номер из рулсета и есть номер кадра;
  * PNG: индекс с нулевой альфой (tRNS) движок переводит в 0 (Surface::FixTransparent), индекс 0
    прозрачен (R-043) - листы читаются индексами, не через convert('RGBA');
  * рулсеты - загрузчиком tools/rul_map.py (Tolerant к повторному якорю, R-046; refNode,
    new/override/update/delete как в движке).

HD-пак ищется так же, как его ищет игра (HdSprites::loadPack): hd/<лист>/pack.hdp и
hd/<лист>/<n>.png во ВСЕХ активных модах (мод башни танка кладёт свой пак в себя, R-175);
отдельно - копия мода hd в репозитории (R-081/R-087) и hd_18+.

Вывод: census/units/armors.tsv, sheets.tsv, frames_summary.tsv, families.tsv, family_pairs.tsv,
corpses.tsv, inv.tsv, handob.tsv, units.tsv, summary.json (UTF-8 со спецификацией, R-001).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rul_map as rm  # noqa: E402  (загрузчик рулсетов, R-046)

ENC = "utf-8-sig"
ROOT = Path(__file__).resolve().parent.parent
PZ = ROOT / "Пиратки" / "Dioxine_XPiratez"
OUT = ROOT / "census" / "units"

SHARED = ("BIGOBS.PCK", "FLOOROB.PCK", "HANDOB.PCK")
# наборы движка, которые не являются листами юнитов, даже если нарезаны 32x40
NOT_UNIT_SETS = {"BIGOBS.PCK", "FLOOROB.PCK", "HANDOB.PCK", "SMOKE.PCK", "HIT.PCK", "X1.PCK",
                 "CURSOR.PCK", "BLANKS.PCK", "BASEBITS.PCK", "INTICON.PCK", "CustomArmorPreviews",
                 "CustomItemPreviews", "Projectiles", "UnderwaterProjectiles", "GlobeMarkers",
                 "TinyRanks", "Touch", "SPICONS.DAT", "DETBORD.PCK", "DETBORD2.PCK", "ICONS.PCK",
                 "MEDIBORD.PCK", "SCANBORD.PCK", "UNIBORD.PCK", "SCANG.DAT", "BREATH-1.PCK"}

# UnitSprite.cpp: таблица routines[] и комментарии к drawRoutineN
ROUTINES = {
    0: "солдат/сектоид", 1: "флоатер", 2: "танк X-COM", 3: "кибердиск", 4: "гражданский/эфириал/зомби",
    5: "сектопод/жнец", 6: "змеечеловек", 7: "крисалид", 8: "силакоид", 9: "селатид",
    10: "мутон", 11: "танк TFTD", 12: "галлюциноид", 13: "акванавт", 14: "калцинит/глубоководный",
    15: "акватоид", 16: "биодрон", 17: "гражданский TFTD", 18: "гражданский TFTD 2",
    19: "тентакулат", 20: "трисцен", 21: "ксарквид", 22: "вертолёт",
}
MOVEMENT = {0: "walk", 1: "fly", 2: "slide"}


# ------------------------------------------------------------------ виртуальная файловая система

class VFS:
    """Слои данных как в FileMap: позже слой - выше приоритет. Поиск без учёта регистра."""

    def __init__(self, roots):
        self.roots = [(mid, Path(p)) for mid, p in roots if Path(p).is_dir()]
        self._dir = {}

    def _list(self, d: Path):
        key = str(d)
        if key not in self._dir:
            try:
                self._dir[key] = {n.upper(): n for n in os.listdir(d)}
            except OSError:
                self._dir[key] = {}
        return self._dir[key]

    def _walk(self, root: Path, rel: str):
        cur = root
        for part in [p for p in re.split(r"[\\/]", rel) if p and p != "."]:
            names = self._list(cur)
            real = names.get(part.upper())
            if real is None:
                return None
            cur = cur / real
        return cur

    def resolve(self, rel: str):
        """(мод, путь) самого верхнего слоя, где файл есть, иначе None."""
        for mid, root in reversed(self.roots):
            p = self._walk(root, rel)
            if p is not None and p.exists():
                return mid, p
        return None

    def folder(self, rel: str):
        """Содержимое виртуальной папки: ИМЯ -> (мод, путь), верхний слой перекрывает."""
        out = {}
        for mid, root in self.roots:
            p = self._walk(root, rel)
            if p is not None and p.is_dir():
                for n in os.listdir(p):
                    out[n.upper()] = (mid, p / n)
        return out


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# ------------------------------------------------------------------ игры и моды

def read_meta(d: Path):
    meta = {}
    p = d / "metadata.yml"
    if p.is_file():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r'^\s*(\w+)\s*:\s*"?([^"#]*?)"?\s*(#.*)?$', line)
            if m:
                meta[m.group(1)] = m.group(2).strip()
    return meta


def piratez_chain():
    """[(id, папка)] в порядке загрузки: xcom1, затем активные моды из options.cfg."""
    import yaml
    cfg = yaml.safe_load((PZ / "user" / "options.cfg").read_text(encoding="utf-8"))
    active = [m["id"] for m in cfg.get("mods", []) if m.get("active")]
    dirs = {}
    for base in (PZ / "user" / "mods", PZ / "standard"):
        for d in base.iterdir():
            if d.is_dir():
                mid = read_meta(d).get("id")
                if mid:
                    dirs.setdefault(mid, d)
    chain = [("xcom1", PZ / "standard" / "xcom1")]
    for mid in active:
        if mid in dirs and mid != "xcom1":
            chain.append((mid, dirs[mid]))
        elif mid not in dirs:
            print(f"  мод {mid} активен, но не найден", file=sys.stderr)
    return chain


def games():
    pz_chain = piratez_chain()
    pz_hd = [(mid, d / "hd") for mid, d in pz_chain if (d / "hd").is_dir()]
    return {
        "piratez": dict(
            chain=pz_chain,
            data=[("common", PZ / "common"), ("UFO", PZ / "UFO")] + pz_chain,
            battle_pal=("jasc", PZ / "user" / "mods" / "Piratez" / "Resources" / "Pals" / "delicious_regular.pal"),
            hd=pz_hd,
        ),
        "xcom1": dict(
            chain=[("xcom1", ROOT / "bin" / "standard" / "xcom1")],
            data=[("common", ROOT / "bin" / "common"), ("UFO", ROOT / "bin" / "UFO"),
                  ("xcom1", ROOT / "bin" / "standard" / "xcom1")],
            battle_pal=("dat", ROOT / "bin" / "UFO" / "GEODATA" / "PALETTES.DAT"),
            # ванильный UFO с HD играют той же сборкой и тем же модом hd, что и Пиратки
            hd=[("hd", PZ / "user" / "mods" / "hd" / "hd")],
        ),
    }


HD_REPO = ROOT / "user" / "mods" / "hd" / "hd"
HD_ADULT = PZ / "user" / "mods" / "hd" / "hd_18+"


def mod_offsets(chain):
    off, cur = {}, 0
    for mid, d in chain:
        size = int(read_meta(d).get("reservedSpace") or 1)
        off[mid] = (1000 * cur, 1000 * size)
        cur += size
    return off


def load_rules(chain, src):
    keys = rm.section_keys(src)
    st = rm.Store()
    for mid, d in chain:
        rdir = d / "Ruleset" if (d / "Ruleset").is_dir() else d
        files = rm.rul_files(rdir)
        for p in files:
            rel = f"{mid}|{p.relative_to(d).as_posix()}"
            rm.load_file(st, p, rel, keys)
    # op записи extraSprites (type / typeSingle / delete) - по месту объявления
    ops = {}
    for (sec, rid), lst in st.defs.items():
        if sec == "extraSprites":
            for rel, line, op in lst:
                ops[(rel, line)] = op
    return st, ops


def mod_of(rel):
    return rel.split("|", 1)[0] if rel else ""


# ------------------------------------------------------------------ палитры и картинки

def load_battle_palette(kind, path: Path):
    if kind == "jasc":
        lines = path.read_text(encoding="ascii", errors="replace").split()
        vals = [int(x) for x in lines[3:3 + 768]]
        return np.array(vals, dtype=np.int16).reshape(256, 3)
    raw = path.read_bytes()
    off = 4 * (768 + 6)          # палитра 4 PALETTES.DAT - боевая, 6-битная
    pal = np.frombuffer(raw[off:off + 768], dtype=np.uint8).astype(np.int16).reshape(256, 3)
    return pal * 4


_IMG_CACHE = {}


def read_image(path: Path):
    """(индексы HxW uint8, палитра 256x3 int16 или None, ошибка)."""
    key = str(path)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    res = (None, None, "")
    try:
        im = Image.open(path)
        if im.mode in ("P", "L"):
            idx = np.array(im, dtype=np.uint8)
            pal = None
            if im.mode == "P":
                p = (im.getpalette() or []) + [0] * 768
                pal = np.array(p[:768], dtype=np.int16).reshape(256, 3)
                tr = im.info.get("transparency")
                t = None
                if isinstance(tr, int):
                    t = tr
                elif isinstance(tr, (bytes, bytearray)):
                    for i, a in enumerate(tr):
                        if a == 0:
                            t = i
                            break
                if t:
                    idx = idx.copy()
                    idx[idx == t] = 0
            res = (idx, pal, "")
        else:
            res = (None, None, f"не 8-битная ({im.mode})")
    except Exception as e:  # noqa: BLE001
        res = (None, None, f"не читается: {e}")
    if len(_IMG_CACHE) > 64:
        _IMG_CACHE.clear()
    _IMG_CACHE[key] = res
    return res


def read_pck(pck: Path, tab: Path | None, w, h):
    """Кадры PCK подряд, из TAB только число кадров (SurfaceSet::loadPck, R-075)."""
    if tab is not None and tab.exists():
        t = tab.read_bytes()
        first = struct.unpack("<i", t[:4])[0] if len(t) >= 4 else 0
        n = len(t) // 2 if first != 0 else len(t) // 4
    else:
        n = 1
    data = pck.read_bytes()
    pos, frames = 0, []
    size = w * h
    for _ in range(n):
        buf = bytearray(size)
        if pos >= len(data):
            frames.append(np.zeros((h, w), np.uint8))
            continue
        x = data[pos] * w
        pos += 1
        while pos < len(data):
            v = data[pos]
            pos += 1
            if v == 255:
                break
            if v == 254:
                x += data[pos] if pos < len(data) else 0
                pos += 1
            else:
                if x < size:
                    buf[x] = v
                x += 1
        frames.append(np.frombuffer(bytes(buf), np.uint8).reshape(h, w))
    return frames


# ------------------------------------------------------------------ сборка набора кадров

class SetBuild:
    def __init__(self, name):
        self.name = name
        self.frames = {}        # номер -> массив индексов
        self.fw = self.fh = 0
        self.sources = []       # (мод, файл, вид)
        self.src_of = {}        # номер -> индекс в sources
        self.pal_diffs = []     # средний разброс палитры PNG против боевой
        self.errors = []
        self.vanilla = 0


def build_set(name, vfs: VFS, extras, offsets, battle_pal):
    """Набор кадров так, как его соберёт движок."""
    sb = SetBuild(name)
    shared = 1 << 31
    base = vfs.resolve(f"UNITS/{name}")
    if base:
        mid, pck = base
        w, h = (32, 48) if name.upper() == "BIGOBS.PCK" else (32, 40)
        tab = pck.with_suffix(".TAB")
        if not tab.exists():
            tab = vfs.resolve(f"UNITS/{Path(name).stem}.TAB")
            tab = tab[1] if tab else None
        frs = read_pck(pck, tab, w, h)
        sb.fw, sb.fh = w, h
        sb.sources.append((mid, pck.relative_to(pck.parents[1]).as_posix(), "PCK", pck))
        for i, f in enumerate(frs):
            sb.frames[i] = f
            sb.src_of[i] = 0
        sb.vanilla = len(frs)
        if name in SHARED:
            shared = len(frs)
    for rid, rel, line, fields, op in extras.get(name, []):
        if op == "delete":
            sb.frames.clear()
            sb.src_of.clear()
            continue
        if op == "typeSingle" or fields.get("singleImage"):
            continue
        mid = mod_of(rel)
        moff, msize = offsets.get(mid, (0, 1000))
        width = int(fields.get("width", 320))
        height = int(fields.get("height", 200))
        subx, suby = int(fields.get("subX", 0) or 0), int(fields.get("subY", 0) or 0)
        sub = subx != 0 and suby != 0
        fw, fh = (subx, suby) if sub else (width, height)
        if not sb.frames and not sb.fw:
            sb.fw, sb.fh = fw, fh
        elif not sb.frames:
            sb.fw, sb.fh = fw, fh       # пустой набор перекраивается под новый размер

        def put(index, arr, si):
            idx = index
            if idx >= shared:
                idx += moff
            sb.frames[idx] = arr
            sb.src_of[idx] = si

        files = fields.get("files") or {}
        if not isinstance(files, dict):
            continue
        for start, fname in sorted(files.items(), key=lambda kv: int(kv[0])):
            start = int(start)
            fname = str(fname)
            if fname.endswith("/"):
                folder = vfs.folder(fname.rstrip("/"))
                names = sorted((n for n in folder), key=lambda n: natural_key(folder[n][1].name))
                k = start
                for n in names:
                    fmid, fp = folder[n]
                    if fp.suffix.lower() not in (".png", ".gif", ".bmp"):
                        continue
                    idx, pal, err = read_image(fp)
                    if idx is None:
                        sb.errors.append(f"{fp.name}: {err}")
                        continue
                    sb.sources.append((fmid, fname + fp.name, "папка", fp))
                    put(k, idx, len(sb.sources) - 1)
                    k += 1
                continue
            hit = vfs.resolve(fname)
            if not hit:
                sb.errors.append(f"нет файла {fname} ({mid})")
                continue
            fmid, fp = hit
            idx, pal, err = read_image(fp)
            if idx is None:
                sb.errors.append(f"{fname}: {err}")
                continue
            sb.sources.append((fmid, fname, "лист" if sub else "кадр", fp))
            si = len(sb.sources) - 1
            if pal is not None and battle_pal is not None:
                used = np.unique(idx)
                used = used[used != 0]
                if used.size:
                    sb.pal_diffs.append(float(np.abs(pal[used] - battle_pal[used]).mean()))
            if not sub:
                put(start, idx, si)
                continue
            canvas = np.zeros((height, width), np.uint8)
            hh, ww = min(height, idx.shape[0]), min(width, idx.shape[1])
            canvas[:hh, :ww] = idx[:hh, :ww]
            k = start
            for y in range(height // suby):
                for x in range(width // subx):
                    put(k, canvas[y * suby:(y + 1) * suby, x * subx:(x + 1) * subx].copy(), si)
                    k += 1
    return sb


# ------------------------------------------------------------------ отпечатки кадров

def h12(b: bytes):
    return hashlib.sha1(b).hexdigest()[:12]


def fingerprint(arr: np.ndarray):
    """exact, mask, recolor, mirror-mask, пикселей, цветов. recolor - перенумерация индексов
    по порядку первого появления: одна форма в других рампах даёт тот же ключ."""
    shp = f"{arr.shape[1]}x{arr.shape[0]}".encode()
    flat = arr.ravel()
    nz = flat != 0
    npx = int(nz.sum())
    if npx == 0:
        return None
    mask = np.packbits(nz)
    vals = flat[nz]
    u, first = np.unique(vals, return_index=True)
    order = np.argsort(first)
    rank = np.zeros(256, np.uint8)
    rank[u[order]] = np.arange(1, len(u) + 1, dtype=np.uint8)
    norm = np.zeros_like(flat)
    norm[nz] = rank[vals]
    mir = np.packbits(arr[:, ::-1].ravel() != 0)
    return (h12(shp + flat.tobytes()), h12(shp + mask.tobytes()), h12(shp + norm.tobytes()),
            h12(shp + mir.tobytes()), npx, len(u))


# ------------------------------------------------------------------ HD-паки

def pack_info(d: Path):
    """(кадров в паке, номера, масштаб, база WxH, модель)."""
    p = d / "pack.hdp"
    out = dict(count=0, idx=set(), scale="", base="", model="", fmt="", path=None, table={}, mtime=0.0)
    if p.is_file():
        with open(p, "rb") as f:
            head = f.read(24)
            if head[:8] == b"OXHDPCK1":
                scale, bw, bh, n = struct.unpack("<IIII", head[8:24])
                raw = f.read(n * 12)
                table = {}
                for i in range(n):
                    a, o, s = struct.unpack_from("<III", raw, i * 12)
                    if s:
                        table[a] = (o, s)
                out.update(count=len(table), idx=set(table), scale=str(scale), base=f"{bw}x{bh}",
                           fmt="pack.hdp", path=p, table=table, mtime=p.stat().st_mtime)
        st = d / "settings.txt"
        if st.is_file():
            m = re.search(r"model=(\S+)", st.read_text(encoding="utf-8", errors="replace"))
            meth = re.search(r"method=(\S+)", st.read_text(encoding="utf-8", errors="replace"))
            out["model"] = (m.group(1) if m else "") + (f" ({meth.group(1)})" if meth else "")
        elif out["fmt"]:
            out["model"] = "нет settings.txt"
    pngs = set()
    for n in os.listdir(d):
        m = re.match(r"^(\d+)(\.v\d+)?\.png$", n, re.I)
        if m:
            pngs.add(int(m.group(1)))
    if pngs:
        out["idx"] = out["idx"] | pngs
        out["count"] = len(out["idx"])
        out["fmt"] = (out["fmt"] + "+png") if out["fmt"] else "png"
    return out


def verify_pack(info, frames, sample):
    """Совпадает ли силуэт HD-кадра пака с силуэтом классического кадра (IoU масок на базовой
    сетке). Ловит пак, снятый со старого листа (R-175). Возвращает (проверено, мин. IoU, номер)."""
    if not info or not info.get("path") or not sample:
        return 0, None, None
    cand = [i for i in sorted(info["table"]) if i in frames and (frames[i] != 0).any()]
    if not cand:
        return 0, None, None
    if sample > 0 and len(cand) > sample:
        step = len(cand) / sample
        cand = [cand[int(k * step)] for k in range(sample)]
    worst, worst_i, done = 1.0, None, 0
    with open(info["path"], "rb") as f:
        for i in cand:
            o, s = info["table"][i]
            f.seek(o)
            try:
                im = Image.open(io.BytesIO(f.read(s)))
                im.load()
            except Exception:  # noqa: BLE001
                return done, 0.0, i
            base = frames[i] != 0
            bh, bw = base.shape
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            if im.size[0] % bw or im.size[1] % bh:
                im = im.resize((bw * 4, bh * 4))
            k = im.size[0] // bw
            al = np.asarray(im)[:, :, 3].reshape(bh, k, bw, k).mean(axis=(1, 3)) > 127
            inter = (al & base).sum()
            union = (al | base).sum()
            iou = float(inter) / union if union else 1.0
            done += 1
            if iou < worst:
                worst, worst_i = iou, i
    return done, worst, worst_i


class HdIndex:
    def __init__(self, roots):
        self.roots = [(mid, Path(r)) for mid, r in roots if Path(r).is_dir()]
        self.names = []
        for mid, r in self.roots:
            self.names.append((mid, r, {n.upper(): n for n in os.listdir(r)}))

    def find(self, setname):
        """[(мод, сведения)] по всем слоям."""
        res = []
        for mid, r, names in self.names:
            real = names.get(setname.upper())
            if real and (r / real).is_dir():
                res.append((mid, pack_info(r / real)))
        return res


def single_dir(root: Path, setname):
    if not root.is_dir():
        return None
    for n in os.listdir(root):
        if n.upper() == setname.upper() and (root / n).is_dir():
            return pack_info(root / n)
    return None


# ------------------------------------------------------------------ вспомогательное

def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def jcell(v):
    if v is None or v == "" or v == [] or v == {}:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def cell(v):
    s = jcell(v)
    return s.replace("\t", " ").replace("\r", " ").replace("\n", " | ")


def write_tsv(path: Path, header, rows):
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(cell(x) for x in r) + "\n")


def script_names(scripts):
    if not isinstance(scripts, dict):
        return ""
    return ",".join(sorted(k for k in scripts))


# ------------------------------------------------------------------ перепись одной игры

def census_game(gname, g, src, acc, verify):
    t0 = time.time()
    print(f"== {gname}: рулсеты ({len(g['chain'])} модов)", flush=True)
    st, ops = load_rules(g["chain"], src)
    offsets = mod_offsets(g["chain"])
    vfs = VFS(g["data"])
    battle_pal = load_battle_palette(*g["battle_pal"])
    hdx = HdIndex(g["hd"])
    print(f"   {time.time() - t0:.1f} с; записей: {len(st.rules)}", flush=True)

    def section(sec):
        return {rid: rec for (s, rid), rec in st.rules.items() if s == sec}

    def src_mod(sec, rid):
        d = st.defs.get((sec, rid), [])
        return mod_of(d[0][0]) if d else ""

    def touched_by(sec, rid):
        return sorted({mod_of(r) for r, _l, _o in st.defs.get((sec, rid), [])})

    armors, units, soldiers, items = section("armors"), section("units"), section("soldiers"), section("items")
    races = section("alienRaces")

    extras = defaultdict(list)
    singles = {}                  # имя поверхности -> (мод, файл, w, h)
    for rid, rel, line, fields in st.lists.get("extraSprites", []):
        op = ops.get((rel, line), "type")
        extras[rid].append((rid, rel, line, fields, op))
        if op == "delete":
            singles.pop(rid, None)
            continue
        if op == "typeSingle" or fields.get("singleImage"):
            f = fields.get("fileSingle")
            if not f:
                fl = fields.get("files") or {}
                f = next(iter(fl.values()), "") if isinstance(fl, dict) and fl else ""
            singles[rid] = (mod_of(rel), str(f), fields.get("width", ""), fields.get("height", ""))

    # кто носит броню
    unit_by_armor = defaultdict(list)
    for uid, rec in units.items():
        a = rec["fields"].get("armor")
        if a:
            unit_by_armor[a].append(uid)
    sold_by_armor = defaultdict(list)
    for sid, rec in soldiers.items():
        f = rec["fields"]
        for a in as_list(f.get("armor")):
            sold_by_armor[a].append(sid)
        for a in as_list(f.get("allowedArmors")):
            sold_by_armor[a].append(sid + "(allowed)")
    race_members = defaultdict(list)
    for rid, rec in races.items():
        for m in as_list(rec["fields"].get("members")):
            race_members[m].append(rid)

    # ---------------- листы
    sheet_users = defaultdict(list)
    for aid, rec in armors.items():
        s = rec["fields"].get("spriteSheet")
        if s:
            sheet_users[s].append(aid)
    names = set(sheet_users)
    for name, lst in extras.items():
        if name in NOT_UNIT_SETS or name in names:
            continue
        for _r, _rel, _l, fields, op in lst:
            if op != "typeSingle" and not fields.get("singleImage") and \
                    int(fields.get("subX", 0) or 0) == 32 and int(fields.get("subY", 0) or 0) == 40 \
                    and name.upper().endswith(".PCK"):
                names.add(name)
                break
    for n in vfs.folder("UNITS"):
        if n.endswith(".PCK") and n not in SHARED:
            names.add(n)

    sheet_rows, frame_rows = [], []
    sheet_fp = {}                 # имя -> {номер: отпечаток}
    sheet_frames = {}             # имя -> {номер: индексы} (для проверки перекраски)
    acc_iou = acc.setdefault("iou", [])
    print(f"   листов: {len(names)}", flush=True)
    t1 = time.time()
    for name in sorted(names):
        sb = build_set(name, vfs, extras, offsets, battle_pal)
        fps = {}
        for i, arr in sb.frames.items():
            fp = fingerprint(arr)
            if fp:
                fps[i] = fp
        sheet_fp[name] = fps
        users = sheet_users.get(name, [])
        routines = sorted({int(armors[a]["fields"].get("drawingRoutine", 0) or 0) for a in users})
        sizes = sorted({int(armors[a]["fields"].get("size", 1) or 1) for a in users})
        hd = hdx.find(name)
        hd_cov = set()
        for _m, info in hd:
            hd_cov |= info["idx"]
        nonempty = set(fps)
        rep = single_dir(HD_REPO, name)
        adult = single_dir(HD_ADULT, name)
        shapes = Counter(f"{a.shape[1]}x{a.shape[0]}" for a in sb.frames.values())
        mods_src = sorted({s[0] for s in sb.sources})
        # пак, который возьмёт игра: pack.hdp самого верхнего мода (одно имя в общей ФС)
        eff = next((i for _m, i in reversed(hd) if i.get("path")), None)
        hd_date = hd_stale = hd_check = ""
        if eff:
            hd_date = time.strftime("%Y-%m-%d", time.localtime(eff["mtime"]))
            newer = [s for s in sb.sources if s[2] != "PCK" and s[3].stat().st_mtime > eff["mtime"] + 60]
            if newer:
                hd_stale = f"новее пака: {len(newer)} файл(ов), напр. {newer[0][0]}:{newer[0][1]}"
            n, worst, wi = verify_pack(eff, sb.frames, verify)
            if n:
                hd_check = f"{n} кадр., IoU мин {worst:.2f} (#{wi})"
                acc_iou.append((gname, name, worst, wi))
        sheet_frames[name] = sb.frames
        sheet_rows.append([
            gname, name, "да" if users else "нет", len(users), ",".join(users[:6]) + (" ..." if len(users) > 6 else ""),
            ",".join(map(str, routines)), ",".join(map(str, sizes)),
            len(sb.frames), (max(sb.frames) + 1) if sb.frames else 0, len(nonempty), len(sb.frames) - len(nonempty),
            len({fp[0] for fp in fps.values()}), len({fp[1] for fp in fps.values()}),
            ",".join(f"{k}:{v}" for k, v in shapes.most_common()),
            "PCK+PNG" if sb.vanilla and len(sb.sources) > 1 else ("PCK" if sb.vanilla else "PNG"),
            ";".join(f"{s[0]}:{s[1]}" for s in sb.sources[:4]) + (f" (+{len(sb.sources) - 4})" if len(sb.sources) > 4 else ""),
            ",".join(mods_src),
            "боевая" if not sb.pal_diffs else f"своя PNG, разброс {np.mean(sb.pal_diffs):.1f}",
            ";".join(f"{m}" for m, _i in hd), max((i["count"] for _m, i in hd), default=0),
            len(nonempty & hd_cov), len(nonempty - hd_cov),
            ";".join(i["fmt"] for _m, i in hd), ";".join(i["model"] for _m, i in hd if i["model"]),
            hd_date, hd_stale, hd_check,
            rep["count"] if rep else "", adult["count"] if adult else "",
            "; ".join(sb.errors[:3]),
        ])
        for i in sorted(fps):
            e, mk, rc, mi, npx, nc = fps[i]
            frame_rows.append([gname, name, i, e, mk, rc, mi, npx, nc, "да" if i in hd_cov else ""])
    print(f"   листы: {time.time() - t1:.1f} с", flush=True)

    # ---------------- семейства перекраски и копий
    fam_rows, pair_rows, fam_stats = families(gname, sheet_fp, sheet_frames, sheet_users)
    skeleton = {r[4]: r[1] for r in fam_rows if r[1].startswith("S")}
    family_of = {r[4]: r[1] for r in fam_rows if r[1].startswith("F")}
    for r in sheet_rows:
        r.append(family_of.get(r[1], ""))
        r.append(skeleton.get(r[1], ""))
    del sheet_frames

    # ---------------- сколько кадров рисовать: копии и перекраски выводятся, а не рисуются
    fam_base = {r[4]: (r[3], r[5]) for r in fam_rows if r[1].startswith("F")}
    used_names = sorted(n for n in sheet_fp if sheet_users.get(n))
    order = sorted(used_names, key=lambda n: (fam_base.get(n, (n, "основа"))[1] != "основа", n))
    seen, draw, d_copy, d_recolor = set(), 0, 0, 0
    draw_by_sheet = {}
    for n in order:
        base, rel = fam_base.get(n, (n, "основа"))
        bfp = sheet_fp.get(base, {})
        k = 0
        for i, fp in sheet_fp[n].items():
            if fp[0] in seen:
                d_copy += 1
                continue
            seen.add(fp[0])
            if rel == "перекраска" and i in bfp and bfp[i][1] == fp[1]:
                d_recolor += 1
                continue
            draw += 1
            k += 1
        draw_by_sheet[n] = k
    for r in sheet_rows:
        r.append(draw_by_sheet.get(r[1], ""))
    plan = dict(frames_to_draw=draw, derived_exact_copy=d_copy, derived_recolor=d_recolor)

    # ---------------- брони
    armor_rows = []
    for aid, rec in sorted(armors.items()):
        f = rec["fields"]
        layers = ""
        if f.get("layersDefinition"):
            ld = f["layersDefinition"]
            layers = f"{f.get('layersDefaultPrefix', '')}; версий {len(ld)}; слоёв до {max((len(v) for v in ld.values()), default=0)}"
            if f.get("layersSpecificPrefix"):
                layers += f"; specific {jcell(f.get('layersSpecificPrefix'))}"
        colors = []
        for grp in ("Face", "Hair", "Utile", "Rank"):
            gk, ck = f"sprite{grp}Group", f"sprite{grp}Color"
            if f.get(gk) is not None or f.get(ck) is not None:
                colors.append(f"{grp.lower()}:{f.get(gk, '')}/{jcell(f.get(ck))}")
        armor_rows.append([
            gname, aid, f.get("spriteSheet", ""), f.get("spriteInv", ""),
            int(f.get("drawingRoutine", 0) or 0), ROUTINES.get(int(f.get("drawingRoutine", 0) or 0), "?"),
            int(f.get("size", 1) or 1), jcell(f.get("corpseBattle")), f.get("corpseGeo", ""),
            layers, script_names(f.get("scripts")),
            jcell(f.get("canHoldWeapon")), jcell(f.get("constantAnimation")),
            MOVEMENT.get(int(f.get("movementType", 0) or 0), f.get("movementType")),
            "; ".join(colors), jcell(f.get("units")),
            ",".join(unit_by_armor.get(aid, [])), ",".join(sold_by_armor.get(aid, [])),
            src_mod("armors", aid), ",".join(touched_by("armors", aid)),
        ])

    # ---------------- общие наборы предметов
    shared_sets = {n: build_set(n, vfs, extras, offsets, None) for n in SHARED}
    shared_hd = {n: hdx.find(n) for n in SHARED}

    def engine_index(item_id, field, setname):
        rec = items[item_id]
        v = rec["fields"].get(field)
        if v is None or isinstance(v, (dict, list)):
            return v, None
        v = int(v)
        if v < 0:
            return v, None
        rel = rec["setby"].get(field, ("", 0))[0]
        moff = offsets.get(mod_of(rel), (0, 0))[0]
        shared = shared_sets[setname].vanilla
        return v, (v + moff if v >= shared else v)

    def hd_has(setname, idx):
        return any(idx in i["idx"] for _m, i in shared_hd[setname])

    # ---------------- трупы
    corpse_of = defaultdict(list)
    for aid, rec in armors.items():
        for c in as_list(rec["fields"].get("corpseBattle")):
            corpse_of[c].append((aid, "battle"))
        cg = rec["fields"].get("corpseGeo")
        if cg:
            corpse_of[cg].append((aid, "geo"))
    corpse_rows = []
    for iid, rec in sorted(items.items()):
        f = rec["fields"]
        bt = int(f.get("battleType", 0) or 0)
        if bt != 11 and iid not in corpse_of:
            continue
        roles = sorted({r for _a, r in corpse_of.get(iid, [])})
        fv, fi = engine_index(iid, "floorSprite", "FLOOROB.PCK")
        bv, bi = engine_index(iid, "bigSprite", "BIGOBS.PCK")
        hv, hi = engine_index(iid, "handSprite", "HANDOB.PCK") if "handSprite" in f else (None, None)
        fl = shared_sets["FLOOROB.PCK"].frames.get(fi) if fi is not None else None
        bg = shared_sets["BIGOBS.PCK"].frames.get(bi) if bi is not None else None
        ffp = fingerprint(fl) if fl is not None else None
        bfp = fingerprint(bg) if bg is not None else None
        owners = [a for a, _r in corpse_of.get(iid, [])]
        corpse_rows.append([
            gname, iid, bt, ",".join(roles), len(owners), ",".join(owners[:4]) + (" ..." if len(owners) > 4 else ""),
            "" if fv is None else fv, "" if fi is None else fi, ffp[0] if ffp else ("пусто" if fl is not None else ("нет кадра" if fi is not None else "")),
            "" if bv is None else bv, "" if bi is None else bi, bfp[0] if bfp else ("пусто" if bg is not None else ("нет кадра" if bi is not None else "")),
            "" if hv is None else hv, "" if hi is None else hi,
            "да" if fi is not None and hd_has("FLOOROB.PCK", fi) else "",
            "да" if bi is not None and hd_has("BIGOBS.PCK", bi) else "",
            src_mod("items", iid),
        ])

    # ---------------- HANDOB
    hand_use = defaultdict(list)
    default_hand = 0
    for iid, rec in items.items():
        if "handSprite" not in rec["fields"]:
            default_hand += 1
            continue
        _v, hi = engine_index(iid, "handSprite", "HANDOB.PCK")
        if hi is None:
            continue
        for d in range(8):
            hand_use[hi + d].append(iid)
    hs = shared_sets["HANDOB.PCK"]
    hand_rows = []
    for i in sorted(set(hs.frames) | set(hand_use)):
        arr = hs.frames.get(i)
        fp = fingerprint(arr) if arr is not None else None
        srcf = hs.sources[hs.src_of[i]] if i in hs.src_of else None
        users = sorted(set(hand_use.get(i, [])))
        hand_rows.append([gname, i, "нет кадра" if arr is None else ("пусто" if fp is None else "да"),
                          fp[0] if fp else "", fp[1] if fp else "", len(users), ",".join(users[:4]) + (" ..." if len(users) > 4 else ""),
                          f"{srcf[0]}:{srcf[1]}" if srcf else "", "да" if hd_has("HANDOB.PCK", i) else ""])

    # ---------------- куклы инвентаря
    surf = dict(singles)
    for n, (mid, p) in vfs.folder("UFOGRAPH").items():
        if n.endswith(".SPK"):
            surf.setdefault(n, (mid, f"UFOGRAPH/{p.name}", 320, 200))
    by_base = defaultdict(list)
    for n in surf:
        m = re.match(r"^(.*?)([MF]\d+)?\.SPK$", n)
        if m:
            by_base[m.group(1)].append(n)
    hd_ui = {}
    for _mid, r in g["hd"]:
        u = r / "UI"
        if u.is_dir():
            for n in os.listdir(u):
                if n.lower().endswith(".png"):
                    hd_ui[n[:-4].lower()] = True
    inv_use = defaultdict(lambda: [set(), set()])   # имя -> (вид, брони)
    armor_inv = {}
    for aid, rec in armors.items():
        f = rec["fields"]
        got = []
        p = f.get("spriteInv")
        if p:
            for n in [p, p + ".SPK"] + [x for x in by_base.get(p, []) if x != p + ".SPK"]:
                if n in surf:
                    got.append(n)
                    inv_use[n][0].add("spriteInv" if n in (p, p + ".SPK") else "вариант пол/вид")
                    inv_use[n][1].add(aid)
        ld = f.get("layersDefinition") or {}
        if isinstance(ld, dict) and ld:
            pre = f.get("layersDefaultPrefix", "")
            spec = f.get("layersSpecificPrefix") or {}
            for _ver, layer_list in ld.items():
                for li, item in enumerate(as_list(layer_list)):
                    if not item:
                        continue
                    pfx = spec.get(li, spec.get(str(li), pre)) if isinstance(spec, dict) else pre
                    n = f"{pfx}__{li}__{item}"
                    inv_use[n][0].add("слой")
                    inv_use[n][1].add(aid)
                    got.append(n)
        armor_inv[aid] = len(set(got))
    inv_rows = []
    file_hash = {}
    for n, (kinds, aids) in sorted(inv_use.items()):
        s = surf.get(n)
        fh = ""
        size = ""
        if s:
            hit = vfs.resolve(s[1]) if s[1] else None
            if hit:
                key = str(hit[1])
                if key not in file_hash:
                    sz = ""
                    if hit[1].suffix.upper() != ".SPK":
                        try:
                            with Image.open(hit[1]) as im:
                                sz = f"{im.size[0]}x{im.size[1]}"
                        except Exception:  # noqa: BLE001
                            sz = "не читается"
                    else:
                        sz = "320x200"
                    file_hash[key] = (h12(hit[1].read_bytes()), sz)
                fh, size = file_hash[key]
            else:
                size = "НЕТ ФАЙЛА"
        stem = Path(s[1]).stem.lower() if s and s[1] else ""
        inv_rows.append([gname, n, ",".join(sorted(kinds)), len(aids), ",".join(sorted(aids)[:3]) + (" ..." if len(aids) > 3 else ""),
                         s[0] if s else "", s[1] if s else "НЕТ ПОВЕРХНОСТИ", size, fh,
                         "да" if (n.lower() in hd_ui or stem in hd_ui) else ""])

    # ---------------- юниты и бойцы
    unit_rows = []
    for uid, rec in sorted(units.items()):
        f = rec["fields"]
        a = f.get("armor", "")
        af = armors.get(a, {}).get("fields", {})
        unit_rows.append([gname, "unit", uid, f.get("race", ""), f.get("rank", ""), a, af.get("spriteSheet", ""),
                          int(af.get("drawingRoutine", 0) or 0) if af else "", int(af.get("size", 1) or 1) if af else "",
                          jcell(f.get("livingWeapon")), f.get("spawnUnit", ""), ",".join(race_members.get(uid, [])[:5]),
                          src_mod("units", uid)])
    for sid, rec in sorted(soldiers.items()):
        f = rec["fields"]
        a = f.get("armor", "")
        af = armors.get(a, {}).get("fields", {})
        allowed = [aid for aid, ar in armors.items()
                   if sid in as_list(ar["fields"].get("units"))]
        unit_rows.append([gname, "soldier", sid, "", "", a, af.get("spriteSheet", ""),
                          int(af.get("drawingRoutine", 0) or 0) if af else "", int(af.get("size", 1) or 1) if af else "",
                          "", "", f"брони с units: {len(allowed)}; avatar {f.get('armorForAvatar', '')}", src_mod("soldiers", sid)])

    # ---------------- итоги
    used = [r for r in sheet_rows if r[2] == "да"]
    all_fp = [fp for n, fps in sheet_fp.items() for fp in fps.values() if sheet_users.get(n)]
    summary = dict(
        armors=len(armors), units=len(units), soldiers=len(soldiers),
        sheets_used=len(used), sheets_unused=len(sheet_rows) - len(used),
        frames_total=sum(r[7] for r in used), frames_nonempty=sum(r[9] for r in used),
        unique_frames=len({fp[0] for fp in all_fp}), unique_silhouettes=len({fp[1] for fp in all_fp}),
        unique_recolor=len({fp[2] for fp in all_fp}),
        sheets_with_hd=sum(1 for r in used if r[19]), sheets_full_hd=sum(1 for r in used if r[19] and r[21] == 0 and r[9] > 0),
        frames_hd_covered=sum(r[20] for r in used), frames_hd_missing=sum(r[21] for r in used),
        hd_models=Counter(r[23] for r in used if r[19]).most_common(),
        hd_stale_sheets=[r[1] for r in used if r[25]],
        hd_low_iou=sorted([(n, round(w, 3), i) for gg, n, w, i in acc.get("iou", []) if gg == gname and w < 0.75],
                          key=lambda t: t[1]),
        hd_checked_sheets=sum(1 for gg, *_r in acc.get("iou", []) if gg == gname),
        sheets_without_hd=[r[1] for r in used if not r[19]],
        unused_sheets=[r[1] for r in sheet_rows if r[2] == "нет"],
        by_routine=Counter(r[4] for r in armor_rows).most_common(),
        by_size=Counter(r[6] for r in armor_rows).most_common(),
        sheets_by_routine=Counter(r[5] for r in used).most_common(),
        corpses=len(corpse_rows), corpse_floor_unique=len({r[8] for r in corpse_rows if r[8]}),
        corpse_big_unique=len({r[11] for r in corpse_rows if r[11]}),
        handob_frames=len(hs.frames), handob_vanilla=hs.vanilla, handob_used=len(hand_use), items_default_hand=default_hand,
        floorob_frames=len(shared_sets["FLOOROB.PCK"].frames), bigobs_frames=len(shared_sets["BIGOBS.PCK"].frames),
        shared_hd={n: [(m, i["count"]) for m, i in v] for n, v in shared_hd.items()},
        inv_images=len(inv_rows), inv_missing=sum(1 for r in inv_rows if r[6] == "НЕТ ПОВЕРХНОСТИ"),
        inv_unique_files=len({r[8] for r in inv_rows if r[8]}), inv_hd=sum(1 for r in inv_rows if r[9]),
        armors_with_layers=sum(1 for r in armor_rows if r[9]), armors_with_scripts=sum(1 for r in armor_rows if r[10]),
        families=fam_stats, plan=plan, mod_offsets=offsets, seconds=round(time.time() - t0, 1),
    )
    acc["sheets"] += sheet_rows
    acc["frames"] += frame_rows
    acc["families"] += fam_rows
    acc["pairs"] += pair_rows
    acc["armors"] += armor_rows
    acc["corpses"] += corpse_rows
    acc["handob"] += hand_rows
    acc["inv"] += inv_rows
    acc["units"] += unit_rows
    acc["summary"][gname] = summary
    print(f"   готово за {summary['seconds']} с: броней {len(armors)}, листов {len(sheet_rows)}, "
          f"кадров {summary['frames_total']}, уникальных {summary['unique_frames']}", flush=True)


# ------------------------------------------------------------------ семейства

def recolor_func(fa, fb, fpa, fpb, common):
    """Доля пикселей, которые объясняет ОДНА общая карта индексов A -> B на всём листе.
    Считается по кадрам с тем же номером и тем же силуэтом. Перекраска палитрой (рампы с
    разным усилением, R-166) - это функция цвета, даже если порядок цветов в кадре поменялся."""
    sa, sb = [], []
    for i in common:
        if fpa[i][1] != fpb[i][1]:
            continue
        a, b = fa[i], fb[i]
        if a.shape != b.shape:
            continue
        nz = a != 0
        sa.append(a[nz])
        sb.append(b[nz])
    if not sa:
        return 0.0, 0.0, 0
    va = np.concatenate(sa).astype(np.int32)
    vb = np.concatenate(sb).astype(np.int32)
    joint = np.bincount(va * 256 + vb, minlength=65536).reshape(256, 256)
    tot = joint.sum()
    ab = joint.max(axis=1).sum() / tot
    ba = joint.max(axis=0).sum() / tot
    return float(ab), float(ba), int(tot)


def families(gname, sheet_fp, sheet_frames, sheet_users, skel=0.90, near=0.50, func=0.98):
    """Связи листов по кадрам С ТЕМ ЖЕ НОМЕРОМ. Доли - от большего числа непустых кадров пары.

    Семейство F (рычаг экономии: рисуется основа, остальное выводится):
      копия            - >= 95 % кадров побайтно те же;
      почти копия      - >= 50 % кадров побайтно те же;
      перекраска       - силуэт тот же у >= 90 % кадров И одна карта индексов A->B (или B->A)
                         объясняет >= 98 % пикселей этих кадров.
    Каркас S (слабее): силуэт тот же у >= 90 % кадров - одно тело, нарисованное по-разному
      (типично для routine 0: ноги и руки общие у десятков тел); выводить нельзя, но позу и форму
      можно задавать общими."""
    names = sorted(n for n in sheet_fp if sheet_fp[n])
    pos = {n: i for i, n in enumerate(names)}
    nz = np.array([len(sheet_fp[n]) for n in names], np.int32)
    k = len(names)
    cnt = {}
    for key, col in (("exact", 0), ("mask", 1), ("recolor", 2)):
        inv = defaultdict(list)
        for n in names:
            p = pos[n]
            for i, fp in sheet_fp[n].items():
                inv[(i, fp[col])].append(p)
        m = np.zeros((k, k), np.int32)
        for lst in inv.values():
            if len(lst) > 1:
                a = np.array(lst)
                m[np.ix_(a, a)] += 1
        cnt[key] = m
    denom = np.maximum(np.maximum(nz[:, None], nz[None, :]), 1).astype(np.float32)
    rmask, rexact, rrec = cnt["mask"] / denom, cnt["exact"] / denom, cnt["recolor"] / denom

    class UF:
        def __init__(self, n):
            self.p = list(range(n))

        def find(self, x):
            while self.p[x] != x:
                self.p[x] = self.p[self.p[x]]
                x = self.p[x]
            return x

        def join(self, a, b):
            ra, rb = self.find(a), self.find(b)
            if ra != rb:
                self.p[ra] = rb

    fam, sk = UF(k), UF(k)
    info = {}
    iu, ju = np.triu_indices(k, 1)
    sel = (rmask[iu, ju] >= near) | (rexact[iu, ju] >= near)
    for a, b in zip(iu[sel], ju[sel]):
        na, nb = names[a], names[b]
        pm, pe, pr = float(rmask[a, b]), float(rexact[a, b]), float(rrec[a, b])
        fab = fba = 0.0
        if pm >= skel and pe < 0.95:
            common = set(sheet_fp[na]) & set(sheet_fp[nb])
            fab, fba, _tot = recolor_func(sheet_frames[na], sheet_frames[nb], sheet_fp[na], sheet_fp[nb], common)
        rel = relation(pm, pe, max(fab, fba), func)
        info[(a, b)] = (pm, pe, pr, fab, fba, rel)
        if pm >= skel:
            sk.join(a, b)
        if rel in ("копия", "почти копия", "перекраска"):
            fam.join(a, b)

    def pair(a, b):
        if a == b:
            return None
        if a < b:
            return info.get((a, b))
        v = info.get((b, a))
        return None if v is None else (v[0], v[1], v[2], v[4], v[3], v[5])

    def groups(uf):
        g = defaultdict(list)
        for i in range(k):
            g[uf.find(i)].append(i)
        out = [v for v in g.values() if len(v) > 1]
        out.sort(key=lambda v: (-len(v), names[v[0]]))
        return out

    def pick_base(g):
        # основа - лист, из которого выводится больше всего членов, затем больше броней и кадров
        def score(i):
            der = sum(1 for j in g if j != i and (pair(i, j) or (0, 0, 0, 0, 0, ""))[5] in
                      ("копия", "почти копия", "перекраска"))
            return (der, len(sheet_users.get(names[i], [])), int(nz[i]), -i)
        return max(g, key=score)

    rows = []
    member_frames = 0
    fam_groups = groups(fam)
    fam_base = {}
    for fid, g in enumerate(fam_groups, 1):
        base = pick_base(g)
        fam_base[fid] = names[base]
        for i in sorted(g, key=lambda i: (i != base, names[i])):
            p = pair(base, i)
            if i == base:
                rel = "основа"
            elif p is None:
                rel = "через другого члена"
            else:
                rel = p[5]
            if i != base:
                member_frames += int(nz[i])
            rows.append([gname, f"F{fid:03d}", len(g), names[base], names[i], rel, int(nz[i]),
                         f"{p[0]:.3f}" if p else "", f"{p[1]:.3f}" if p else "", f"{p[3]:.3f}" if p else "",
                         f"{p[4]:.3f}" if p else "", len(sheet_users.get(names[i], []))])
    sk_groups = groups(sk)
    for sid, g in enumerate(sk_groups, 1):
        base = max(g, key=lambda i: (len(sheet_users.get(names[i], [])), int(nz[i]), -i))
        for i in sorted(g, key=lambda i: (i != base, names[i])):
            p = pair(base, i)
            rows.append([gname, f"S{sid:03d}", len(g), names[base], names[i],
                         "основа каркаса" if i == base else (p[5] if p else "через другого члена"), int(nz[i]),
                         f"{p[0]:.3f}" if p else "", f"{p[1]:.3f}" if p else "", f"{p[3]:.3f}" if p else "",
                         f"{p[4]:.3f}" if p else "", len(sheet_users.get(names[i], []))])
    pair_rows = []
    for (a, b), (pm, pe, pr, fab, fba, rel) in sorted(info.items(), key=lambda kv: (-kv[1][0], -kv[1][1])):
        pair_rows.append([gname, names[a], names[b], f"{pm:.3f}", f"{pe:.3f}", f"{pr:.3f}",
                          f"{fab:.3f}" if fab else "", f"{fba:.3f}" if fba else "", rel])
    rel_count = Counter(v[5] for v in info.values())
    stats = dict(
        families=len(fam_groups), sheets_in_families=sum(len(g) for g in fam_groups),
        member_frames=member_frames,
        biggest=[(len(g), fam_base[fid]) for fid, g in enumerate(fam_groups[:15], 1)],
        skeletons=len(sk_groups), sheets_in_skeletons=sum(len(g) for g in sk_groups),
        biggest_skeletons=[(len(g), names[max(g, key=lambda i: (len(sheet_users.get(names[i], [])), int(nz[i])))])
                           for g in sk_groups[:10]],
        pair_relations=rel_count.most_common(),
    )
    return rows, pair_rows, stats


def relation(pm, pe, f, func=0.98):
    if pe >= 0.95:
        return "копия"
    if pe >= 0.50:
        return "почти копия"
    if pm >= 0.90 and f >= func:
        return "перекраска"
    if pm >= 0.90:
        return "тот же каркас, другой рисунок"
    return "частично тот же силуэт"


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--games", default="piratez,xcom1")
    ap.add_argument("--src", type=Path, default=ROOT / "src")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--verify-hd", type=int, default=6,
                    help="сколько кадров каждого HD-пака сверить с классикой по силуэту (0 - не сверять, -1 - все)")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    a.out.mkdir(parents=True, exist_ok=True)
    acc = defaultdict(list)
    acc["summary"] = {}
    gs = games()
    for gname in a.games.split(","):
        census_game(gname, gs[gname], a.src, acc, a.verify_hd)

    o = a.out
    write_tsv(o / "armors.tsv", ["game", "armor", "spriteSheet", "spriteInv", "drawingRoutine", "routine_name", "size",
                                 "corpseBattle", "corpseGeo", "layers", "scripts", "canHoldWeapon", "constantAnimation",
                                 "movementType", "colorGroups", "armor_units_field", "used_by_units", "used_by_soldiers",
                                 "source_mod", "touched_by"], acc["armors"])
    write_tsv(o / "sheets.tsv", ["game", "sheet", "used", "armors", "armor_examples", "routines", "sizes",
                                 "frames", "max_index_plus1", "nonempty", "empty", "unique_frames", "unique_silhouettes",
                                 "frame_size", "origin", "files", "file_mods", "palette",
                                 "hd_mods", "hd_frames", "hd_covers_nonempty", "hd_missing_nonempty", "hd_format", "hd_model",
                                 "hd_pack_date", "hd_stale", "hd_check", "hd_repo_copy", "hd_18plus", "errors",
                                 "family", "skeleton", "frames_to_draw"], acc["sheets"])
    write_tsv(o / "frames_summary.tsv", ["game", "sheet", "index", "exact", "mask", "recolor", "mirror_mask",
                                         "pixels", "colours", "hd"], acc["frames"])
    write_tsv(o / "families.tsv", ["game", "family", "members", "base", "sheet", "relation_to_base", "nonempty",
                                   "silhouette_match", "exact_match", "func_base_to_sheet", "func_sheet_to_base",
                                   "armors"], acc["families"])
    write_tsv(o / "family_pairs.tsv", ["game", "sheet_a", "sheet_b", "silhouette_match", "exact_match",
                                       "same_colour_order", "func_a_to_b", "func_b_to_a", "relation"], acc["pairs"])
    write_tsv(o / "corpses.tsv", ["game", "item", "battleType", "role", "owners", "owner_examples",
                                  "floorSprite", "floor_index", "floor_hash", "bigSprite", "big_index", "big_hash",
                                  "handSprite", "hand_index", "hd_floor", "hd_big", "source_mod"], acc["corpses"])
    write_tsv(o / "handob.tsv", ["game", "index", "frame", "exact", "mask", "items", "item_examples", "source", "hd"],
              acc["handob"])
    write_tsv(o / "inv.tsv", ["game", "surface", "kind", "armors", "armor_examples", "mod", "file", "size",
                              "file_hash", "hd_ui"], acc["inv"])
    write_tsv(o / "units.tsv", ["game", "kind", "type", "race", "rank", "armor", "spriteSheet", "drawingRoutine",
                                "size", "livingWeapon", "spawnUnit", "races_or_note", "source_mod"], acc["units"])
    with open(o / "summary.json", "w", encoding=ENC) as f:
        json.dump(acc["summary"], f, ensure_ascii=False, indent=1, default=str)
    for g, s in acc["summary"].items():
        print(f"\n## {g}")
        for k, v in s.items():
            if k not in ("mod_offsets",):
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

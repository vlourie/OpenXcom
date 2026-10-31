#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка photo_ui.Swapper без видеокарты (R-213): текстовая модель живёт в обычной RAM, на «карту»
(здесь - копия в RAM вместо переноса, put подменён) идут мелкие части на весь проход и большие блоки по
одному, на время своего forward; pin_memory нет. Модель - игрушечная, того же устройства: эмбеддинг,
список из 8 блоков (внутри блока свой список из 8 слоёв - он не второй уровень), голова, буфер; fp8
хранение, как у Painter. «На карте» - параметр, чей адрес не адрес его копии в RAM.

    tools/hdart/.venv/Scripts/python.exe tools/hdart/test_photo_swapper.py   (код 0 - всё верно)
"""
import inspect
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import torch  # noqa: E402
from diffusers.hooks import apply_layerwise_casting  # noqa: E402

import photo_ui  # noqa: E402

nn = torch.nn
RAM = set()     # адреса копий в RAM


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.inner = nn.ModuleList(nn.Linear(16, 16) for _ in range(8))
        self.norm = nn.LayerNorm(16)

    def forward(self, x):
        for lin in self.inner:
            x = lin(x)
        return self.norm(x)


class Toy(nn.Module):
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(32, 16)
        self.layers = nn.ModuleList(Block() for _ in range(8))
        self.head = nn.Linear(16, 32)
        self.register_buffer("scale", torch.ones(16))

    def forward(self, ids):
        x = self.embed(ids) * self.scale
        for b in self.layers:
            x = b(x)
        return self.head(x)


def on_card(module):
    """(сколько параметров модуля сейчас не своей копией в RAM, сколько всего)."""
    ps = list(module.parameters())
    return sum(1 for p in ps if p.data.data_ptr() not in RAM), len(ps)


def main():
    src = inspect.getsource(photo_ui.Swapper)
    assert "pin_memory(" not in src, "Swapper снова закрепляет RAM - это shared память карты (R-213)"

    torch.manual_seed(1)
    m = Toy()
    apply_layerwise_casting(m, storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.float32,
                            skip_modules_pattern=("embed", "norm", "head"))
    ids = torch.arange(4)
    with torch.no_grad():
        ref = m(ids)
    RAM.update(p.data.data_ptr() for p in m.parameters())
    photo_ui.Swapper.put = lambda self, t: t.clone()
    s = photo_ui.Swapper(m, torch)
    assert s.blocks == 8, f"блоков {s.blocks}, ждал 8 (внутренний список блока - не второй уровень)"
    assert s.rest and all(n.startswith(("embed.", "head.")) for n in s.rest), s.rest

    seen = []
    for b in m.layers:      # после хука Swapper: что на карте, пока работает блок
        b.register_forward_pre_hook(lambda mod, _a: seen.append(
            (on_card(mod), sum(1 for x in m.layers if on_card(x)[0]))))

    s.to_gpu()
    for part in (m.embed, m.head):
        got, total = on_card(part)
        assert got == total, "мелкие части не на карте"
    assert all(on_card(b)[0] == 0 for b in m.layers), "блоки на карте до прохода"
    with torch.no_grad():
        out = m(ids)
    assert torch.equal(out, ref), "проход с переносом весов дал другой ответ"
    assert len(seen) == 8 and all(c == t > 0 and n == 1 for (c, t), n in seen), \
        f"во время работы блок не на карте или на карте не один: {seen}"
    assert all(on_card(b)[0] == 0 for b in m.layers), "блок остался на карте после прохода"
    s.to_cpu()
    assert on_card(m)[0] == 0, "после to_cpu не всё своими копиями в RAM"
    print("Swapper: без pin_memory; 8 блоков по одному, мелкие части на проход, после прохода всё в RAM, "
          "ответ тот же - верно")
    return 0


if __name__ == "__main__":
    sys.exit(main())

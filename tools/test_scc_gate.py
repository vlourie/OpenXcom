# Проверка ворот конвейера SCC (tools/hdart/scc_gate.py, П-12 контракта адресации стен).
# Пилот URBAN проходит; разные n у кадра и его разрушенного вида, неполная петля, дверь с другим n, чужой слот -
# отказ. Контроль: ворота без правил (check, всегда пусто) этот тест не проходят.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import scc_gate as g

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rec(frames, typ, die=0, alt=0, door=0):
    b = bytearray(g.RECORD)
    fr = (list(frames) * 8)[:8] if len(frames) < 8 else frames
    b[0:8] = bytes(fr)
    b[g.F_TYPE], b[g.F_DIE], b[g.F_ALT], b[g.F_DOOR] = typ, die, alt, door
    return bytes(b)


def recs_of(raw):
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".MCD") as f:
        f.write(raw)
    try:
        return g.read_mcd(f.name)
    finally:
        os.unlink(f.name)


def refused(recs, text):
    addr, errors = g.parse_address(text)
    return bool(g.check(recs, addr)[0] or errors)


def main():
    ok = True

    def expect(name, cond):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + name)
        ok &= cond

    # синтетика: 0 пустая; 1 анимированная north-стена (кадры 1-4); 2 west-дверь (кадр 10) с alt 3 (кадр 11);
    # 4 north-стена (кадр 20) с die 5 (кадр 21); 5 разрушенный вид
    syn = recs_of(rec([0], 0) + bytes(rec([1, 2, 3, 4, 1, 2, 3, 4], 2)) + rec([10], 1, alt=3, door=1) + rec([11], 1)
                  + rec([20], 2, die=5) + rec([21], 2))
    V = "version: 1\nframes: "
    expect("петля целиком с одним n - проходит", not refused(syn, V + "1:north:6 2:north:6 3:north:6 4:north:6"))
    expect("петля не целиком - отказ", refused(syn, V + "1:north:6 2:north:6"))
    expect("петля с разным n - отказ", refused(syn, V + "1:north:6 2:north:6 3:north:6 4:north:5"))
    expect("дверь без разрешения второго состояния - проходит", not refused(syn, V + "10:west:6"))
    expect("дверь и второе состояние с одним n - проходит", not refused(syn, V + "10:west:6 11:west:6"))
    expect("дверь и второе состояние с разным n - отказ", refused(syn, V + "10:west:6 11:west:5"))
    expect("стена и разрушенный вид с разным n - отказ", refused(syn, V + "20:north:6 21:north:4"))
    expect("стена и разрушенный вид с одним n - проходит", not refused(syn, V + "20:north:6 21:north:6"))
    expect("чужой слот - отказ", refused(syn, V + "20:west:6"))
    expect("version 2 - отказ", refused(syn, "version: 2\nframes: 20:north:6"))
    # настоящий MCD URBAN Пираток: пилот и его разрушенные виды 74 / 75
    mcd = g.find_mcd("URBAN", ROOT)
    if mcd:
        urb = g.read_mcd(mcd)
        pilot = open(os.path.join(ROOT, "census", "maps", "addressing_syn", "pilot_address.txt"), encoding="utf-8-sig").read() \
            if os.path.exists(os.path.join(ROOT, "census", "maps", "addressing_syn", "pilot_address.txt")) \
            else V + "69:north:6 70:west:6\n"
        expect("пилот URBAN 69:north:6 70:west:6 - проходит", not refused(urb, pilot))
        expect("URBAN 69:north:6 и 74:north:4 (die 65 -> 70) - отказ", refused(urb, V + "69:north:6 70:west:6 74:north:4"))
        expect("URBAN 69:north:6 и 74:north:6 - проходит", not refused(urb, V + "69:north:6 70:west:6 74:north:6"))
        expect("URBAN 70:west:6 и 75:west:5 (die 66 -> 71) - отказ", refused(urb, V + "69:north:6 70:west:6 75:west:5"))
    else:
        print("skip URBAN: MCD не найден")
    # контроль: ворота без правил не отказывают ничему - тест обязан это поймать
    real = g.check
    g.check = lambda recs, addr: ([], [])
    ctl = refused(syn, V + "1:north:6 2:north:6")
    g.check = real
    expect("контроль: пустые ворота пропускают неполную петлю (значит тест чувствителен)", not ctl)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

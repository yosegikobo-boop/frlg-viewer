"""スマホ版の Python の入口。Pyodide の中で動く（ふつうの Python でも import できる）。

判断は frlg/core.py（PC 版と同じ）。ここは JavaScript とのやりとりだけ:
  - 引数は bytes・int・str。JavaScript の Uint8Array（JsProxy）も受け取れる
  - 返りは JSON の文字か ""（何もしない）
遊ぶゲームは1つなので、状態はこのモジュールに持つ（boot で作り直す）。
"""
import json
import random

from frlg.calc import nature_label
from frlg.core import Core
from frlg.rematch import Wins
from frlg.replace import Settings, settings_from_json
from frlg.rom import Rom, UnsupportedRom

_rom = None
_code = None
_core = None


def _b(x) -> bytes:
    """JavaScript の Uint8Array（JsProxy）・memoryview・bytes → bytes"""
    if x is None:
        return b""
    if hasattr(x, "to_py"):
        x = x.to_py()
    return bytes(x)


def _loads(s, kind):
    try:
        v = json.loads(s) if s else None
    except (TypeError, ValueError):
        return kind()
    return v if isinstance(v, kind) else kind()


def boot(rom, settings_json: str, wins_json: str, save_wins=None) -> str:
    """ROM と、覚えていた設定・勝った回数で始める。save_wins(JSON の文字) は勝った回数が変わるたびに呼ぶ"""
    global _rom, _code, _core
    _rom = _code = _core = None
    try:
        r = Rom(_b(rom))
    except (UnsupportedRom, IndexError, ValueError):
        return json.dumps({"ok": False})
    s = settings_from_json(_loads(settings_json, dict))
    s.enabled = False                   # 起動直後はいつも OFF（PC 版と同じ）
    on_change = (lambda d: save_wins(json.dumps(d, ensure_ascii=False))) if save_wins else None
    _rom, _code = r, r.game_code
    _core = Core(s, Wins(data=_loads(wins_json, dict), on_change=on_change), random.Random())
    return json.dumps({
        "ok": True, "code": _code, "game": r.game_name, "settings": s.to_json(),
        "species": [{"no": n, "name": r.species_name(r.national_to_internal(n))} for n in range(1, 387)],
        "natures": [{"id": i, "label": nature_label(i)} for i in range(25)],
        "exp_ok": _core.exp_hook(r) is not None,
    }, ensure_ascii=False)


def set_settings(settings_json: str) -> str:
    """設定を変える。clear: 作った差し替えを取り消す（倍率のほかが変わった）、exp: ROM に書き直すもの"""
    if _core is None:
        return json.dumps({"settings": Settings().to_json(), "clear": False, "exp": []})
    old, new = _core.settings, settings_from_json(_loads(settings_json, dict))
    _core.settings = new
    a, b = old.to_json(), new.to_json()
    a.pop("exp_rate")
    b.pop("exp_rate")
    exp = _core.exp_writes(_rom, only_factor=True) if new.exp_rate != old.exp_rate else []
    return json.dumps({"settings": new.to_json(), "clear": a != b,
                       "exp": [[addr, data.hex()] for addr, data in exp]}, ensure_ascii=False)


def exp_writes() -> str:
    """経験値の倍率のために、ゲームの中の ROM に書くもの全部 [[番地, hex], ...]"""
    if _core is None:
        return "[]"
    return json.dumps([[addr, data.hex()] for addr, data in _core.exp_writes(_rom)])


def state(party, count: int, enemy, inb: int, boxes, cur_box: int, box_sel: int) -> str:
    """画面のカード。boxes が空なら箱は出さない。box_sel が -1 なら今の箱"""
    if _core is None:
        return json.dumps({"party": [], "enemy": [], "box": None, "box_cards": []})
    bx = _b(boxes)
    out = _core.cards(_rom, _b(party), int(count), enemy=_b(enemy) if inb else None,
                      boxes=(int(cur_box), bx) if bx else None, box=None if box_sel < 0 else int(box_sel))
    return json.dumps(out, ensure_ascii=False)


def enemy_new(data, flags: int, opp: int, player: int) -> str:
    """戦闘が始まった瞬間。書くなら {"pid", "mask", "hex"}"""
    if _core is None:
        return ""
    r = _core.enemy_new(_rom, _code, _b(data), int(flags), int(opp), int(player))
    if r is None:
        return ""
    pid, mask, new = r
    return json.dumps({"pid": pid, "mask": mask, "hex": new.hex()})


def party_first(data) -> str:
    """手持ちが 0→1。書くなら {"addr", "pid", "hex"}"""
    if _core is None:
        return ""
    r = _core.party_first(_rom, _code, _b(data))
    if r is None:
        return ""
    addr, pid, new = r
    return json.dumps({"addr": addr, "pid": pid, "hex": new.hex()})


def battle_end(flags: int, opp: int, outcome: int, player: int) -> None:
    if _core is not None:
        _core.battle_end(_code, int(flags), int(opp), int(outcome), int(player))


def map_entered(scripts: str, tflags, player: int) -> str:
    """別の場所に入った。scripts は人ごとの台本の頭（hex）を「,」でつないだもの（PC 版の Lua と同じ形）"""
    if _core is None:
        return "[]"
    parts = []
    for h in (scripts or "").split(","):
        try:
            parts.append(bytes.fromhex(h))
        except ValueError:
            parts.append(b"")
    return json.dumps(_core.map_entered(_rom, _code, parts, _b(tflags), int(player)))

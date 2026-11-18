"""能力値・性格・個性値さがし・覚えている技"""
from .pk3 import is_shiny

# 能力の位置: 0=HP 1=こうげき 2=ぼうぎょ 3=すばやさ 4=とくこう 5=とくぼう
STAT_NAMES = ["HP", "こうげき", "ぼうぎょ", "すばやさ", "とくこう", "とくぼう"]

_NATURE_NAMES = ["がんばりや", "さみしがり", "ゆうかん", "いじっぱり", "やんちゃ",
                 "ずぶとい", "すなお", "のんき", "わんぱく", "のうてんき",
                 "おくびょう", "せっかち", "まじめ", "ようき", "むじゃき",
                 "ひかえめ", "おっとり", "れいせい", "てれや", "うっかりや",
                 "おだやか", "おとなしい", "なまいき", "しんちょう", "きまぐれ"]


def nature_effect(n: int):
    """(上がる能力の位置, 下がる能力の位置)。補正なしは (None, None)"""
    up, down = n // 5 + 1, n % 5 + 1
    return (None, None) if up == down else (up, down)


NATURES = [(name, *nature_effect(i)) for i, name in enumerate(_NATURE_NAMES)]


def nature_label(n: int) -> str:
    name, up, down = NATURES[n]
    if up is None:
        return f"{name}　へんかなし"
    return f"{name}　{STAT_NAMES[up]}↑ {STAT_NAMES[down]}↓"


def calc_stats(base, ivs, evs, level, nature) -> list:
    """base は6つの数か BaseStats。返すのは 最大HP・攻・防・素早・特攻・特防"""
    b = base.stats if hasattr(base, "stats") else list(base)
    _, up, down = NATURES[nature]
    out = []
    for i in range(6):
        x = (2 * b[i] + ivs[i] + evs[i] // 4) * level // 100
        if i == 0:
            out.append(1 if b[0] == 1 else x + level + 10)   # ヌケニンは HP 1
        else:
            v = x + 5
            if i == up:
                v = v * 110 // 100
            elif i == down:
                v = v * 90 // 100
            out.append(v)
    return out


def level_moves(learnset, level) -> list:
    """そのレベルまでに覚える技を、ゲームと同じく古いものから押し出して最後の4つ"""
    moves = []
    for lv, m in learnset:
        if lv > level:
            break
        if m in moves:
            continue
        if len(moves) == 4:
            moves.pop(0)
        moves.append(m)
    return moves


MAX_TRIES = 100000


def gender_of(pid: int, ratio: int):
    """性別。ratio は種族の表のメスになりやすさ（0 オスだけ、254 メスだけ、255 性別なし）。
    それ以外は 個性値の下の1バイト < ratio ならメス"""
    if ratio == 255:
        return None
    if ratio == 0:
        return "male"
    if ratio == 254:
        return "female"
    return "female" if (pid & 0xFF) < ratio else "male"


def can_choose_gender(ratio: int) -> bool:
    return ratio not in (0, 254, 255)


def find_pid(otid, want_shiny: bool, want_nature, rng, want_gender=None, gender_ratio=255) -> int:
    """色違いかどうか・性格（pid % 25）・性別に合う個性値をさがす。
    色違いは下の16ビットから上の16ビットを逆算して作れる。
    性別は、オスかメスのどちらにもなれる種族のときだけ合わせる。
    見つからなければ色違いを優先して性格・性別をあきらめる（実際には起きない）"""
    if not can_choose_gender(gender_ratio):
        want_gender = None
    tid_sid = (otid & 0xFFFF) ^ (otid >> 16)
    last = None
    for _ in range(MAX_TRIES):
        lo = rng.getrandbits(16)
        if want_shiny:
            hi = tid_sid ^ lo ^ rng.randrange(8)
        else:
            hi = rng.getrandbits(16)
        pid = (hi << 16) | lo
        if is_shiny(pid, otid) != want_shiny:
            continue
        last = pid
        if want_nature is not None and pid % 25 != want_nature:
            continue
        if want_gender is not None and gender_of(pid, gender_ratio) != want_gender:
            continue
        return pid
    return last

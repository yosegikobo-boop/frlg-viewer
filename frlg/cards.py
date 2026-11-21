"""ポケモンのデータ → 画面のカード"""
from .addresses import PARTY_SIZE, BOX_MON_SIZE, BOXES, BOX_SLOTS
from .calc import NATURES, nature_label, gender_of, calc_stats
from .pk3 import decode_pk3, is_shiny
from .text import decode_text


def status_label(status: int):
    """状態異常の名前。なければ None"""
    if status & 7:
        return "ねむり"
    for bit, name in ((7, "もうどく"), (3, "どく"), (4, "やけど"), (5, "こおり"), (6, "まひ")):
        if status & (1 << bit):
            return name
    return None


def card(p, rom, party: bool):
    if p.is_empty or not p.checksum_ok or p.species >= 412:
        return None
    base = rom.base_stats(p.species)
    level = p.level if party else rom.level_for_exp(base.growth_rate, p.exp)
    n = p.pid % 25
    if party:      # 手持ち・戦っている相手は、ゲームが計算した今の値
        stats, hp, status = p.stats, p.cur_hp, status_label(p.status)
    else:          # ボックスは能力値を持っていないので計算する（HP はいっぱい）
        stats = calc_stats(base, p.ivs, p.evs, level, n)
        hp, status = stats[0], None
    ability = base.abilities[p.ability_bit] or base.abilities[0]
    return {
        "no": rom.internal_to_national(p.species),
        "name": decode_text(p.nickname_raw),
        "species_name": rom.species_name(p.species),
        "level": level,
        "egg": p.is_egg,
        "nature_label": nature_label(n),
        "nature_up": NATURES[n][1],
        "nature_down": NATURES[n][2],
        "ability": rom.ability_name(ability),
        "ivs": p.ivs,
        "evs": p.evs,
        "shiny": is_shiny(p.pid, p.otid),
        "gender": gender_of(p.pid, base.gender_ratio),
        "stats": stats,
        "hp": hp,
        "max_hp": stats[0],
        "status": status,
        "item": rom.item_name(p.item) if p.item else None,
    }


def species_choices(rom):
    """設定の画面の種族の一覧（全国図鑑の順）。abilities はとくせいの名前（2つ目が無ければ None）"""
    out = []
    for n in range(1, 387):
        sp = rom.national_to_internal(n)
        a = rom.base_stats(sp).abilities
        out.append({"no": n, "name": rom.species_name(sp),
                    "abilities": [rom.ability_name(a[0]), rom.ability_name(a[1]) if a[1] else None]})
    return out


def party_cards(data: bytes, rom, count: int = 6):
    out = []
    for i in range(min(count, 6)):
        c = card(decode_pk3(data[i * PARTY_SIZE:(i + 1) * PARTY_SIZE]), rom, True)
        if c:
            out.append(c)
    return out


def box_cards(data: bytes, rom, box: int):
    out = []
    if not 0 <= box < BOXES:
        return out
    for i in range(BOX_SLOTS):
        o = (box * BOX_SLOTS + i) * BOX_MON_SIZE
        c = card(decode_pk3(data[o:o + BOX_MON_SIZE]), rom, False)
        if c:
            out.append(c)
    return out

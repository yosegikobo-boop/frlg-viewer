"""差し替えるかの判断と、差し替える1匹を作る"""
from dataclasses import dataclass, asdict

from .addresses import DENY_MASK
from .calc import calc_stats, find_pid, level_moves, can_choose_gender, gender_of
from .pk3 import Pk3
from .text import encode_text

FATEFUL_NATIONAL = (151, 386)   # ミュウ・デオキシスは配布の印がないと言うことを聞かない


@dataclass
class Settings:
    enabled: bool = False
    species: int = None     # 全国図鑑の番号。None なら元のまま
    level: int = None
    max_ivs: bool = False
    shiny: bool = False
    nature: int = None      # 0〜24。None なら元のまま
    starter: int = None     # 最初のポケモン（全国図鑑の番号）
    exp_rate: float = 1.0   # 経験値の倍率 1.0〜5.0（0.5刻み）。スイッチとは別
    gender: str = None      # "male"・"female"。None なら元のまま（2026-11-15）
    rematch: bool = True    # トレーナーと何度でも戦う・再戦で強くなる（2026-11-17）。スイッチとは別

    def to_json(self):
        return asdict(self)


def _int_or_none(v, lo, hi):
    if v is None or v == "":
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n < lo:
        return None
    return min(n, hi) if hi == 100 else (n if n <= hi else None)


def _exp_rate(v) -> float:
    try:
        r = round(float(v) * 2) / 2
    except (TypeError, ValueError):
        return 1.0
    return r if 1.0 <= r <= 5.0 else 1.0


def settings_from_json(j: dict) -> Settings:
    return Settings(
        enabled=bool(j.get("enabled", False)),
        species=_int_or_none(j.get("species"), 1, 386),
        level=_int_or_none(j.get("level"), 1, 100),
        max_ivs=bool(j.get("max_ivs", False)),
        shiny=bool(j.get("shiny", False)),
        nature=_int_or_none(j.get("nature"), 0, 24),
        starter=_int_or_none(j.get("starter"), 1, 386),
        exp_rate=_exp_rate(j.get("exp_rate", 1.0)),
        gender=j.get("gender") if j.get("gender") in ("male", "female") else None,
        rematch=bool(j.get("rematch", True)),
    )


def _wants_change(s: Settings) -> bool:
    return any((s.species, s.level, s.max_ivs, s.shiny, s.nature is not None, s.gender))


def should_replace(flags: int, settings: Settings) -> bool:
    return settings.enabled and _wants_change(settings) and (flags & DENY_MASK) == 0


def should_replace_starter(prev_count: int, count: int, settings: Settings) -> bool:
    return prev_count == 0 and count == 1 and settings.starter is not None


STARTER_NATIONAL = (1, 4, 7)   # 研究所でもらえる3匹


def is_starter_gift(p: Pk3, rom) -> bool:
    """もらったばかりの最初のポケモンか（Lv5 のフシギダネ・ヒトカゲ・ゼニガメ）。
    育てたポケモンを、ステートセーブの読み込みなどで間違えて差し替えないため"""
    return (rom.internal_to_national(p.species) in STARTER_NATIONAL and p.level == 5
            and p.exp == rom.exp_for_level(rom.base_stats(p.species).growth_rate, 5))


def _rebuild(orig: Pk3, sp: int, level: int, s: Settings, rom, rng) -> Pk3:
    p = orig.copy()
    changed_species = sp != orig.species
    base = rom.base_stats(sp)
    ratio = base.gender_ratio
    want_gender = s.gender if can_choose_gender(ratio) else None
    if want_gender and gender_of(p.pid, ratio) == want_gender and not s.shiny and s.nature is None:
        want_gender = None      # もうその性別なら、個性値はそのまま
    if s.shiny or s.nature is not None or want_gender:
        p.pid = find_pid(p.otid, want_shiny=s.shiny, want_nature=s.nature, rng=rng,
                         want_gender=want_gender, gender_ratio=ratio)
    if changed_species:
        p.species = sp
        p.item = 0
        p.nickname_raw = encode_text(rom.species_name(sp)) + b"\xff"
    if changed_species or level != orig.level:
        p.exp = rom.exp_for_level(base.growth_rate, level)
        moves = level_moves(rom.learnset(sp), level)
        p.moves = moves + [0] * (4 - len(moves))
        p.pp = [rom.move_pp(m) if m else 0 for m in p.moves]
        p.pp_bonuses = 0
    if s.max_ivs:
        p.ivs = [31] * 6
    if p.pid != orig.pid or changed_species:
        p.ability_bit = (p.pid & 1) if base.abilities[1] else 0
    if rom.internal_to_national(sp) in FATEFUL_NATIONAL:
        p.fateful = True
    p.level = level
    p.stats = calc_stats(base, p.ivs, p.evs, level, p.pid % 25)
    p.cur_hp = p.stats[0]
    p.status = 0
    return p


def build_replacement(orig: Pk3, settings: Settings, rom, rng) -> Pk3:
    sp = rom.national_to_internal(settings.species) if settings.species else orig.species
    level = settings.level or orig.level
    return _rebuild(orig, sp, level, settings, rom, rng)


def build_starter(orig: Pk3, settings: Settings, rom, rng) -> Pk3:
    return _rebuild(orig, rom.national_to_internal(settings.starter), orig.level, settings, rom, rng)

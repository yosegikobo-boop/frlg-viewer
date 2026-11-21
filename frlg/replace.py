"""差し替えるかの判断と、差し替える1匹を作る"""
from dataclasses import dataclass, asdict

from .addresses import DENY_MASK
from .calc import calc_stats, find_pid, level_moves, can_choose_gender, gender_of
from .pk3 import Pk3, is_shiny
from .text import encode_text

ITEM_MODES = ("common", "rare")
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
    ability: int = None     # とくせい 0（1つ目）・1（2つ目）。None なら元のまま（2026-11-21）
    item: str = None        # 野生の持ち物 "common"（よく持つ）・"rare"（たまに持つ）。None なら元のまま

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
        ability=_int_or_none(j.get("ability"), 0, 1),
        item=j.get("item") if j.get("item") in ITEM_MODES else None,
    )


def _wants_change(s: Settings) -> bool:
    return any((s.species, s.level, s.max_ivs, s.shiny, s.nature is not None, s.gender,
                s.ability is not None, s.item))


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


def held_item(items: tuple, mode, rng=None) -> int:
    """持たせる道具。mode が "common"・"rare" なら、そのほう（無ければもう片方）。
    None ならゲームと同じ確率（2つ同じならいつも、ほかは よく持つ 50%・たまに持つ 5%）"""
    common, rare = items
    if mode == "common":
        return common or rare
    if mode == "rare":
        return rare or common
    if common == rare:
        return common
    r = rng.randrange(100)
    return 0 if r < 45 else common if r < 95 else rare


def _rebuild(orig: Pk3, sp: int, level: int, s: Settings, rom, rng) -> Pk3:
    p = orig.copy()
    changed_species = sp != orig.species
    base = rom.base_stats(sp)
    ratio = base.gender_ratio
    want_gender = s.gender if can_choose_gender(ratio) else None
    want_ability = s.ability if base.abilities[1] else None   # とくせいが1つなら選べない
    # 色違い・性格は選んだら探し直す。性別・とくせいは今と違うときだけ。
    # 探すときは、選んだものを全部合わせる（性別だけ合っていても、とくせいのために探すなら外さない）
    if (s.shiny or s.nature is not None
            or (want_gender and gender_of(p.pid, ratio) != want_gender)
            or (want_ability is not None and p.pid & 1 != want_ability)):
        # 色違いを選んでいなくても、たまたま色違いだった野生は色違いのままにする
        p.pid = find_pid(p.otid, want_shiny=s.shiny or is_shiny(orig.pid, orig.otid), want_nature=s.nature, rng=rng,
                         want_gender=want_gender, gender_ratio=ratio, want_ability=want_ability)
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
    if p.pid != orig.pid or changed_species or want_ability is not None:
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
    p = _rebuild(orig, sp, level, settings, rom, rng)
    if settings.item or sp != orig.species:     # 種族を変えないで「元のまま」なら、ゲームが決めた持ち物のまま
        p.item = held_item(rom.base_stats(sp).items, settings.item, rng)
    return p


def build_starter(orig: Pk3, settings: Settings, rom, rng) -> Pk3:
    return _rebuild(orig, rom.national_to_internal(settings.starter), orig.level, settings, rom, rng)

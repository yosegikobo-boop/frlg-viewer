"""トレーナーと何度でも戦う（2026-11-17）

- 別の場所（道路・町・建物）から入ってきたら、その場所のトレーナーの「勝った印」を消す。
  消されたトレーナーは初めて会ったときと同じに、目が合うと戦いに来る。話しかけても戦える
- 勝った回数を数えて、再戦のたびに相手のポケモンを強くする（1回ごとに Lv+2、技はそのレベルのもの、
  レベルで進化する。石・通信交換・なつき度などで進化するものは Lv40 で進化）。個体値は変えない
- 印を消すのは、ふつうのトレーナーとジムリーダーだけ。ライバル・四天王・チャンピオン・ロケット団は消さない
  （四天王はゲームが自分で戦い直せるようにする。強くはなる）
"""
import json
import os
import struct
import threading

from .calc import calc_stats, level_moves
from .pk3 import decode_pk3, encode_pk3
from .text import encode_text

# セーブの1つめの塊（SaveBlock1）の中の場所。ROM の頭の表（0x150 に flags 0xEE0）で確かめた
FLAGS_OFFSET = 0xEE0
TEMPLATES_OFFSET = 0x8E0     # 今いる場所の人の決まり（64人 × 0x18バイト）。印のすぐ前
NUM_TEMPLATES = 64
TEMPLATE_SIZE = 0x18
TEMPLATE_SCRIPT = 0x10       # 話しかけたときの台本の場所（u32）
TRAINER_FLAGS_START = 0x500  # トレーナー n の「勝った印」は 0x500 + n 番
TRAINER_FLAG_BYTES = (743 + 7) // 8

LEVEL_STEP = 2               # 再戦1回ごとに上がるレベル
OTHER_EVO_LEVEL = 40         # 石・通信交換・なつき度・うつくしさで進化するもの
MAX_LEVEL = 100

# トレーナーの種類
CLASS_RIVAL_EARLY = 0x51
CLASS_BOSS = 0x53
CLASS_LEADER = 0x54
CLASS_ROCKET = 0x55
CLASS_ELITE_FOUR = 0x57
CLASS_RIVAL_LATE = 0x59
CLASS_CHAMPION = 0x5A
NO_REVIVE = {CLASS_RIVAL_EARLY, CLASS_BOSS, CLASS_ROCKET, CLASS_ELITE_FOUR,
             CLASS_RIVAL_LATE, CLASS_CHAMPION}
NO_GROW = {CLASS_RIVAL_EARLY, CLASS_BOSS, CLASS_ROCKET, CLASS_RIVAL_LATE, CLASS_CHAMPION}

# trainerbattle の種類。0 ふつう・4 ダブル は、勝ったあとに話を進める処理がない
PLAIN_TYPES = {0, 4}
# ジムリーダーは勝ったあとにバッジを渡す処理（1・2・6・8）。もう一度渡しても困らない
LEADER_TYPES = {0, 1, 2, 4, 6, 8}

# 進化のしかた
EVO_LEVEL = 4
EVO_ATK_GT_DEF, EVO_ATK_EQ_DEF, EVO_ATK_LT_DEF = 8, 9, 10
EVO_SILCOON, EVO_CASCOON = 11, 12
EVO_NINJASK, EVO_SHEDINJA = 13, 14
LEVEL_METHODS = {EVO_LEVEL, EVO_ATK_GT_DEF, EVO_ATK_EQ_DEF, EVO_ATK_LT_DEF,
                 EVO_SILCOON, EVO_CASCOON, EVO_NINJASK}

BT_TRAINER = 1 << 3
OUTCOME_WON = 1


def script_trainer(script: bytes):
    """台本の頭から (trainerbattle の種類, トレーナーの番号)。トレーナーの台本でなければ None。
    ジムリーダーの台本は前に setvar・special（思い出の記録用）が付いているので読み飛ばす"""
    i = 0
    while i < len(script):
        op = script[i]
        if op == 0x5C:
            if i + 4 > len(script):
                return None
            return script[i + 1], struct.unpack_from("<H", script, i + 2)[0]
        if op == 0x16:       # setvar var, value
            i += 5
        elif op == 0x25:     # special n
            i += 3
        elif op in (0x6A, 0x5A):   # lock, faceplayer
            i += 1
        else:
            return None
    return None


def revivable(rom, script: bytes):
    """印を消してよいトレーナーの番号。だめなら None"""
    t = script_trainer(script)
    if t is None:
        return None
    btype, tid = t
    cls = rom.trainer_class(tid)
    if cls < 0 or cls in NO_REVIVE:
        return None
    allowed = LEADER_TYPES if cls == CLASS_LEADER else PLAIN_TYPES
    return tid if btype in allowed else None


def flag_is_set(flag_bytes: bytes, tid: int) -> bool:
    """flag_bytes はトレーナーの印（0x500 番から）の部分"""
    i = tid // 8
    return i < len(flag_bytes) and bool(flag_bytes[i] >> (tid % 8) & 1)


def evolve_once(rom, sp: int, level: int, pid: int, atk: int, df: int):
    """このレベルで進化する先。進化しないなら None"""
    evos = rom.evolutions(sp)
    for method, param, target in evos:
        if method not in LEVEL_METHODS or level < param:
            continue
        if method == EVO_ATK_GT_DEF and not atk > df:
            continue
        if method == EVO_ATK_EQ_DEF and not atk == df:
            continue
        if method == EVO_ATK_LT_DEF and not atk < df:
            continue
        if method in (EVO_SILCOON, EVO_CASCOON):
            silcoon = (pid >> 16) % 10 <= 4
            if silcoon != (method == EVO_SILCOON):
                continue
        return target
    others = [t for m, _, t in evos if m not in LEVEL_METHODS and m != EVO_SHEDINJA]
    if others and level >= OTHER_EVO_LEVEL:
        return others[pid % len(others)]      # イーブイなど、いくつかあるときは個性値で決める
    return None


def grow_mon(p, wins: int, rom):
    """勝った回数 wins に合わせて強くした1匹（Pk3）。個体値・努力値・性格・持ち物はそのまま"""
    q = p.copy()
    level = min(MAX_LEVEL, p.level + LEVEL_STEP * wins)
    sp = p.species
    for _ in range(3):
        base = rom.base_stats(sp)
        st = calc_stats(base, q.ivs, q.evs, level, q.pid % 25)
        nxt = evolve_once(rom, sp, level, q.pid, st[1], st[2])
        if not nxt:
            break
        sp = nxt
    base = rom.base_stats(sp)
    if sp != p.species:
        q.species = sp
        q.nickname_raw = encode_text(rom.species_name(sp)) + b"\xff"
        if not base.abilities[1]:
            q.ability_bit = 0
    q.exp = rom.exp_for_level(base.growth_rate, level)
    moves = level_moves(rom.learnset(sp), level)
    q.moves = moves + [0] * (4 - len(moves))
    q.pp = [rom.move_pp(m) if m else 0 for m in q.moves]
    q.pp_bonuses = 0
    q.level = level
    q.stats = calc_stats(base, q.ivs, q.evs, level, q.pid % 25)
    q.cur_hp = q.stats[0]
    q.status = 0
    return q


def grow_party(data: bytes, wins: int, rom):
    """相手のパーティ（100バイト × 6）を強くしたもの。変えるものがなければ None"""
    if wins <= 0:
        return None
    out = bytearray(data)
    changed = False
    for i in range(len(data) // 100):
        chunk = data[i * 100:(i + 1) * 100]
        p = decode_pk3(chunk)
        if p.pid == 0 and p.otid == 0 or p.is_empty or not p.checksum_ok or p.is_egg:
            continue
        out[i * 100:(i + 1) * 100] = encode_pk3(grow_mon(p, wins, rom), party=True)
        changed = True
    return bytes(out) if changed else None


def can_grow(rom, tid: int) -> bool:
    cls = rom.trainer_class(tid)
    return cls >= 0 and cls not in NO_GROW


class Wins:
    """トレーナーに勝った回数。セーブ（ゲームと主人公の ID）ごとに覚える"""

    def __init__(self, path=None, data: dict = None, on_change=None):
        """path があればファイルに覚える。無ければ data から始めて、変わるたびに on_change(中身) を呼ぶ（スマホ版）"""
        self.path = path
        self.on_change = on_change
        self._lock = threading.Lock()
        self._d = {}
        if path is None:
            if isinstance(data, dict):
                self._d = {k: dict(v) for k, v in data.items() if isinstance(v, dict)}
            return
        try:
            with open(path, encoding="utf-8-sig") as f:   # 手で直して BOM が付いても読める
                self._d = json.load(f)
            if not isinstance(self._d, dict):
                self._d = {}
        except (OSError, ValueError):
            self._d = {}

    @staticmethod
    def _key(code, player):
        return "%s:%08x" % (code, player & 0xFFFFFFFF)

    def get(self, code, player, tid) -> int:
        with self._lock:
            return int(self._d.get(self._key(code, player), {}).get(str(tid), 0))

    def add(self, code, player, tid, n=1):
        with self._lock:
            d = self._d.setdefault(self._key(code, player), {})
            d[str(tid)] = int(d.get(str(tid), 0)) + n
            self._save()

    def seed(self, code, player, tids):
        """機能を入れる前に勝っていたトレーナーは、1回勝ったことにする"""
        with self._lock:
            d = self._d.setdefault(self._key(code, player), {})
            changed = False
            for t in tids:
                if int(d.get(str(t), 0)) == 0:
                    d[str(t)] = 1
                    changed = True
            if changed:
                self._save()

    def _save(self):
        if self.path is None:
            if self.on_change:
                self.on_change({k: dict(v) for k, v in self._d.items()})
            return
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

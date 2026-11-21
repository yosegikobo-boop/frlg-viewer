"""ROM の表を、中身の並びで探して読む（場所は決め打ちしない）"""
import struct
from dataclasses import dataclass

from .text import decode_text, encode_text

SUPPORTED = {"BPRJ": "ファイアレッド", "BPGJ": "リーフグリーン"}

NAME_LEN = 6        # 名前 5文字 + 終わり
MOVE_NAME_LEN = 8   # 技 7文字 + 終わり
ABILITY_NAME_LEN = 8
BASE_STATS_SIZE = 28
BATTLE_MOVE_SIZE = 12
NUM_SPECIES = 412   # 内部番号 0〜411
NUM_MOVES = 355
NUM_ABILITIES = 78
ITEM_SIZE = 40      # 道具の表（日本版）: 名前 10バイト、+10 に道具の番号
ITEM_NAME_LEN = 10
NUM_ITEMS = 375
TRAINER_SIZE = 32   # 日本版は名前が短いので 32バイト（海外版は 40）
NUM_TRAINERS = 743
TRAINER_BROCK = 414
EVO_SIZE = 8        # 進化のしかた・条件・進化先・空き（u16 ×4）
EVOS_PER_SPECIES = 5


@dataclass(frozen=True)
class BaseStats:
    hp: int
    atk: int
    df: int
    spe: int
    spa: int
    spd: int
    types: tuple
    gender_ratio: int
    growth_rate: int
    abilities: tuple
    items: tuple = (0, 0)   # 野生が持つ道具（よく持つ 50%, たまに持つ 5%）。2つ同じなら いつも

    @property
    def stats(self):
        """HP・攻・防・素早・特攻・特防の順"""
        return [self.hp, self.atk, self.df, self.spe, self.spa, self.spd]


class UnsupportedRom(Exception):
    pass


def _find(data: bytes, pattern: bytes, what: str) -> int:
    i = data.find(pattern)
    if i < 0:
        raise UnsupportedRom(f"{what} が見つからない")
    return i


class Rom:
    def __init__(self, data: bytes):
        self.data = data
        self.game_code = data[0xAC:0xB0].decode("ascii", "replace")
        if self.game_code not in SUPPORTED or data[0xBC] != 0:
            raise UnsupportedRom(f"対応していないROM: {self.game_code} 版{data[0xBC]}")
        d = data
        self.base_stats_at = _find(d, bytes([45, 49, 49, 45, 65, 65]), "種族の表") - BASE_STATS_SIZE
        self.species_names_at = _find(
            d, bytes([0xAC] * 5 + [0xFF, 0x6C, 0x5C, 0x88, 0x91, 0x68, 0xFF]), "名前の表")
        self.move_names_at = _find(
            d, bytes([0xAE] + [0xFF] * 7 + [0x1A, 0x10, 0x08, 0xFF]), "技の名前の表")
        self.ability_names_at = _find(
            d, bytes([0xAE] * 7 + [0xFF, 0x01, 0x08, 0x0C, 0x35, 0x03, 0xFF]), "特性の名前の表")
        self.exp_at = _find(d, struct.pack("<6I", 0, 1, 8, 27, 64, 125), "経験値の表")
        self.dex_at = _find(d, struct.pack("<251H", *range(1, 252)), "図鑑番号の表")
        # はたく: 威力40 ノーマル 命中100 PP35
        self.battle_moves_at = _find(d, bytes([0, 40, 0, 100, 35]), "技の表") - BATTLE_MOVE_SIZE
        bulba = _find(d, bytes.fromhex("21022d08490e"), "覚える技")
        # 表の0番（なし）と1番（フシギダネ）は、どちらもフシギダネの覚える技を指す
        self.learnset_ptrs_at = _find(d, struct.pack("<I", 0x08000000 + bulba) * 2, "覚える技の表")
        # タケシ（414番）: 技を決めたパーティ・ジムリーダー・タケシの名前（日本版）
        brock = _find(d, bytes.fromhex("01540074605 95cff".replace(" ", "")), "トレーナーの表")
        self.trainers_at = brock - TRAINER_BROCK * TRAINER_SIZE
        # フシギダネ: Lv16 でフシギソウ、フシギソウ: Lv32 でフシギバナ
        self.evolutions_at = _find(
            d, struct.pack("<4H", 4, 16, 2, 0) + bytes(32) + struct.pack("<4H", 4, 32, 3, 0),
            "進化の表") - EVO_SIZE * EVOS_PER_SPECIES
        master = _find(d, encode_text("マスターボール") + b"\xff", "道具の表")
        if struct.unpack_from("<H", d, master + ITEM_NAME_LEN)[0] != 1:
            raise UnsupportedRom("道具の表 が見つからない")
        self.items_at = master - ITEM_SIZE
        self._dex = struct.unpack_from("<%dH" % (NUM_SPECIES - 1), d, self.dex_at)
        self._nat2int = {n: i + 1 for i, n in enumerate(self._dex) if 1 <= n <= 386}

    @classmethod
    def open(cls, path) -> "Rom":
        with open(path, "rb") as f:
            return cls(f.read())

    @property
    def game_name(self) -> str:
        return SUPPORTED[self.game_code]

    def species_name(self, sp: int) -> str:
        o = self.species_names_at + sp * NAME_LEN
        return decode_text(self.data[o:o + NAME_LEN])

    def move_name(self, m: int) -> str:
        o = self.move_names_at + m * MOVE_NAME_LEN
        return decode_text(self.data[o:o + MOVE_NAME_LEN])

    def ability_name(self, a: int) -> str:
        o = self.ability_names_at + a * ABILITY_NAME_LEN
        return decode_text(self.data[o:o + ABILITY_NAME_LEN])

    def item_name(self, i: int):
        """道具の名前。道具でない番号（0・表の外）は None"""
        if not 0 < i < NUM_ITEMS:
            return None
        o = self.items_at + i * ITEM_SIZE
        if struct.unpack_from("<H", self.data, o + ITEM_NAME_LEN)[0] != i:
            return None
        return decode_text(self.data[o:o + ITEM_NAME_LEN])

    def move_pp(self, m: int) -> int:
        return self.data[self.battle_moves_at + m * BATTLE_MOVE_SIZE + 4]

    def base_stats(self, sp: int) -> BaseStats:
        o = self.base_stats_at + sp * BASE_STATS_SIZE
        b = self.data[o:o + BASE_STATS_SIZE]
        return BaseStats(b[0], b[1], b[2], b[3], b[4], b[5], (b[6], b[7]),
                         b[16], b[19], (b[22], b[23]), struct.unpack_from("<2H", b, 12))

    def learnset(self, sp: int) -> list:
        ptr = struct.unpack_from("<I", self.data, self.learnset_ptrs_at + sp * 4)[0] - 0x08000000
        out = []
        while True:
            v = struct.unpack_from("<H", self.data, ptr)[0]
            if v == 0xFFFF:
                return out
            out.append((v >> 9, v & 0x1FF))
            ptr += 2

    def exp_for_level(self, growth_rate: int, level: int) -> int:
        return struct.unpack_from("<I", self.data, self.exp_at + (growth_rate * 101 + level) * 4)[0]

    def level_for_exp(self, growth_rate: int, exp: int) -> int:
        lv = 1
        while lv < 100 and self.exp_for_level(growth_rate, lv + 1) <= exp:
            lv += 1
        return lv

    def national_to_internal(self, n: int) -> int:
        return self._nat2int[n]

    def internal_to_national(self, sp: int) -> int:
        if sp <= 0 or sp >= NUM_SPECIES:
            return 0
        return self._dex[sp - 1]

    def trainer_class(self, tid: int) -> int:
        """トレーナーの種類（ジムリーダー 0x54 など）。番号の外なら -1"""
        if not 0 < tid < NUM_TRAINERS:
            return -1
        return self.data[self.trainers_at + tid * TRAINER_SIZE + 1]

    def evolutions(self, sp: int) -> list:
        """[(進化のしかた, 条件, 進化先)]。しかた: 4=レベル 7=石 5=通信交換 など"""
        out = []
        for i in range(EVOS_PER_SPECIES):
            method, param, target = struct.unpack_from(
                "<3H", self.data, self.evolutions_at + (sp * EVOS_PER_SPECIES + i) * EVO_SIZE)
            if method:
                out.append((method, param, target))
        return out

    def trainer_party_species(self, tid: int) -> list:
        """ROM の表にあるトレーナーの手持ちの種族（順番どおり）"""
        if not 0 < tid < NUM_TRAINERS:
            return []
        o = self.trainers_at + tid * TRAINER_SIZE
        flags = self.data[o]
        size = self.data[o + 24]
        ptr = struct.unpack_from("<I", self.data, o + 28)[0] - 0x08000000
        step = 16 if flags & 1 else 8     # bit0 = 技を決めている
        if not (0 <= ptr < len(self.data)) or size > 6:
            return []
        return [struct.unpack_from("<H", self.data, ptr + i * step + 4)[0] for i in range(size)]

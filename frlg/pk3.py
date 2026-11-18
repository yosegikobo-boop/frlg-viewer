"""第3世代のポケモン1匹（手持ち100バイト / ボックス80バイト）の解読と作り直し"""
import struct
from dataclasses import dataclass, field

# 4つの区画 G=成長 A=技 E=努力値 M=その他 の並び（pid % 24）
ORDERS = ["GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
          "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
          "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
          "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG"]


def is_shiny(pid: int, otid: int) -> bool:
    return ((otid & 0xFFFF) ^ (otid >> 16) ^ (pid & 0xFFFF) ^ (pid >> 16)) < 8


@dataclass
class Pk3:
    pid: int
    otid: int
    header: bytearray            # 0x00〜0x1F（名前・言語・親の名前など、そのまま保つ）
    sub: dict                    # 'G','A','E','M' → bytearray(12)（解いたもの）
    tail: bytearray = field(default_factory=lambda: bytearray(20))   # 手持ちの 0x50〜0x63
    checksum_ok: bool = True

    @classmethod
    def blank(cls, pid=0, otid=0) -> "Pk3":
        h = bytearray(32)
        struct.pack_into("<II", h, 0, pid, otid)
        h[0x08:0x12] = b"\xff" * 10
        h[0x12] = 1                  # 言語 = 日本
        h[0x13] = 0x02               # 種類あり
        h[0x14:0x1B] = b"\xff" * 7
        return cls(pid, otid, h, {k: bytearray(12) for k in "GAEM"})

    # --- 成長 ---
    def _g(self, fmt, off):
        return struct.unpack_from(fmt, self.sub["G"], off)[0]

    species = property(lambda s: s._g("<H", 0), lambda s, v: struct.pack_into("<H", s.sub["G"], 0, v))
    item = property(lambda s: s._g("<H", 2), lambda s, v: struct.pack_into("<H", s.sub["G"], 2, v))
    exp = property(lambda s: s._g("<I", 4), lambda s, v: struct.pack_into("<I", s.sub["G"], 4, v))
    friendship = property(lambda s: s.sub["G"][9], lambda s, v: s.sub["G"].__setitem__(9, v))

    @property
    def pp_bonuses(self):
        return self.sub["G"][8]

    @pp_bonuses.setter
    def pp_bonuses(self, v):
        self.sub["G"][8] = v

    # --- 技 ---
    @property
    def moves(self):
        return list(struct.unpack_from("<4H", self.sub["A"], 0))

    @moves.setter
    def moves(self, v):
        struct.pack_into("<4H", self.sub["A"], 0, *v)

    @property
    def pp(self):
        return list(self.sub["A"][8:12])

    @pp.setter
    def pp(self, v):
        self.sub["A"][8:12] = bytes(v)

    # --- 努力値（HP・攻・防・素早・特攻・特防） ---
    @property
    def evs(self):
        return list(self.sub["E"][0:6])

    @evs.setter
    def evs(self, v):
        self.sub["E"][0:6] = bytes(v)

    # --- その他 ---
    @property
    def iv_word(self):
        return struct.unpack_from("<I", self.sub["M"], 4)[0]

    @iv_word.setter
    def iv_word(self, v):
        struct.pack_into("<I", self.sub["M"], 4, v)

    @property
    def ivs(self):
        w = self.iv_word
        return [(w >> (5 * i)) & 31 for i in range(6)]

    @ivs.setter
    def ivs(self, v):
        w = self.iv_word & 0xC0000000
        for i, x in enumerate(v):
            w |= (x & 31) << (5 * i)
        self.iv_word = w

    @property
    def is_egg(self):
        return bool(self.iv_word >> 30 & 1)

    @is_egg.setter
    def is_egg(self, v):
        self.iv_word = (self.iv_word & ~(1 << 30)) | (int(bool(v)) << 30)

    @property
    def ability_bit(self):
        return self.iv_word >> 31 & 1

    @ability_bit.setter
    def ability_bit(self, v):
        self.iv_word = (self.iv_word & 0x7FFFFFFF) | ((v & 1) << 31)

    @property
    def ribbons(self):
        return struct.unpack_from("<I", self.sub["M"], 8)[0]

    @property
    def fateful(self):
        return bool(self.ribbons >> 31)

    @fateful.setter
    def fateful(self, v):
        r = (self.ribbons & 0x7FFFFFFF) | (int(bool(v)) << 31)
        struct.pack_into("<I", self.sub["M"], 8, r)

    # --- 名前 ---
    @property
    def nickname_raw(self):
        return bytes(self.header[0x08:0x12])

    @nickname_raw.setter
    def nickname_raw(self, v):
        self.header[0x08:0x12] = v[:10].ljust(10, b"\xff")

    # --- 手持ちだけの部分 ---
    @property
    def level(self):
        return self.tail[4]

    @level.setter
    def level(self, v):
        self.tail[4] = v

    @property
    def cur_hp(self):
        return struct.unpack_from("<H", self.tail, 6)[0]

    @cur_hp.setter
    def cur_hp(self, v):
        struct.pack_into("<H", self.tail, 6, v)

    @property
    def stats(self):
        """最大HP・攻・防・素早・特攻・特防"""
        return list(struct.unpack_from("<6H", self.tail, 8))

    @stats.setter
    def stats(self, v):
        struct.pack_into("<6H", self.tail, 8, *v)

    @property
    def status(self):
        return struct.unpack_from("<I", self.tail, 0)[0]

    @status.setter
    def status(self, v):
        struct.pack_into("<I", self.tail, 0, v)

    @property
    def is_empty(self):
        return self.species == 0

    def copy(self) -> "Pk3":
        return Pk3(self.pid, self.otid, bytearray(self.header),
                   {k: bytearray(v) for k, v in self.sub.items()}, bytearray(self.tail), self.checksum_ok)


def _crypt(data: bytes, key: int) -> bytearray:
    out = bytearray(len(data))
    for i in range(0, len(data), 4):
        struct.pack_into("<I", out, i, struct.unpack_from("<I", data, i)[0] ^ key)
    return out


def _checksum(plain48: bytes) -> int:
    return sum(struct.unpack("<24H", plain48)) & 0xFFFF


def decode_pk3(data: bytes) -> Pk3:
    pid, otid = struct.unpack_from("<II", data, 0)
    plain = _crypt(data[0x20:0x50], pid ^ otid)
    order = ORDERS[pid % 24]
    sub = {k: bytearray(plain[i * 12:(i + 1) * 12]) for i, k in enumerate(order)}
    stored = struct.unpack_from("<H", data, 0x1C)[0]
    tail = bytearray(data[0x50:0x64]) if len(data) >= 100 else bytearray(20)
    return Pk3(pid, otid, bytearray(data[0:0x20]), sub, tail, stored == _checksum(plain))


def encode_pk3(p: Pk3, party: bool) -> bytes:
    h = bytearray(p.header)
    struct.pack_into("<II", h, 0, p.pid, p.otid)
    plain = b"".join(bytes(p.sub[k]) for k in ORDERS[p.pid % 24])
    struct.pack_into("<H", h, 0x1C, _checksum(plain))
    out = bytes(h) + bytes(_crypt(plain, p.pid ^ p.otid))
    if party:
        out += bytes(p.tail)
    return out

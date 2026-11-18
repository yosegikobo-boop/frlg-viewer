"""経験値の倍率: mGBA の中の ROM に書く小さな処理を作る（ROM のファイルは変えない）

ゲームの経験値の計算（Cmd_getexp）の中、しあわせタマゴ・トレーナー戦・交換の1.5倍が
終わって経験値（gBattleMoveDamage）が決まったところに割り込む。

  0x0802164c  ldr r7,=…        ← 交換でない道
  0x08021652  ldr r0,=gBattleTypeFlags   ← 2つの道がここで合流。読む値（lit）を「処理|1」に変える
  0x08021654  ldr r1,[r0]; movs r0,#1    ← ここを bl _call_via_r0 にする（bl は 4MB までしか届かない）

処理（ROUTINE_ADDR）は 経験値 = 経験値 × n ÷ 2（n は倍率×2、FACTOR_ADDR に置く）にしてから、
元の命令と同じく r1=戦いの種類・r0=1 にして戻る。r2〜r4 は守る。
"""
import struct
from dataclasses import dataclass

from .rom import UnsupportedRom

# ROM の中ほどの空き（FR・LG とも 0x6C7xxx〜0xBFFFFF が 0xFF）。
# ROM の後ろの 0xFF だけの部分（0xFE0000〜）は、mGBA がステートセーブの読み込みで元に戻すので使わない
FACTOR_ADDR = 0x08B00000
ROUTINE_ADDR = 0x08B00004
FREE_CHECK = (0xB00000, 0xB00040)
HOOK_PATTERN = bytes.fromhex("0e4f0f4a91460f480168012001400029")
CALL_VIA_PATTERN = bytes.fromhex("0047c0460847c0461047c0461847c046")
ROM_BASE = 0x08000000


@dataclass
class ExpHook:
    hook: int           # HOOK_PATTERN の先頭（バスの番地）
    lit: int            # 0x08021652 の ldr が読む値の番地
    flags_addr: int     # gBattleTypeFlags
    dmg_addr: int       # gBattleMoveDamage
    call_via_r0: int


def _find_one(data, pattern, what):
    i = data.find(pattern)
    if i < 0 or data.find(pattern, i + 1) >= 0:
        raise UnsupportedRom("経験値の倍率: %s が見つからない" % what)
    return i


def _ldr_pc_target(data, off):
    """off にある Thumb の ldr Rd,[pc,#imm] が読む番地（ファイルの位置）"""
    imm = data[off] * 4
    return ((off + 4) & ~3) + imm


def find_exp_hook(data: bytes) -> ExpHook:
    h = _find_one(data, HOOK_PATTERN, "経験値の計算の場所")
    cv = _find_one(data, CALL_VIA_PATTERN, "_call_via_r0")
    if any(b != 0xFF for b in data[FREE_CHECK[0]:FREE_CHECK[1]]):
        raise UnsupportedRom("経験値の倍率: ROM の空きが使われている")
    lit = _ldr_pc_target(data, h + 6)
    dmg = _ldr_pc_target(data, h + 2)
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    return ExpHook(hook=ROM_BASE + h, lit=ROM_BASE + lit, flags_addr=u32(lit),
                   dmg_addr=u32(dmg), call_via_r0=ROM_BASE + cv)


def rate_to_halves(rate) -> int:
    try:
        n = int(round(float(rate) * 2))
    except (TypeError, ValueError):
        return 2
    return n if 2 <= n <= 10 else 2


def thumb_bl(src: int, dst: int) -> bytes:
    off = dst - (src + 4)
    assert -0x400000 <= off < 0x400000, "bl が届かない"
    hi = 0xF000 | ((off >> 12) & 0x7FF)
    lo = 0xF800 | ((off >> 1) & 0x7FF)
    return struct.pack("<HH", hi, lo)


def factor_write(rate):
    return FACTOR_ADDR, struct.pack("<HH", rate_to_halves(rate), 0)


def _ldr_pc(rd, at, target):
    return 0x4800 | (rd << 8) | ((target - ((at + 4) & ~3)) // 4)


def _routine(hook: ExpHook) -> bytes:
    b = ROUTINE_ADDR
    done = 24

    def bcond(cond, at):
        return 0xD000 | (cond << 8) | (((done - (at + 4)) // 2) & 0xFF)

    ops = [
        0xB51C,                         # push {r2,r3,r4,lr}
        _ldr_pc(4, b + 2, b + 32),      # ldr r4,=FACTOR_ADDR
        0x8821,                         # ldrh r1,[r4]
        0x2902,                         # cmp r1,#2
        bcond(0x9, 8),                  # bls done
        0x290A,                         # cmp r1,#10
        bcond(0x8, 12),                 # bhi done
        _ldr_pc(4, b + 14, b + 36),     # ldr r4,=gBattleMoveDamage
        0x6820,                         # ldr r0,[r4]
        0x4348,                         # muls r0,r1
        0x1040,                         # asrs r0,r0,#1
        0x6020,                         # str r0,[r4]
        _ldr_pc(0, b + 24, b + 40),     # done: ldr r0,=gBattleTypeFlags
        0x6801,                         # ldr r1,[r0]
        0x2001,                         # movs r0,#1
        0xBD1C,                         # pop {r2,r3,r4,pc}
    ]
    return struct.pack("<16H3I", *ops, FACTOR_ADDR, hook.dmg_addr, hook.flags_addr)


def patch_writes(hook: ExpHook, rate):
    """書く順: 倍率 → 処理 → 読む値 → bl（Lua の1回の呼び出しの中で全部書く）"""
    bl_at = hook.hook + 8
    return [factor_write(rate),
            (ROUTINE_ADDR, _routine(hook)),
            (hook.lit, struct.pack("<I", ROUTINE_ADDR | 1)),
            (bl_at, thumb_bl(bl_at, hook.call_via_r0))]

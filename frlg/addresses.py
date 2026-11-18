"""日本版 FR/LG（版0）の RAM の番地。

ROM のプログラムの中に出てくる番地を数えて決めた（調べたこと/RAMの番地.md）。
海外版（BPRE）からは EWRAM が -0xA0、IWRAM が +0x40 ずれている。FR と LG は同じ。
"""

_JP = {
    "party_count": 0x02023F89,      # u8 手持ちの数
    "enemy_party": 0x02023F8C,      # 100バイト×6
    "party": 0x020241E4,            # 100バイト×6
    "battle_type_flags": 0x02022AAC,  # u32
    "main": 0x03003130,             # gMain。+0x439 の bit1 が戦闘中
    "save_block1_ptr": 0x03005048,
    "save_block2_ptr": 0x0300504C,
    "storage_ptr": 0x03005050,      # ボックス。先頭 u8 = 今の箱、+4 から 14箱×30匹×80バイト
}

ADDR = {"BPRJ": _JP, "BPGJ": _JP}

IN_BATTLE_OFFSET = 0x439
IN_BATTLE_BIT = 0x02

PARTY_SIZE = 100
BOX_MON_SIZE = 80
BOXES = 14
BOX_SLOTS = 30
STORAGE_BOXES_OFFSET = 4

# 戦いの種類のビット（pokefirered include/constants/battle.h）
BT_DOUBLE = 1 << 0
BT_LINK = 1 << 1
BT_TRAINER = 1 << 3
BT_FIRST_BATTLE = 1 << 4
BT_SAFARI = 1 << 7
BT_BATTLE_TOWER = 1 << 8
BT_OLD_MAN_TUTORIAL = 1 << 9
BT_ROAMER = 1 << 10
BT_EREADER_TRAINER = 1 << 11
BT_LEGENDARY = 1 << 13       # 伝説・カビゴンなど。ゆうれいの正体が見えたときにも使う
BT_REGI = 1 << 14
BT_GHOST = 1 << 15
BT_POKEDUDE = 1 << 16
BT_WILD_SCRIPTED = 1 << 17   # 話しかけて始まる野生戦（ビリリダマ・マルマインなど）

# これのどれかが立っていたら差し替えない
DENY_MASK = (BT_LINK | BT_TRAINER | BT_FIRST_BATTLE | BT_BATTLE_TOWER | BT_OLD_MAN_TUTORIAL
             | BT_ROAMER | BT_EREADER_TRAINER | BT_LEGENDARY | BT_REGI | BT_GHOST
             | BT_POKEDUDE | BT_WILD_SCRIPTED)

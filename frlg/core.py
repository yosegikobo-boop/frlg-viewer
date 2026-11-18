"""判断だけをまとめたもの。PC 版（server.py）とスマホ版（mobile/py/webapp.py）が同じものを使う。

ソケット・ファイル・スレッドには触らない。ROM と、ゲームから読んだバイト列をもらって、
「何を書くか」を返すだけ。rom が None（ROM が見つからない）のときは、何もしない答えを返す。
"""
import random

from .addresses import ADDR, DENY_MASK, BT_LINK, BT_BATTLE_TOWER, BT_EREADER_TRAINER, BT_TRAINER
from .cards import party_cards, box_cards
from .exp_patch import find_exp_hook, patch_writes, factor_write
from .pk3 import decode_pk3, encode_pk3
from .rematch import revivable, flag_is_set, grow_party, can_grow, OUTCOME_WON
from .replace import (should_replace, build_replacement, should_replace_starter, build_starter,
                      is_starter_gift)
from .rom import UnsupportedRom

# トレーナー戦で書いてよいか（つうしん・バトルタワー・カードeの戦いには書かない）
TRAINER_DENY = BT_LINK | BT_BATTLE_TOWER | BT_EREADER_TRAINER


class Core:
    def __init__(self, settings, wins, rng=None):
        self.settings = settings
        self.wins = wins
        self.rng = rng or random.Random()
        self._hooks = {}     # ROM ごとの、経験値の計算の場所

    # --- 戦闘が始まった瞬間 ---
    def enemy_new(self, rom, code, data: bytes, flags: int = 0, opp=None, player=None):
        """相手を書きかえるなら (今の個性値, 書いてはいけない戦いの種類, 書く中身)。変えないなら None"""
        if rom is None:
            return None
        if flags & BT_TRAINER:
            return self._trainer_growth(rom, code, data, flags, opp, player)
        s = self.settings
        if not should_replace(flags, s):
            return None
        orig = decode_pk3(data[:100])
        if not orig.checksum_ok or orig.is_empty:
            return None
        new = build_replacement(orig, s, rom, self.rng)
        return orig.pid, DENY_MASK, encode_pk3(new, party=True)

    def _trainer_growth(self, rom, code, data, flags, opp, player):
        """再戦のときに相手を強くする。戦っている相手が ROM の表のトレーナーと同じときだけ"""
        if not self.settings.rematch or opp is None or player is None or len(data) < 600:
            return None
        if (flags & TRAINER_DENY) or not can_grow(rom, opp):
            return None
        wins = self.wins.get(code, player, opp)
        if wins <= 0:
            return None
        live = [decode_pk3(data[i * 100:(i + 1) * 100]) for i in range(6)]
        live_species = [p.species for p in live if p.pid and not p.is_empty]
        if live_species != rom.trainer_party_species(opp):
            return None       # 番地がずれているなど。関係ないポケモンは変えない
        new = grow_party(data[:600], wins, rom)
        if new is None:
            return None
        return live[0].pid, TRAINER_DENY, new

    # --- 戦闘が終わった ---
    def battle_end(self, code, flags, opp, outcome, player):
        if not (flags & BT_TRAINER) or outcome != OUTCOME_WON or opp is None or player is None:
            return
        if (flags & TRAINER_DENY) or not code:
            return
        self.wins.add(code, player, opp)

    # --- 別の場所に入った ---
    def map_entered(self, rom, code, scripts, tflags: bytes, player) -> list:
        """その場所の、勝った印がついたトレーナーのうち、印を消してよい番号のリスト"""
        if rom is None or not self.settings.rematch or player is None:
            return []
        ids = []
        for sc in scripts:
            tid = revivable(rom, sc) if sc else None
            if tid is not None and tid not in ids and flag_is_set(tflags, tid):
                ids.append(tid)
        if ids:
            self.wins.seed(code, player, ids)
        return ids

    # --- 手持ちが 0 → 1 ---
    def party_first(self, rom, code, data: bytes):
        """最初のポケモンを差し替えるなら (書く番地, 今の個性値, 書く中身)"""
        s = self.settings
        if rom is None or code not in ADDR or not should_replace_starter(0, 1, s):
            return None
        orig = decode_pk3(data)
        if not orig.checksum_ok or orig.is_empty or not is_starter_gift(orig, rom):
            return None
        new = build_starter(orig, s, rom, self.rng)
        return ADDR[code]["party"], orig.pid, encode_pk3(new, party=True)

    # --- 経験値の倍率 ---
    def exp_hook(self, rom):
        if rom is None:
            return None          # ROM があとで見つかれば使えるよう、覚えない
        if id(rom) not in self._hooks:
            try:
                self._hooks[id(rom)] = (rom, find_exp_hook(rom.data))
            except UnsupportedRom:
                self._hooks[id(rom)] = (rom, None)
        return self._hooks[id(rom)][1]

    def exp_writes(self, rom, only_factor=False) -> list:
        """ゲームの中の ROM に書くもの [(番地, 中身)]。書けない ROM なら []"""
        hook = self.exp_hook(rom)
        if hook is None:
            return []
        if only_factor:
            return [factor_write(self.settings.exp_rate)]
        return list(patch_writes(hook, self.settings.exp_rate))

    # --- 画面のカード ---
    def cards(self, rom, party: bytes, count: int, enemy=None, boxes=None, box=None) -> dict:
        """enemy は戦闘中だけ渡す。boxes は (今の箱, 全部の箱の中身)。box は見る箱（None なら今の箱）"""
        out = {"party": [], "enemy": [], "box": None, "box_cards": []}
        if rom is None:
            return out
        out["party"] = party_cards(party, rom, count)
        if enemy:
            out["enemy"] = party_cards(enemy, rom, 1)
        if boxes:
            cur, data = boxes
            b = cur if box is None else box
            out["box"] = b
            out["box_cards"] = box_cards(data, rom, b)
        return out

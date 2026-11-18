// 毎フレームの見張り。PC 版の lua/frlg_bridge.lua の on_frame と同じ役
//
// メモリを読んで、出来事があったら Python（webapp.py）を呼ぶ。番地は Lua の A と同じ（日本版 FR・LG 共通）。
// PC 版と違って、Python は同じページの中にいるので、その場で返事をもらって書く（待たない）。

export const A = {
  party_count: 0x02023F89,
  enemy_party: 0x02023F8C,
  party: 0x020241E4,
  flags: 0x02022AAC,
  main: 0x03003130,
  sb1_ptr: 0x03005048,
  sb2_ptr: 0x0300504C,
  opp: 0x020385E2,       // gTrainerBattleOpponent_A（u16）
  outcome: 0x02023DEA,   // gBattleOutcome（u8。1 = 勝ち）
  map_header: 0x02036D30,
  storage_ptr: 0x03005050,
};
export const IN_BATTLE_OFFSET = 0x439, IN_BATTLE_BIT = 0x02;
const PLAYTIME_VBLANK = 0x12;      // SaveBlock2 の遊んでいる時間（1/60秒）
const SB2_PLAYER_ID = 0x0A;
// トレーナーと何度でも戦う（SaveBlock1 の中）
const SB1_LOC = 0x04;                           // 今いる場所
const SB1_FLAGS = 0xEE0;
const TRAINER_FLAG_BASE = SB1_FLAGS + (0x500 >> 3);   // トレーナー n の勝った印は 0x500+n 番
const TRAINER_FLAG_BYTES = 93;
const BOX_BYTES = 14 * 30 * 80;

/** SaveBlock などを指す値が EWRAM の中か */
export function ewramPtr(p) {
  return p >= 0x02000000 && p < 0x02040000 ? p : null;
}

export function unhex(h) {
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
  return out;
}

const sameBytes = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
const hexOf = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
const romPtr = (p, size) => p >= 0x08000000 && p + size <= 0x0A000000;

/** 今の場所の人ごとの台本の頭（20バイト）を hex で「,」につないだもの（PC 版の Lua と同じ） */
export function mapScripts(m) {
  const ev = m.r32(A.map_header + 4);
  if (!romPtr(ev, 8)) return "";
  const n = Math.min(m.r8(ev), 64), objs = m.r32(ev + 4), parts = [];
  for (let i = 0; i < n; i++) {
    const ptr = romPtr(objs, (i + 1) * 0x18) ? m.r32(objs + i * 0x18 + 0x10) : 0;
    parts.push(romPtr(ptr, 20) ? hexOf(m.read(ptr, 20)) : "");
  }
  return parts.join(",");
}

/**
 * @param emu  emu.js の createEmu の返り（mem と onFrame を使う）
 * @param hooks {onState(st), onLog(msg), wantState(): 画面にカードを出しているか}
 */
export function startBridge(emu, hooks = {}) {
  let py = null, frame = 0, boxSel = null, snap = null, boxes = null, queued = false;
  let prevInb = null, prevCount = null, lastVb = null, steady = 0;
  let patches = new Map(), patchBroken = false;
  let battleFlags = 0, battleOpp = null;              // 今の戦闘の始まりのときの戦いの種類と相手
  let curLoc = null, locFrame = 0, mapSent = true;
  const log = (msg) => { if (hooks.onLog) hooks.onLog(msg); };

  const playerId = (m) => {
    const sb2 = ewramPtr(m.r32(A.sb2_ptr));
    return sb2 ? m.r32(sb2 + SB2_PLAYER_ID) : 0;
  };

  const bridge = {
    /** 差し替えなどで書いた回数（確かめ用） */
    writes: 0,
    get py() { return py; },
    setPy(p) { py = p; bridge.refresh(); },
    setBox(n) { boxSel = n; bridge.refresh(); },

    /** ゲームの中の ROM に書いて覚える（経験値の倍率）。list は [[番地, hex], ...] */
    applyPatches(list) {
      const m = emu.mem;
      for (const [addr, h] of list) {
        const data = unhex(h);
        patches.set(addr, data);
        if (m) m.write(addr, data);
      }
      patchBroken = false;
    },

    /** 今の読んだもので、カードを作り直す（フレームの外で） */
    refresh() {
      if (queued || !py || !snap || !(hooks.wantState ? hooks.wantState() : true)) return;
      queued = true;
      setTimeout(() => {
        queued = false;
        if (!py || !snap) return;
        const st = JSON.parse(py.call("state", snap.party, snap.count, snap.enemy, snap.inb,
          boxes ? boxes.data : new Uint8Array(0), boxes ? boxes.cur : 0, boxSel === null ? -1 : boxSel));
        if (hooks.onState) hooks.onState(st);
      }, 0);
    },

    /** ステートセーブの読み込みなどで ROM の書き換えが消えていたら、全部書き直す */
    checkPatches(m) {
      for (const [addr, data] of patches) {
        if (sameBytes(m.read(addr, data.length), data)) continue;
        if (patchBroken) return;
        for (const [a, d] of patches) m.write(a, d);
        if (!sameBytes(m.read(addr, data.length), data)) {
          patchBroken = true;
          log("経験値の倍率を ROM に書けない");
        }
        return;
      }
    },

    /** 毎フレーム（emu の合図の中。メモリは止まっている） */
    tick() {
      const m = emu.mem;
      if (!m) return;
      frame++;
      bridge.checkPatches(m);

      // 遊んでいる時間が 1 ずつ続けて進んでいるか（タイトル・メニューでは止まる。ステートセーブの読み込みでは飛ぶ）
      const sb2 = ewramPtr(m.r32(A.sb2_ptr));
      const vb = sb2 ? m.r8(sb2 + PLAYTIME_VBLANK) : null;
      if (vb !== null && lastVb !== null && vb !== lastVb) steady = vb === (lastVb + 1) % 60 ? steady + 1 : 0;
      else if (vb === null) steady = 0;
      lastVb = vb;

      // 戦闘が始まった瞬間に、相手を Python に渡して、返事があればその場で書く
      // （最初のフレームの値を基準にする: 戦闘中に始めても、その相手は差し替えない）
      const inb = (m.r8(A.main + IN_BATTLE_OFFSET) & IN_BATTLE_BIT) ? 1 : 0;
      if (inb === 1 && prevInb === 0) { battleFlags = m.r32(A.flags); battleOpp = m.r16(A.opp); }
      if (inb === 1 && prevInb === 0 && py && m.r32(A.enemy_party) !== 0) {
        const flags = m.r32(A.flags);
        const r = py.call("enemy_new", m.read(A.enemy_party, 600), flags, m.r16(A.opp), playerId(m));
        if (r) {
          const w = JSON.parse(r);
          if (m.r32(A.enemy_party) === w.pid && (flags & w.mask) === 0) {
            m.write(A.enemy_party, unhex(w.hex));
            bridge.writes++;
            log((flags & 0x8) ? "再戦なので、トレーナーのポケモンを強くした"
              : "野生の相手を差し替えた（戦いの種類 0x" + flags.toString(16) + "）");
          }
        }
      }
      // 戦闘が終わった: トレーナー戦なら勝ち負けを渡す（勝った回数を数える）
      if (inb === 0 && prevInb === 1 && battleOpp !== null) {
        if ((battleFlags & 0x8) && py) py.call("battle_end", battleFlags, battleOpp, m.r8(A.outcome), playerId(m));
        battleOpp = null;
      }
      prevInb = inb;

      // 別の場所に入ったら、少し待って（人の決まりが読み込まれてから）その場所の、勝ったトレーナーを復活させる
      const sb1 = ewramPtr(m.r32(A.sb1_ptr));
      if (sb1 && inb === 0) {
        const loc = m.r16(sb1 + SB1_LOC);
        if (loc !== curLoc) {
          curLoc = loc; locFrame = frame; mapSent = false;
        } else if (!mapSent && frame - locFrame >= 30 && py) {
          mapSent = true;
          const ids = JSON.parse(py.call("map_entered", mapScripts(m), m.read(sb1 + TRAINER_FLAG_BASE, TRAINER_FLAG_BYTES), playerId(m)));
          for (const id of ids) {
            const f = 0x500 + id, a = sb1 + SB1_FLAGS + (f >> 3);
            m.w8(a, m.r8(a) & ~(1 << (f & 7)));
          }
          if (ids.length) log("トレーナー " + ids.length + " 人と、また戦えるようになった");
        }
      }

      // 手持ちが 0 → 1（遊んでいる最中だけ。続きから始めたときは数えない）
      const count = m.r8(A.party_count);
      if (prevCount === 0 && count === 1 && steady >= 120 && py) {
        const r = py.call("party_first", m.read(A.party, 100));
        if (r) {
          const w = JSON.parse(r);
          if (m.r32(w.addr) === w.pid) {
            m.write(w.addr, unhex(w.hex));
            bridge.writes++;
            log("最初のポケモンを差し替えた");
          }
        }
      }
      prevCount = count;

      if (frame % 30 === 0) {
        snap = { party: m.read(A.party, 600), count, enemy: m.read(A.enemy_party, 600), inb };
        bridge.refresh();
      }
      if (frame % 240 === 0) {
        const st = ewramPtr(m.r32(A.storage_ptr));
        if (st) boxes = { cur: m.r8(st), data: m.read(st + 4, BOX_BYTES) };
      }
    },
  };
  emu.onFrame(() => bridge.tick());
  return bridge;
}

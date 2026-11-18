// mGBA（wasm）を動かす・ゲームのメモリを探す・読み書き・セーブ
//
// mgba.js はメモリを外に出してくれないので、WebAssembly.Memory を作るところをつかまえる。
// その中から ROM と同じ並びを探し、その場所を指している「メモリの表」（BIOS・EWRAM・IWRAM・ROM の順）を見つける。
// くわしくは スマホ版の設計.md の「お試しで分かったこと」。

export const SUPPORTED = ["BPRJ", "BPGJ"];
const GAMES = "/data/games/", SAVES = "/data/saves/", STATES = "/data/states/";
const EWRAM_SIZE = 0x40000, IWRAM_SIZE = 0x8000;
const KEYS = ["a", "b", "l", "r", "start", "select", "up", "down", "left", "right"];

/** ROM のヘッダーを見る。gba: GBA の ROM らしいか、supported: 機能が使えるゲームか */
export function romInfo(bytes) {
  if (!bytes || bytes.length < 0xC0 || bytes[0xB2] !== 0x96) return { code: null, gba: false, supported: false };
  let code = "";
  for (let i = 0xAC; i < 0xB0; i++) code += String.fromCharCode(bytes[i]);
  if (!/^[A-Z0-9]{4}$/.test(code)) return { code: null, gba: false, supported: false };
  return { code, gba: true, supported: SUPPORTED.includes(code) };
}

/** メモリの中から ROM と同じ並びの場所を全部探す */
export function findRoms(u32, rom32) {
  const out = [];
  const a = rom32[0], b = rom32[1], c = rom32[40], d = rom32[43];
  for (let i = 0, n = u32.length - 64; i < n; i++) {
    if (u32[i] === a && u32[i + 1] === b && u32[i + 40] === c && u32[i + 43] === d) out.push(i * 4);
  }
  return out;
}

/** ROM の場所を指していて、すぐ前が BIOS・EWRAM・IWRAM の場所になっているものを全部探す */
export function findTables(u32, romPtr) {
  const out = [], limit = u32.length * 4;
  const ok = (p) => p > 0 && p < limit && (p & 3) === 0;
  for (let i = 3; i < u32.length; i++) {
    if (u32[i] !== romPtr) continue;
    const bios = u32[i - 3], wram = u32[i - 2], iwram = u32[i - 1];
    if (ok(bios) && ok(wram) && ok(iwram) && iwram === wram + EWRAM_SIZE) out.push({ at: (i - 3) * 4, bios, wram, iwram, rom: romPtr });
  }
  return out;
}

/** 表がちょうど1つのときだけ使う。あやしいときは使わない（どこにも書かない）。
 *  ROM の写しは2つあることがある（mGBA が始めたあとで ROM を別の場所に移す）ので、ROM の数は見ない */
export function chooseTable(tables) {
  return tables.length === 1 ? tables[0] : null;
}

function locateMemory(buffer, romBytes) {
  const u32 = new Uint32Array(buffer);
  const rom32 = new Uint32Array(romBytes.buffer, romBytes.byteOffset, 64);
  return chooseTable(findRoms(u32, rom32).flatMap((r) => findTables(u32, r)));
}

/** 表の場所（at）から、毎回 EWRAM・IWRAM・ROM の場所を読んで使う（ROM は途中で移ることがある） */
function makeMem(buffer, tableAt, romBytes) {
  const dv = new DataView(buffer), u8 = new Uint8Array(buffer), u32 = new Uint32Array(buffer);
  const t = tableAt >> 2, limit = buffer.byteLength, romSize = romBytes.length;
  const head0 = new DataView(romBytes.buffer, romBytes.byteOffset).getUint32(0, true);
  const head1 = new DataView(romBytes.buffer, romBytes.byteOffset).getUint32(4, true);
  const ptr = (p, size) => p > 0 && (p & 3) === 0 && p + size <= limit;
  const at = (a, n) => {
    const r = a >>> 24;
    let o;
    if (r === 2) o = [u32[t + 1], a & 0xFFFFFF, EWRAM_SIZE];
    else if (r === 3) o = [u32[t + 2], a & 0xFFFFFF, IWRAM_SIZE];
    else if (r === 8 || r === 9) o = [u32[t + 3], a - 0x08000000, romSize];
    else throw new RangeError("読めない番地 0x" + a.toString(16));
    if (o[1] + n > o[2]) throw new RangeError("番地がはみ出す 0x" + a.toString(16));
    return o[0] + o[1];
  };
  return {
    tableAt,
    table: () => ({ at: tableAt, wram: u32[t + 1], iwram: u32[t + 2], rom: u32[t + 3] }),
    /** 表が今も使えるか（ゲームを開き直すと変わることがある）。毎フレーム確かめる */
    alive: () => {
      const wram = u32[t + 1], iwram = u32[t + 2], rom = u32[t + 3];
      return ptr(wram, EWRAM_SIZE) && iwram === wram + EWRAM_SIZE && ptr(rom, romSize)
        && u32[rom >> 2] === head0 && u32[(rom >> 2) + 1] === head1;
    },
    r8: (a) => u8[at(a, 1)],
    r16: (a) => dv.getUint16(at(a, 2), true),
    r32: (a) => dv.getUint32(at(a, 4), true),
    read: (a, n) => { const o = at(a, n); return u8.slice(o, o + n); },
    w8: (a, v) => { u8[at(a, 1)] = v & 0xFF; },
    write: (a, bytes) => { u8.set(bytes, at(a, bytes.length)); },
  };
}

/**
 * @param canvas ゲームを描く canvas
 * @param opts.locate 確かめ用: メモリの探し方を差し替える
 */
export async function createEmu(canvas, opts = {}) {
  const locate = opts.locate || locateMemory;
  let wasmMemory = null;
  const Orig = WebAssembly.Memory;
  WebAssembly.Memory = function (d) { const m = new Orig(d); if (d && d.shared) wasmMemory = m; return m; };
  WebAssembly.Memory.prototype = Orig.prototype;
  let Module;
  try {
    const { default: mGBA } = await import("../vendor/mgba.js");
    Module = await mGBA({ canvas });
  } finally {
    WebAssembly.Memory = Orig;
  }
  await Module.FSInit();
  // 自動のステートセーブ: 30秒ごとと、アプリが隠れたときに残す。開くときに勝手には戻さない（「続きから」を聞く）
  Module.setCoreSettings({ autoSaveStateEnable: true, restoreAutoSaveStateOnLoad: false, autoSaveStateTimerIntervalSeconds: 30 });
  // Module.toggleInput(false) は使わない: 画面のボタン（buttonPress）まで効かなくなる

  let frameFn = null, savedFn = null, syncing = null, running = false, romBytes = null;
  const autoPath = (code) => "/autosave/" + code + "_auto.ss";
  const sync = () => (syncing = (syncing || Promise.resolve()).then(() => Module.FSSync()).catch(() => {}));
  const exists = (p) => Module.FS.analyzePath(p).exists;

  const emu = {
    Module,
    code: null,
    mem: null,
    frames: 0,
    romInfo,
    get running() { return running; },
    get rom() { return romBytes; },

    /** ブラウザの中にある ROM のコードの一覧 */
    roms() {
      return Module.listRoms().filter((n) => n.endsWith(".gba")).map((n) => n.slice(0, -4));
    },
    hasRom() { return emu.roms().length > 0; },

    /** ROM をブラウザの中に覚える。対応していないファイルは覚えない */
    async storeRom(bytes) {
      const info = romInfo(bytes);
      if (!info.gba) return info;
      Module.FS.writeFile(GAMES + info.code + ".gba", bytes);
      await sync();
      return info;
    },

    /** ゲームを始める。bytes があれば先に覚える。code は覚えてある ROM から選ぶとき */
    async start(bytes, code) {
      if (bytes) {
        const info = await emu.storeRom(bytes);
        if (!info.gba) throw new Error("GBA の ROM ではありません");
        code = info.code;
      }
      code = code || emu.roms()[0];
      if (!code || !exists(GAMES + code + ".gba")) throw new Error("ROM がありません");
      if (running) Module.quitGame();
      running = false;
      emu.mem = null;
      if (!Module.loadGame(GAMES + code + ".gba")) throw new Error("ゲームを開けませんでした");
      emu.code = code;
      running = true;
      romBytes = Module.FS.readFile(GAMES + code + ".gba");
      emu.relocate();
      // 合図は loadGame のあとに登録しないと来ない
      Module.addCoreCallbacks({
        videoFrameEndedCallback: () => {
          emu.frames++;
          if (emu.mem && !emu.mem.alive()) emu.mem = null;
          if (frameFn) frameFn();
        },
        saveDataUpdatedCallback: () => { sync().then(() => { if (savedFn) savedFn(); }); },
      });
      return romInfo(romBytes);
    },

    /** メモリの場所を探し直す。見つからなければ mem は null（ゲームは遊べる） */
    relocate() {
      const table = wasmMemory && romBytes ? locate(wasmMemory.buffer, romBytes) : null;
      emu.mem = table ? makeMem(wasmMemory.buffer, table.at, romBytes) : null;
      if (emu.mem && !emu.mem.alive()) emu.mem = null;
      return emu.mem;
    },

    onFrame(fn) { frameFn = fn; },
    onSaved(fn) { savedFn = fn; },
    sync,

    press(key) { if (running && KEYS.includes(key)) Module.buttonPress(key); },
    release(key) { if (running && KEYS.includes(key)) Module.buttonUnpress(key); },
    setFast(on, times = 4) { if (running) Module.setFastForwardMultiplier(on ? times : 1); },
    pause() { if (running) { Module.pauseGame(); Module.pauseAudio(); } },
    resume() { if (running) { Module.resumeGame(); Module.resumeAudio(); } },
    /** 音は、画面を触ったあとでないと鳴らない（ブラウザの決まり） */
    unlockAudio() {
      const ctx = Module.SDL2 && Module.SDL2.audioContext;
      if (ctx && ctx.state === "suspended") ctx.resume();
    },

    exportSave(code) {
      const p = SAVES + (code || emu.code) + ".sav";
      return exists(p) ? Module.FS.readFile(p) : null;
    },
    /** セーブを入れる。遊んでいる途中なら、ゲームを開き直す */
    async importSave(bytes, code) {
      code = code || emu.code;
      if (!code) throw new Error("先に ROM を選んでください");
      Module.FS.writeFile(SAVES + code + ".sav", bytes);
      emu.clearAutoState(code);       // 前のセーブの「続きから」は使わない
      await sync();
      if (running && code === emu.code) await emu.start(null, code);
    },
    saveState(slot) { const ok = running && Module.saveState(slot); sync(); return !!ok; },
    loadState(slot) { return !!(running && Module.loadState(slot)); },
    hasState(slot) { return !!emu.code && exists(STATES + emu.code + ".ss" + slot); },

    /** 自動のステートセーブ（閉じても続きから） */
    hasAutoState(code) { code = code || emu.code; return !!code && exists(autoPath(code)); },
    async saveAutoState() {
      if (!running) return false;
      const ok = !!Module.forceAutoSaveState();
      await sync();
      return ok && exists(autoPath(emu.code));
    },
    loadAutoState() { return !!(running && Module.loadAutoSaveState()); },
    clearAutoState(code) {
      const p = autoPath(code || emu.code);
      if (exists(p)) Module.FS.unlink(p);
    },
  };
  return emu;
}

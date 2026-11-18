// ページのまとめ役: mGBA を用意して、最初の画面（ROM を選ぶ・はじめる）を動かす
import { createEmu, romInfo } from "./emu.js";
import { createPad } from "./pad.js";
import { createSpeed } from "./speed.js";
import { startBridge } from "./bridge.js";
import { createUi } from "./ui.js";
import { loadPy } from "./py.js";
import { checkSaveFile, createSaveTab, download, backupName } from "./savetab.js";

export const GAME_NAMES = { BPRJ: "ファイアレッド", BPGJ: "リーフグリーン" };
const $ = (id) => document.getElementById(id);

/** localStorage の JSON。壊れていたら {} */
export function loadJson(key) {
  try {
    const v = JSON.parse(localStorage.getItem(key) || "{}");
    return v && typeof v === "object" && !Array.isArray(v) ? v : {};
  } catch (_) {
    return {};
  }
}
export function saveText(key, text) {
  try { localStorage.setItem(key, text); } catch (_) { /* いっぱい・使えない */ }
}

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch (_) { /* 使えないブラウザでも動かす */ }
  return null;
}

/** ROM に選ばれたファイルを見て、だめなら理由を返す */
export function checkRomFile(bytes) {
  if (bytes && bytes.length >= 2 && bytes[0] === 0x50 && bytes[1] === 0x4B) {
    return { ok: false, reason: "zip のままでは読めません。中の .gba のファイルを選んでね" };
  }
  const info = romInfo(bytes);
  if (!info.gba) return { ok: false, reason: "GBA の ROM ではないみたい。.gba のファイルを選んでね" };
  return { ok: true, info };
}

export async function createApp(opts = {}) {
  const emu = await createEmu($("screen"), opts);
  const speed = createSpeed(emu);
  createPad(document, emu, speed);

  const app = {
    emu,
    /** 早送り（ON・OFF と速さ） */
    speed,
    ui: null,
    bridge: null,
    py: null,
    /** 今の設定（Python から返ってきたもの） */
    settings: null,
    /** Python の準備ができたら解決する（使えないゲーム・メモリが読めないときは null） */
    pyReady: Promise.resolve(null),
    notice(text) { $("notice").textContent = text || ""; $("notice").hidden = !text; },
    message(text) { $("msg").textContent = text || ""; },

    /** ROM を選んだ: 確かめて、ブラウザの中に覚える */
    async chooseRom(bytes) {
      const r = checkRomFile(bytes);
      if (!r.ok) { app.message(r.reason); return r; }
      await emu.storeRom(bytes);
      app.message(r.info.supported ? "" : "このゲームは遊べるけど、カードや差し替えは使えません");
      app.showStart(r.info.code);
      return r;
    },

    gameName() { return GAME_NAMES[emu.code] || emu.code || ""; },

    /** はじめる。前に閉じたところ（自動のステートセーブ）があれば、続きからにするか聞く */
    async begin(code) {
      await emu.start(null, code);
      store("frlg.last", emu.code);
      $("start").hidden = true;
      emu.unlockAudio();
      if (emu.hasAutoState()) {
        emu.pause();
        $("resume").hidden = false;
        const yes = await new Promise((r) => { $("resumeYes").onclick = () => r(true); $("resumeNo").onclick = () => r(false); });
        $("resume").hidden = true;
        emu.resume();
        if (yes) {
          // ゲームが動き出してから読み込む（開いた直後に読み込むと、ゲームの始まりに上書きされた）
          const f0 = emu.frames;
          for (let i = 0; i < 200 && emu.frames < f0 + 2; i++) await new Promise((r) => setTimeout(r, 10));
          if (!emu.loadAutoState()) app.notice("前に閉じたところを読み込めませんでした（レポートから始めます）");
        }
      }
      const supported = romInfo(emu.rom).supported;
      app.notice(supported && !emu.mem ? "この版の mGBA ではメモリが読めないので、カードや差し替えは止めています（ゲームは遊べます）" : "");
      app.pyReady = supported && emu.mem ? app.startTools() : Promise.resolve(null);
    },

    /** アプリが隠れる・閉じる: 今の場面を残して、音を止める */
    async suspend() {
      if (!emu.running) return false;
      const ok = await emu.saveAutoState();
      emu.pause();
      return ok;
    },

    exportSaveBytes() { return emu.exportSave(); },

    /** セーブを取り込んで、ゲームを開き直す。backup なら先に今のセーブを書き出す */
    async importSaveBytes(bytes, opts = {}) {
      const c = checkSaveFile(bytes);
      if (!c.ok) return c;
      if (opts.backup !== false) {
        const old = emu.exportSave();
        if (old) download(old, backupName(app.gameName()));
      }
      await emu.importSave(c.bytes);
      return { ok: true };
    },

    /** カード・差し替えなど（Python）を用意する。ゲームは待たずに遊べる */
    async startTools() {
      if (!app.ui) {
        app.ui = createUi({
          onSettings: (s) => app.setSettings(s),
          onBox: (n) => app.bridge && app.bridge.setBox(n),
          onOpen: () => app.bridge && app.bridge.refresh(),
        });
        createSaveTab(app);
        app.bridge = startBridge(emu, {
          wantState: () => app.ui.isOpen,
          onState: (st) => app.ui.showState(st),
          onLog: (msg) => app.ui.log(msg),
        });
      }
      app.ui.status("じゅんび中…（最初だけ少しかかります）");
      try {
        app.py = await loadPy(emu.rom, loadJson("frlg.settings"), loadJson("frlg.wins"),
          (s) => saveText("frlg.wins", s));
      } catch (e) {
        app.ui.status("カードや差し替えを用意できませんでした: " + (e.message || e));
        return null;
      }
      if (!app.py.boot.ok) {
        app.ui.status("このゲームでは、カードや差し替えは使えません");
        app.py = null;
        return null;
      }
      app.ui.status("");
      const b = app.py.boot;
      app.settings = b.settings;
      app.ui.setChoices(b.species, b.natures, b.exp_ok);
      app.ui.showSettings(b.settings);
      app.bridge.applyPatches(JSON.parse(app.py.call("exp_writes")));
      app.bridge.setPy(app.py);
      return app.py;
    },

    /** 設定を変える（画面から・確かめの台本から）。patch は変える項目だけでよい */
    setSettings(patch) {
      if (!app.py) return null;
      const r = JSON.parse(app.py.call("set_settings", JSON.stringify(Object.assign({}, app.settings, patch))));
      app.settings = r.settings;
      saveText("frlg.settings", JSON.stringify(r.settings));
      app.ui.showSettings(r.settings);
      if (r.exp.length) app.bridge.applyPatches(r.exp);
      return r.settings;
    },

    /** 最初の画面: 覚えてある ROM ごとに「はじめる」ボタンを出す */
    showStart(prefer) {
      const codes = emu.roms();
      const last = prefer || store("frlg.last");
      codes.sort((a, b) => (b === last) - (a === last));
      const box = $("games");
      box.textContent = "";
      for (const c of codes) {
        const b = document.createElement("button");
        b.className = "big";
        b.textContent = (GAME_NAMES[c] || c) + " をはじめる";
        b.onclick = () => app.begin(c).catch((e) => app.message(String(e.message || e)));
        box.appendChild(b);
      }
      $("pickLabel").textContent = codes.length ? "ほかの ROM を選ぶ" : "ROM を選ぶ";
      $("start").hidden = false;
    },
  };

  // opts.keepRunning: 確かめのとき（画面なしの Edge は、途中で「隠れた」扱いになることがある）
  document.addEventListener("visibilitychange", () => {
    if (opts.keepRunning) return;
    if (document.hidden) app.suspend();
    else if (emu.running && $("start").hidden && $("resume").hidden) emu.resume();
  });
  window.addEventListener("pagehide", () => { if (!opts.keepRunning) app.suspend(); });

  $("pick").addEventListener("change", async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    app.message("読み込み中…");
    try {
      await app.chooseRom(new Uint8Array(await f.arrayBuffer()));
    } catch (err) {
      app.message("読み込めませんでした: " + (err.message || err));
    }
  });

  app.showStart();
  return app;
}

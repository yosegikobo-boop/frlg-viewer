// セーブのタブ: セーブの書き出し・取り込み、ステートセーブ、ROM の選び直し
const $ = (id) => document.getElementById(id);
const SAVE_SIZE = 131072;

/** 取り込むセーブを確かめる。FRLG のセーブで、中身が入っているものだけ。
 *  （セーブの中では FR と LG を見分けられない。どちらも「FRLG」の印 1 だけ） */
export function checkSaveFile(bytes) {
  if (!bytes || (bytes.length !== SAVE_SIZE && bytes.length !== SAVE_SIZE + 16)) {
    return { ok: false, reason: "セーブのファイルではないみたい（大きさが " + (bytes ? bytes.length : 0) + " バイト。128KB のはず）" };
  }
  const d = bytes.subarray(0, SAVE_SIZE);
  const dv = new DataView(d.buffer, d.byteOffset, d.length);
  let found = false, frlg = false;
  for (let s = 0; s < 28; s++) {
    const o = s * 4096;
    if (dv.getUint32(o + 0xFF8, true) !== 0x08012025) continue;
    found = true;
    if (dv.getUint16(o + 0xFF4, true) === 0 && dv.getUint32(o + 0xAC, true) === 1) frlg = true;
  }
  if (!found) return { ok: false, reason: "セーブの中身が入っていません" };
  if (!frlg) return { ok: false, reason: "ファイアレッド・リーフグリーンのセーブではないみたい" };
  return { ok: true, bytes: d.slice() };
}

function stamp() {
  const t = new Date(), p = (n) => String(n).padStart(2, "0");
  return `${t.getFullYear()}${p(t.getMonth() + 1)}${p(t.getDate())}_${p(t.getHours())}${p(t.getMinutes())}`;
}

/** ファイルとしてスマホに保存させる */
export function download(bytes, name) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export function backupName(gameName) {
  return "FRLG_セーブ控え_" + (gameName || "") + "_" + stamp() + ".sav";
}
export function exportName(gameName) {
  return (gameName || "FRLG") + "_" + stamp() + ".sav";
}

/** タブの中身を作る。app は main.js の createApp の返り */
export function createSaveTab(app) {
  const emu = app.emu;
  const rows = [1, 2, 3].map((n) => `<div class="slot"><span>スロット ${n}</span>
    <button class="sbtn" data-ss="${n}">保存</button><button class="sbtn" data-ls="${n}">読み込む</button></div>`).join("");
  $("tab-save").innerHTML = `
    <div class="sec-title">セーブ（ゲームの中のレポート）</div>
    <div class="row"><button class="sbtn" id="exportSave">書き出す</button>
      <label class="sbtn">取り込む<input type="file" id="importSave" accept=".sav,application/octet-stream" hidden></label></div>
    <p class="note">レポートを書くと、このスマホの中に自動で残ります。Chrome のデータを消すとセーブも消えるので、ときどき「書き出す」で控えを取ってね。取り込むときは、前のセーブを先に控えとして書き出します。</p>
    <div class="sec-title">ステートセーブ（今の場面をそのまま残す）</div>
    ${rows}
    <p class="note">アプリを閉じたり切り替えたりしたときも、自動でその場面を残します。次に「はじめる」と、続きからを選べます。</p>
    <div class="sec-title">ほかのゲーム</div>
    <div class="row"><button class="sbtn" id="changeRom">ROM を選び直す</button></div>
    <div id="saveMsg" class="note"></div>`;
  const msg = (t) => { $("saveMsg").textContent = t || ""; };

  $("exportSave").onclick = () => {
    const b = emu.exportSave();
    if (!b) { msg("まだセーブがありません（ゲームの中でレポートを書いてね）"); return; }
    download(b, exportName(app.gameName()));
    msg("書き出しました");
  };
  $("importSave").onchange = async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    const bytes = new Uint8Array(await f.arrayBuffer());
    const c = checkSaveFile(bytes);
    if (!c.ok) { msg(c.reason); return; }
    if (!confirm("このセーブを取り込んで、ゲームを最初の画面から開き直します。今のセーブは控えとして書き出します。いい？")) return;
    const r = await app.importSaveBytes(bytes);
    msg(r.ok ? "取り込みました。タイトルから「つづきから」を選んでね" : r.reason);
    if (r.ok) app.ui.close();
  };
  for (const b of document.querySelectorAll("[data-ss]")) {
    b.onclick = () => msg(emu.saveState(+b.dataset.ss) ? "スロット " + b.dataset.ss + " に保存しました" : "保存できませんでした");
  }
  for (const b of document.querySelectorAll("[data-ls]")) {
    b.onclick = () => {
      const n = +b.dataset.ls;
      if (!emu.hasState(n)) { msg("スロット " + n + " は空です"); return; }
      if (!confirm("スロット " + n + " を読み込みます。今の場面は消えます。いい？")) return;
      msg(emu.loadState(n) ? "読み込みました" : "読み込めませんでした");
      if (emu.running) app.ui.close();
    };
  }
  $("changeRom").onclick = () => { app.ui.close(); emu.pause(); app.showStart(); };
}

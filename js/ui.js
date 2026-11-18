// メニューのパネル（カード・設定・セーブ）
//
// 見た目と言葉は PC 版の web/index.html と同じ。

const STAT = ["HP", "こうげき", "ぼうぎょ", "すばやさ", "とくこう", "とくぼう"];
const $ = (id) => document.getElementById(id);

export function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]));
}

/** 1匹のカード（PC 版の cardHtml と同じ） */
export function cardHtml(c, enemy) {
  if (c.egg) return `<div class="card"><div class="top"><span class="nm">タマゴ</span></div></div>`;
  const head = `<div class="bar head"><span></span><span>能力値</span><span class="h-iv">個体値</span><span></span><span>努力値</span></div>`;
  const bars = head + c.ivs.map((v, i) => {
    const mark = i === c.nature_up ? '<span class="u">↑</span>' : i === c.nature_down ? '<span class="d">↓</span>' : "";
    const max = v === 31 ? " max" : "";
    return `<div class="bar"><span class="k">${STAT[i]}${mark}</span><span class="st">${c.stats[i]}</span>
      <span class="track"><span class="fill${max}" style="width:${v / 31 * 100}%"></span></span>
      <span class="v${max}">${v}</span><span class="ev">${c.evs[i]}</span></div>`;
  }).join("");
  const r = c.max_hp ? c.hp / c.max_hp : 0;
  const hpBar = `<div class="hp"><span>HP</span>
    <span class="track"><span class="fill${r <= 0.2 ? " low" : r <= 0.5 ? " mid" : ""}" style="width:${Math.min(100, r * 100)}%"></span></span>
    <span class="num">${c.hp} / ${c.max_hp}</span></div>`;
  const cond = c.status ? `<span class="cond">${esc(c.status)}</span>` : "";
  const sex = c.gender === "male" ? '<span class="sex m">♂</span>' : c.gender === "female" ? '<span class="sex f">♀</span>' : "";
  const nick = c.name && c.name !== c.species_name ? `<span class="spn">${esc(c.species_name)}</span>` : "";
  return `<div class="card${enemy ? " enemy" : ""}">
    <div class="top"><span class="nm">${esc(c.name || c.species_name)}</span>${sex}${nick}
      ${c.shiny ? '<span class="shiny">★色違い</span>' : ""}${cond}<span class="lv">Lv.${c.level}</span></div>
    <div class="meta">${esc(c.nature_label)}<br>とくせい ${esc(c.ability)}</div>
    ${hpBar}<div class="bars">${bars}</div></div>`;
}

/** 「025 ピカチュウ」の形 */
function spText(species, no) {
  const s = species[no - 1];
  return s ? String(no).padStart(3, "0") + " " + s.name : "";
}
/** 入力 → 全国図鑑の番号。番号・名前・「025 ピカチュウ」のどれでもよい */
export function spNo(species, text) {
  text = (text || "").trim();
  if (!text) return null;
  const m = text.match(/^(\d{1,3})/);
  if (m) { const n = +m[1]; return n >= 1 && n <= 386 ? n : null; }
  const s = species.find((x) => x.name === text || text.endsWith(" " + x.name));
  return s ? s.no : null;
}

/** 設定のタブ。opts.onSettings(新しい設定) を呼ぶ */
function settingsTab(opts) {
  let species = [], settings = null, dragging = false;
  const showRate = (v) => {
    v = +v;
    $("exp_text").textContent = v.toFixed(1) + "倍";
    $("exp_text").classList.toggle("up", v > 1);
  };
  const collect = (patch) => Object.assign({}, settings, {
    species: spNo(species, $("species").value), starter: spNo(species, $("starter").value),
    level: $("level").value ? Math.max(1, Math.min(100, +$("level").value)) : null,
    nature: $("nature").value === "" ? null : +$("nature").value, gender: $("gender").value || null,
    max_ivs: $("max_ivs").checked, shiny: $("shiny").checked, rematch: $("rematch").checked,
    exp_rate: +$("exp_rate").value,
  }, patch || {});
  const save = (patch) => { if (settings && opts.onSettings) opts.onSettings(collect(patch)); };

  $("toggle").onclick = () => save({ enabled: !settings.enabled });
  for (const id of ["species", "starter", "level", "nature", "gender", "max_ivs", "shiny", "rematch"]) {
    $(id).addEventListener("change", () => save());
  }
  $("exp_rate").addEventListener("input", () => { dragging = true; showRate($("exp_rate").value); });
  $("exp_rate").addEventListener("change", () => { dragging = false; save(); });

  return {
    setChoices(sp, natures, expOk) {
      species = sp;
      $("splist").innerHTML = sp.map((s) => `<option value="${esc(spText(sp, s.no))}">`).join("");
      $("nature").innerHTML = '<option value="">元のまま</option>'
        + natures.map((n) => `<option value="${n.id}">${esc(n.label)}</option>`).join("");
      $("exp_ng").hidden = !!expOk;
      $("exp_rate").disabled = !expOk;
    },
    show(s) {
      settings = s;
      $("toggle").textContent = s.enabled ? "ON" : "OFF";
      $("toggle").classList.toggle("on", s.enabled);
      if (document.activeElement !== $("species")) $("species").value = s.species ? spText(species, s.species) : "";
      if (document.activeElement !== $("starter")) $("starter").value = s.starter ? spText(species, s.starter) : "";
      if (document.activeElement !== $("level")) $("level").value = s.level || "";
      $("nature").value = s.nature === null ? "" : String(s.nature);
      $("gender").value = s.gender || "";
      $("max_ivs").checked = s.max_ivs;
      $("shiny").checked = s.shiny;
      $("rematch").checked = s.rematch;
      if (!dragging) { $("exp_rate").value = s.exp_rate; showRate(s.exp_rate); }
    },
  };
}

function fill(el, list, emptyText, enemy) {
  el.innerHTML = list.length ? list.map((c) => cardHtml(c, enemy)).join("") : `<div class="empty">${emptyText}</div>`;
}

/**
 * @param opts.onBox(n) 見るボックスを変えた（null で今の箱）
 * @param opts.onOpen() パネルを開いた
 * @param opts.onSettings(s) 設定を変えた
 */
/** 横持ちの見た目にする条件（index.html の @media と同じ） */
export const LANDSCAPE = "(orientation: landscape) and (max-height: 520px)";

export function createUi(opts = {}) {
  let open = false, boxTouched = false;
  const panel = $("panel"), btn = $("menuBtn");
  for (let i = 0; i < 14; i++) $("box").insertAdjacentHTML("beforeend", `<option value="${i}">ボックス${i + 1}</option>`);
  $("box").onchange = () => { boxTouched = true; if (opts.onBox) opts.onBox(+$("box").value); };

  const tabs = [...document.querySelectorAll("[data-tab]")];
  const showTab = (name) => {
    for (const t of tabs) t.classList.toggle("on", t.dataset.tab === name);
    for (const s of document.querySelectorAll(".tab")) s.hidden = s.id !== "tab-" + name;
  };
  for (const t of tabs) t.onclick = () => showTab(t.dataset.tab);
  showTab("cards");
  const st = settingsTab(opts);

  const ui = {
    get isOpen() { return open; },
    open() {
      open = true;
      panel.hidden = false;
      btn.textContent = "とじる";
      if (opts.onOpen) opts.onOpen();
    },
    close() { open = false; panel.hidden = true; btn.textContent = "メニュー"; },
    toggle() { open ? ui.close() : ui.open(); },
    showTab,

    /** Python の準備の様子（カードの上に出す） */
    status(text) { $("pyStatus").textContent = text || ""; $("pyStatus").hidden = !text; },

    setChoices: (sp, natures, expOk) => st.setChoices(sp, natures, expOk),
    showSettings: (s) => st.show(s),

    showState(st) {
      $("enemyBox").hidden = !st.enemy.length;
      fill($("enemy"), st.enemy, "", true);
      fill($("party"), st.party, "まだいません");
      $("boxBox").hidden = st.box === null;
      if (st.box !== null) {
        if (!boxTouched) $("box").value = String(st.box);
        fill($("boxCards"), st.box_cards, "このボックスは空です");
      }
    },

    log(msg) {
      const el = $("logs");
      const t = new Date();
      const line = `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")} ${msg}`;
      el.textContent = [line].concat(el.textContent ? el.textContent.split("\n") : []).slice(0, 5).join("\n");
    },
  };
  btn.onclick = () => ui.toggle();
  $("panelClose").onclick = () => ui.close();
  // 横持ちでは、メニューのボタンを下の列（SELECT・START・早送り）に入れる。右上だと R ボタンに重なる
  const wide = window.matchMedia(LANDSCAPE);
  const place = () => {
    const home = document.querySelector(".topbar"), mid = document.querySelector(".mid");
    if (wide.matches) { if (mid && btn.parentElement !== mid) mid.appendChild(btn); }
    else if (home && btn.parentElement !== home) home.appendChild(btn);
  };
  place();
  if (wide.addEventListener) wide.addEventListener("change", place); else wide.addListener(place);
  btn.hidden = false;
  return ui;
}

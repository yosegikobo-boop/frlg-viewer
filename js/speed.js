// 早送り: ボタンを押すたびに ON・OFF。速さは設定のスライダー（1.0〜4.0倍、0.25刻み）で選び、覚えておく
//
// mGBA の早送りの倍率（setFastForwardMultiplier）は整数しか受け取らないので、
// 「1秒に何コマ動かすか」（baseFpsTarget、ふつうは 60）を 60×倍率 にして速さを変える。

export const SPEED_MIN = 1, SPEED_MAX = 4, SPEED_STEP = 0.25, SPEED_DEFAULT = 2;
const KEY = "frlg.speed";

/** 1.0〜4.0 の 0.25刻みに丸める。数でなければ 2.0 */
export function clampSpeed(v) {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() ? Number(v) : NaN;
  if (!Number.isFinite(n)) return SPEED_DEFAULT;
  return Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(n / SPEED_STEP) * SPEED_STEP));
}

/** 2 → "2.0倍"、1.25 → "1.25倍" */
export function speedText(v) {
  return (v * 2 === Math.round(v * 2) ? v.toFixed(1) : v.toFixed(2)) + "倍";
}

/** 倍率 → 1秒に動かすコマ数 */
export const fpsFor = (rate) => Math.round(60 * rate);

function loadRate() {
  try { return clampSpeed(localStorage.getItem(KEY)); } catch (_) { return SPEED_DEFAULT; }
}

/**
 * @param emu  emu.js の createEmu の戻り値（setSpeed を使う）
 * 画面の [data-fast] ボタン、#speed_rate のスライダー、#speed_text の字を使う
 */
export function createSpeed(emu, root = document) {
  let on = false, rate = loadRate();
  const btns = [...root.querySelectorAll("[data-fast]")];
  const slider = root.getElementById ? root.getElementById("speed_rate") : null;
  const text = root.getElementById ? root.getElementById("speed_text") : null;

  const show = () => {
    for (const b of btns) {
      b.classList.toggle("on", on);
      b.textContent = on ? "▶▶ " + speedText(rate) : "早送り ▶▶";
    }
    if (slider) slider.value = String(rate);
    if (text) { text.textContent = speedText(rate); text.classList.toggle("up", rate > 1); }
  };
  const apply = () => emu.setSpeed(on ? rate : 1);

  const speed = {
    get on() { return on; },
    get rate() { return rate; },
    toggle() { on = !on; apply(); show(); },
    setRate(v) {
      rate = clampSpeed(v);
      try { localStorage.setItem(KEY, String(rate)); } catch (_) { /* いっぱい・使えない */ }
      if (on) apply();
      show();
    },
  };

  for (const b of btns) {
    b.addEventListener("click", () => { emu.unlockAudio(); speed.toggle(); });
    b.addEventListener("contextmenu", (e) => e.preventDefault());
  }
  if (slider) {
    slider.addEventListener("input", () => { if (text) text.textContent = speedText(clampSpeed(slider.value)); });
    slider.addEventListener("change", () => speed.setRate(slider.value));
  }
  show();
  return speed;
}

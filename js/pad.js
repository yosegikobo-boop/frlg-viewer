// 画面のコントローラーとキーボード
//
// [data-key="a"] などのボタン、[data-dpad] の十字キー、[data-fast] の早送り（押しているあいだだけ）。

const KEYMAP = {
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  x: "a", z: "b", a: "l", s: "r", Enter: "start", Backspace: "select",
};
const DIRS = ["up", "down", "left", "right"];

/** 十字キーの中での指の場所 → 押している向き（斜めは2つ） */
export function dpadDirs(dx, dy, radius) {
  const dist = Math.hypot(dx, dy);
  if (dist < radius * 0.22) return [];
  const out = [];
  const a = Math.atan2(dy, dx) * 180 / Math.PI;      // 右が 0、下が 90
  if (a > -157.5 && a < -22.5) out.push("up");
  if (a > 22.5 && a < 157.5) out.push("down");
  if (a > 112.5 || a < -112.5) out.push("left");
  if (a > -67.5 && a < 67.5) out.push("right");
  return out;
}

export function createPad(root, emu) {
  const buzz = () => { if (navigator.vibrate) navigator.vibrate(10); };
  const down = (el, fn) => {
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      try { el.setPointerCapture(e.pointerId); } catch (_) { /* 古いブラウザ */ }
      emu.unlockAudio();
      el.classList.add("on");
      buzz();
      fn(true);
    });
    for (const ev of ["pointerup", "pointercancel", "lostpointercapture"]) {
      el.addEventListener(ev, () => { if (el.classList.contains("on")) { el.classList.remove("on"); fn(false); } });
    }
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  };

  for (const el of root.querySelectorAll("[data-key]")) {
    const key = el.dataset.key;
    down(el, (on) => (on ? emu.press(key) : emu.release(key)));
  }
  for (const el of root.querySelectorAll("[data-fast]")) down(el, (on) => emu.setFast(on));

  // 十字キー: 指をすべらせても向きが変わる
  for (const el of root.querySelectorAll("[data-dpad]")) {
    let held = [], active = null;
    const set = (dirs) => {
      for (const d of DIRS) {
        const was = held.includes(d), now = dirs.includes(d);
        if (was && !now) emu.release(d);
        if (!was && now) { emu.press(d); buzz(); }
        el.classList.toggle("on-" + d, now);
      }
      held = dirs;
    };
    const at = (e) => {
      const r = el.getBoundingClientRect();
      return dpadDirs(e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2), r.width / 2);
    };
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      active = e.pointerId;
      try { el.setPointerCapture(e.pointerId); } catch (_) { /* 古いブラウザ */ }
      emu.unlockAudio();
      set(at(e));
    });
    el.addEventListener("pointermove", (e) => { if (e.pointerId === active) set(at(e)); });
    for (const ev of ["pointerup", "pointercancel", "lostpointercapture"]) {
      el.addEventListener(ev, (e) => { if (e.pointerId === active) { active = null; set([]); } });
    }
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  // キーボード（PC で確かめるとき用）
  const typing = (e) => /^(INPUT|SELECT|TEXTAREA)$/.test((e.target && e.target.tagName) || "");
  window.addEventListener("keydown", (e) => {
    if (typing(e)) return;
    if (e.key === "Tab") { e.preventDefault(); if (!e.repeat) emu.setFast(true); return; }
    const k = KEYMAP[e.key];
    if (!k) return;
    e.preventDefault();
    emu.unlockAudio();
    if (!e.repeat) emu.press(k);
  });
  window.addEventListener("keyup", (e) => {
    if (e.key === "Tab") { emu.setFast(false); return; }
    const k = KEYMAP[e.key];
    if (k) emu.release(k);
  });
}

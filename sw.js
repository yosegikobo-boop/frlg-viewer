// サービスワーカー
//  (1) 全部の返事に COOP・COEP のヘッダーを足す（GitHub Pages はヘッダーを変えられない。mGBA はスレッドを使うので要る）
//  (2) アプリのファイルを覚えて、オフラインで動かす
// VERSION と FILES は tools/build_mobile.py が書き入れる。
const VERSION = "845e82551a69";
const FILES = [
  "frlg/__init__.py",
  "frlg/addresses.py",
  "frlg/calc.py",
  "frlg/cards.py",
  "frlg/core.py",
  "frlg/exp_patch.py",
  "frlg/pk3.py",
  "frlg/rematch.py",
  "frlg/replace.py",
  "frlg/rom.py",
  "frlg/text.py",
  "icon-192.png",
  "icon-512.png",
  "index.html",
  "js/bridge.js",
  "js/emu.js",
  "js/main.js",
  "js/pad.js",
  "js/py.js",
  "js/savetab.js",
  "js/speed.js",
  "js/ui.js",
  "manifest.webmanifest",
  "py/webapp.py",
  "vendor/LICENSE-mgba.txt",
  "vendor/LICENSE-pyodide.txt",
  "vendor/mgba.js",
  "vendor/mgba.wasm",
  "vendor/pyodide/pyodide-lock.json",
  "vendor/pyodide/pyodide.asm.mjs",
  "vendor/pyodide/pyodide.asm.wasm",
  "vendor/pyodide/pyodide.mjs",
  "vendor/pyodide/python_stdlib.zip"
];
const CACHE = "frlg-" + VERSION;

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(FILES.map((f) => new Request(f, { cache: "reload" })));
    // 初めて入れるときは、すぐ動き出す。新しい版に替わるときは、前の版のページが全部閉じるまで待つ
    // （遊んでいる途中で中身が入れ替わらないように）
    if (!self.registration.active) await self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) {
      if (k.startsWith("frlg-") && k !== CACHE) await caches.delete(k);
    }
    await self.clients.claim();
  })());
});

function isolated(res) {
  if (!res || res.status === 0) return res;
  const h = new Headers(res.headers);
  h.set("Cross-Origin-Opener-Policy", "same-origin");
  h.set("Cross-Origin-Embedder-Policy", "require-corp");
  h.set("Cross-Origin-Resource-Policy", "same-origin");
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    // 覚えたものが先、無ければネット。ページそのもの（…/ や ?… つき）は index.html
    const key = req.mode === "navigate" || url.pathname.endsWith("/") ? new URL("index.html", self.registration.scope).href : url.origin + url.pathname;
    const hit = await cache.match(key);
    return isolated(hit || await fetch(req));
  })());
});

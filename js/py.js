// Pyodide（ブラウザで動く Python）を読み込んで、mobile/py/webapp.py を呼ぶ
//
// frlg/ のコードは PC 版と同じもの。公開したものでは ./frlg/*.py にある（tools/build_mobile.py が集める）。

// 読み込む frlg/ のファイル（bridge.py は PC 版だけが使う）。tests/test_build_mobile.py が、漏れが無いか確かめる
export const FRLG_FILES = ["__init__", "addresses", "calc", "cards", "core", "exp_patch", "pk3",
  "rematch", "replace", "rom", "text"];

/**
 * @param romBytes ROM（Uint8Array）
 * @param settings 覚えていた設定（オブジェクト）、wins 勝った回数（オブジェクト）
 * @param onWins 勝った回数が変わったら JSON の文字で呼ぶ
 * @returns {boot, call(name, ...args)}  boot は webapp.boot の返り（ok・species・natures・settings など）
 */
export async function loadPy(romBytes, settings, wins, onWins) {
  const root = new URL("../", import.meta.url);
  const { loadPyodide } = await import("../vendor/pyodide/pyodide.mjs");
  const py = await loadPyodide({ indexURL: new URL("vendor/pyodide/", root).href });
  py.FS.mkdirTree("/app/frlg");
  const files = FRLG_FILES.map((n) => "frlg/" + n + ".py").concat(["py/webapp.py"]);
  await Promise.all(files.map(async (f) => {
    const r = await fetch(new URL(f, root));
    if (!r.ok) throw new Error("読み込めない: " + f);
    const dst = f.startsWith("py/") ? "/app/" + f.slice(3) : "/app/" + f;
    py.FS.writeFile(dst, new Uint8Array(await r.arrayBuffer()));
  }));
  py.runPython("import sys\nif '/app' not in sys.path: sys.path.insert(0, '/app')");
  const mod = py.pyimport("webapp");
  const boot = JSON.parse(mod.boot(romBytes, JSON.stringify(settings || {}), JSON.stringify(wins || {}),
    (s) => { if (onWins) onWins(s); }));
  return {
    boot,
    call(name, ...args) { return mod[name](...args); },
  };
}

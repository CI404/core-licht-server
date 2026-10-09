// CDN 模擬伺服器 v2：從解包出的 OBB 資源直接提供遊戲請求的檔案
//
// 可移植化（2026-10-10）：
//   早期版本把所有路徑寫死成開發機的絕對路徑，換電腦就跑不起來。
//   現在一律讀取 ../config/server.json，相對路徑以【專案根目錄】為基準解析。
//
// 設定檔優先順序：環境變數 LICHT_* > config/server.json > 內建預設
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');          // 專案根目錄
const CFG_FILE = path.join(ROOT, 'config', 'server.json');

function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(CFG_FILE, 'utf8'));
  } catch (e) {
    return {};
  }
}
const CFG = loadConfig();

function cfg(key, defaultVal) {
  const env = process.env['LICHT_' + key.toUpperCase()];
  if (env !== undefined && env !== '') return env;
  if (CFG[key] !== undefined && CFG[key] !== '') return CFG[key];
  return defaultVal;
}

// 相對路徑 → 相對專案根；絕對路徑 → 原樣
function resolvePath(v) {
  if (!v) return null;
  if (path.isAbsolute(v)) return path.normalize(v);
  return path.normalize(path.join(ROOT, v));
}

const PORT = parseInt(cfg('cdn_port', 8080), 10);
const OVERRIDE = resolvePath(cfg('cdn_root', 'cdn/cdnroot'));                 // 覆蓋目錄（優先權最高）
const PATCH = resolvePath(cfg('obb_patch', 'obb/patch/assets'));             // patch OBB 資源
const MAIN = resolvePath(cfg('obb_main', 'obb/main/assets'));                // main OBB 資源
const LOG = resolvePath(cfg('cdn_log', 'runtime/cdn-requests.log'));

// 確保 LOG 目錄存在
try {
  fs.mkdirSync(path.dirname(LOG), { recursive: true });
} catch (e) { /* ignore */ }

function log(line) {
  const s = `[${new Date().toISOString()}] ${line}\n`;
  try { fs.appendFileSync(LOG, s); } catch (e) { /* ignore */ }
  process.stdout.write(s);
}

function pick(file) {
  for (const base of [OVERRIDE, PATCH, MAIN]) {
    if (!base) continue;
    const p = path.join(base, file);
    try {
      if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
    } catch (e) { /* ignore */ }
  }
  return null;
}

const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  let rel = url.replace(/^\/+/, '').replace(/^cdnconfig_[^/]+/, '').replace(/^\/+/, '');
  log(`REQ ${url}`);

  let file = null;
  // .../android_tw/stable/release/config.txt
  if (/android_tw\/stable\/release\/config\.txt$/.test(rel)) {
    file = OVERRIDE ? path.join(OVERRIDE, 'android_tw/stable/release/config.txt') : null;
  } else {
    // .../android_tw/stable/release/<channel>/res/<resource path>
    const m = rel.match(/android_tw\/stable\/release\/([^/]+)\/res\/(.+)$/);
    if (m) file = pick(m[2]);
    else {
      const m2 = rel.match(/android_tw\/stable\/release\/(.+)$/);
      if (m2) file = pick(m2[1]) || pick('ZeroThemePark/tw_mmo/' + path.basename(m2[1]));
    }
  }
  // 通用回退：直接用請求路徑在覆蓋目錄／OBB 資源中尋找
  if (!file) file = pick(rel) || pick(rel.replace(/^[^/]+\//, ''));

  if (file && fs.existsSync(file) && fs.statSync(file).isFile()) {
    const buf = fs.readFileSync(file);
    res.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Content-Length': buf.length });
    res.end(buf);
    log(`  -> 200 ${buf.length}B  ${path.relative(ROOT, file)}`);
  } else {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('not found');
    log(`  -> 404  (rel=${rel})`);
  }
});

server.listen(PORT, '0.0.0.0', () => {
  log(`CDN v2 啟動: 0.0.0.0:${PORT}`);
  log(`  專案根目錄  = ${ROOT}`);
  log(`  覆蓋目錄    = ${OVERRIDE}${fs.existsSync(OVERRIDE) ? '' : '  ← 不存在！'}`);
  log(`  patch 資源  = ${PATCH}${fs.existsSync(PATCH) ? '' : '  ← 不存在！'}`);
  log(`  main 資源   = ${MAIN}${fs.existsSync(MAIN) ? '' : '  ← 不存在！'}`);
  log(`  請求日誌    = ${LOG}`);
});

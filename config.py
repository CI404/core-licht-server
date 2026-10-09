# -*- coding: utf-8 -*-
"""config.py : 專案統一設定入口。

為什麼需要這個檔案
------------------
早期把所有路徑寫死成絕對路徑，換一台電腦、換一個磁碟就完全跑不起來。
這個模組把它們統一成「相對於專案根目錄」，並允許用 `config/server.json` 覆寫。

使用方式（其他模組）：
    import config as CFG
    CFG.ROOT          # 專案根目錄
    CFG.DECODED       # 配置表目錄（data/decoded）
    CFG.PROTO         # proto 目錄（data/proto）
    CFG.LOG_PATH      # 伺服器日誌
    CFG.CAPTURE_PATH  # 封包擷取檔
    CFG.OBB_MAIN      # 原廠 main OBB 解包後的 assets 目錄
    CFG.OBB_PATCH     # 原廠 patch OBB 解包後的 assets 目錄
    CFG.PUBLIC_HOST   # 回給客戶端的對外主機（給 select_region 用）

優先順序：環境變數 > config/server.json > 內建預設（相對路徑）
環境變數名稱：LICHT_ROOT / LICHT_HOST / LICHT_LOGIN_PORT / LICHT_GAME_PORT
              LICHT_OBB_MAIN / LICHT_OBB_PATCH / LICHT_CDN_ROOT
"""
import json
import os
import sys

# 讓本模組在「命令提示字元 (GBK)」下也能正常輸出中文與符號。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ----------------------------------------------------------------------
# 專案根目錄 = 本檔案所在目錄
# ----------------------------------------------------------------------
ROOT = os.environ.get("LICHT_ROOT") or os.path.dirname(os.path.abspath(__file__))


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_CFG_FILE = os.path.join(ROOT, "config", "server.json")
_CFG = _load_json(_CFG_FILE)


def cfg(key, default=None):
    """先讀環境變數（LICHT_<KEY大寫>），再讀 server.json，最後用 default。"""
    env = os.environ.get("LICHT_" + key.upper())
    if env not in (None, ""):
        return env
    if key in _CFG:
        return _CFG[key]
    return default


def resolve(value, default_rel):
    """把設定值解析成絕對路徑。

    - 空值 → 用 default_rel（相對於 ROOT）
    - 相對路徑 → 相對於 ROOT
    - 絕對路徑 → 原樣使用（方便指向專案外的既有目錄，例如已解包的 OBB 資源）
    """
    v = value or default_rel
    if not v:
        return None
    if os.path.isabs(v):
        return os.path.normpath(v)
    return os.path.normpath(os.path.join(ROOT, v))


# ----------------------------------------------------------------------
# 路徑設定
# ----------------------------------------------------------------------
DECODED = resolve(cfg("decoded"), os.path.join("data", "decoded"))
PROTO = resolve(cfg("proto"), os.path.join("data", "proto"))
DATA_DIR = resolve(cfg("data_dir"), "data")

RUNTIME_DIR = resolve(cfg("runtime_dir"), "runtime")
LOG_PATH = resolve(cfg("log"), os.path.join("runtime", "mock-server.log"))
CAPTURE_PATH = resolve(cfg("capture"), os.path.join("runtime", "tcp-capture.jsonl"))
CDN_LOG = resolve(cfg("cdn_log"), os.path.join("runtime", "cdn-requests.log"))

CDN_ROOT = resolve(cfg("cdn_root"), os.path.join("cdn", "cdnroot"))
OBB_MAIN = resolve(cfg("obb_main"), "obb/main/assets")
OBB_PATCH = resolve(cfg("obb_patch"), "obb/patch/assets")

# 可選：反編譯 Lua 源碼（只用於 log 對齊例外，不存在也能跑）
LUA_SRC = resolve(cfg("lua_src"), os.path.join("data", "lua-src"))

# ----------------------------------------------------------------------
# 網路設定
# ----------------------------------------------------------------------
PUBLIC_HOST = cfg("host", "10.0.2.2")          # 回給客戶端的 IP（模擬器預設 10.0.2.2）
LOGIN_PORT = int(cfg("login_port", 9001))      # HTTP 登入服 + 遊戲服 TCP（同埠雙協定）
GAME_PORT = int(cfg("game_port", 9001))
CDN_PORT = int(cfg("cdn_port", 8080))

# ----------------------------------------------------------------------
# 啟動時自我檢查
# ----------------------------------------------------------------------
def sanity_report():
    """回傳 (是否通過, 訊息列表)。讓啟動腳本可以提早發現問題。"""
    msgs = []
    ok = True

    for name, path in (("配置表目錄", DECODED), ("proto 目錄", PROTO)):
        if path and os.path.isdir(path):
            n = len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])
            msgs.append(f"  [OK] {name}: {path}  ({n} 檔)")
        else:
            msgs.append(f"  [!!] {name} 不存在: {path}")
            ok = False

    for name, path in (("main OBB assets", OBB_MAIN), ("patch OBB assets", OBB_PATCH)):
        if path and os.path.isdir(path):
            msgs.append(f"  [OK] {name}: {path}")
        else:
            msgs.append(f"  [!!] {name} 不存在: {path}  ← CDN 會無法供應遊戲資源")
            ok = False

    if CDN_ROOT and os.path.isdir(CDN_ROOT):
        msgs.append(f"  [OK] CDN 覆蓋目錄: {CDN_ROOT}")
    else:
        msgs.append(f"  [!!] CDN 覆蓋目錄不存在: {CDN_ROOT}")

    msgs.append(f"  [--] 對外主機: {PUBLIC_HOST}   登入/遊戲埠: {LOGIN_PORT}   CDN 埠: {CDN_PORT}")
    return ok, msgs


def ensure_runtime_dirs():
    for d in (RUNTIME_DIR, os.path.dirname(LOG_PATH), os.path.dirname(CAPTURE_PATH)):
        if d:
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    print("專案根目錄 :", ROOT)
    print("設定檔     :", _CFG_FILE, "(存在)" if os.path.exists(_CFG_FILE) else "(不存在，使用預設)")
    print()
    ok, msgs = sanity_report()
    print("環境檢查：")
    for m in msgs:
        print(m)
    print()
    print("結果:", "全部通過 [OK]" if ok else "有項目缺失 [X]（見上方 [!!]）")
    sys.exit(0 if ok else 1)

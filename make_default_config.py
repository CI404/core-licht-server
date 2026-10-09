# -*- coding: utf-8 -*-
"""make_default_config.py : 在缺少 config/server.json 時建立一份預設設定。

用途：使用者從 GitHub clone 下來時，若設定檔遺失（或你不想把設定檔進版控），
     執行本腳本即可還原一份可用的預設值。

手動用法：
    python make_default_config.py
    python make_default_config.py 192.168.1.100    # 順便指定對外主機
"""
import io
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG_DIR = os.path.join(ROOT, "config")
CFG_FILE = os.path.join(CFG_DIR, "server.json")

DEFAULT = {
    "_說明": "這是本專案唯一需要手動修改的檔案。改完存檔，重新啟動伺服器即可生效。",

    "host": "10.0.2.2",
    "_host說明": "回給遊戲客戶端的『伺服器位址』。模擬器(MuMu/雷電)填 10.0.2.2；真機填你電腦的區網 IP。用 scripts\\2-顯示本機IP.bat 可查詢。",

    "login_port": 9001,
    "_login_port說明": "登入服(HTTP) + 遊戲服(TCP) 共用這個埠。若被佔用可改成 9002 等。",

    "cdn_port": 8080,
    "_cdn_port說明": "CDN 資源伺服器埠號。若被佔用可改。",

    "decoded": "data/decoded",
    "_decoded說明": "遊戲配置表(365 個 DataTable_*.rows.json)。玩家所有數值都從這裡推導。",

    "proto": "data/proto",
    "_proto說明": "協定描述檔(64 個 .bin + msgmap.json + playerattrs.json)。",

    "cdn_root": "cdn/cdnroot",
    "_cdn_root說明": "CDN 覆蓋目錄。內含 serv_list.txt(伺服器清單) 與公告檔，優先權最高。",

    "obb_main": "obb/main/assets",
    "_obb_main說明": "【必改】原廠 main OBB 解包後的 assets 目錄。CDN 會從這裡讀遊戲資源。可填相對路徑（相對於本專案根目錄）或絕對路徑。",

    "obb_patch": "obb/patch/assets",
    "_obb_patch說明": "【必改】原廠 patch OBB 解包後的 assets 目錄。",

    "log": "runtime/mock-server.log",
    "capture": "runtime/tcp-capture.jsonl",
    "cdn_log": "runtime/cdn-requests.log",
    "_log說明": "執行期輸出。相對路徑 = 相對於本專案根目錄。",
}


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else None

    cfg = dict(DEFAULT)
    if host:
        cfg["host"] = host

    os.makedirs(CFG_DIR, exist_ok=True)

    if os.path.exists(CFG_FILE):
        print(f"[--] {CFG_FILE} 已存在，未覆蓋。")
        print("     若要重新建立，請先把它改名或刪除。")
        return 0

    with io.open(CFG_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg, ensure_ascii=False, indent=2))
        f.write("\n")

    print(f"[OK] 已建立 {CFG_FILE}")
    print(f"     對外主機 host = {cfg['host']}")
    if not host:
        print("     若要用真機，請改成你電腦的區網 IP（scripts\\2-顯示本機IP.bat 可查）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

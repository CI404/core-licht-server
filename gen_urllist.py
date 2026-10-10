# -*- coding: utf-8 -*-
"""gen_urllist.py : 產生遊戲客戶端要用的 UrlList_Android.txt。

背景（為什麼需要這個工具）
--------------------------
遊戲客戶端會讀 OBB 內的 `assets/UrlList_Android.txt` 決定「去哪裡抓 CDN 資源」，
原廠寫的是 `https://pfdh-cdnres.rhinosgamestw.com`（已下線），
所以必須改成指向你電腦上跑的 CDN 伺服器（`cdn/server2.js`）。

⚠️ 長度限制（實測）
    原廠檔案 = 598 bytes，無填充
    修改後檔案 = 598 bytes（JSON 本體 + 尾部空白填充）
    也就是 OBB 內這個檔案是【固定 598 bytes 的槽位】，
    所以要嘛剛好 598 bytes，要嘛就得改 OBB 的 CRC/大小（不建議）。

用法
----
    python gen_urllist.py                 # 讀 config/server.json 產生
    python gen_urllist.py 192.168.1.100   # 指定 IP 覆寫
    python gen_urllist.py 192.168.1.100 8080

輸出
----
    output/UrlList_Android.txt            # 要覆蓋到裝置 OBB 的檔案（598 bytes）
    output/UrlList_Android.原始.json      # 未填充的內容，方便檢視
"""
import json
import os
import sys

# 讓本腳本在「命令提示字元 (GBK)」下也能正常輸出中文與符號。
# 實測：未設定時會拋 UnicodeEncodeError: 'gbk' codec can't encode character '\u2705'
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import config as CFG  # noqa: E402

SLOT_SIZE = 598  # 固定槽位大小（實測值，勿改）

# ★★★ 這個值極度重要，改錯會導致遊戲跳出 SDK 登入彈窗 ★★★
#
# 客戶端 x.Module.Login.Control.LoginControl.lua:185-194：
#     if "tw_debug_888" == LoginModel.versionCustomContent.server then
#         LoginModel.isDevTest = true
#         LoginModel.isSdkEnabled = false                       -- 關閉 SDK
#         UIClassHelper.UIClass.LoginView.OpenSubViewDev()      -- 開開發者登入界面
#     else
#         SdkLogin()                                            -- 跳出官方/FB/Google 登入彈窗
#
# 所以：
#   tw_debug_888   → 開發者模式（離線遊玩要用這個）
#   tw_release_*   → 啟用 SDK，會卡在登入彈窗
DEFAULT_SERVER = "tw_debug_888"


def build(host, port, server=None):
    """組出 UrlList 物件。

    注意：`versionCustomContent` 內含 Lua 表 `{isRelease=true, ...}`，
    若用 str.format() 會被當成佔位符而爆炸（實測 KeyError），
    所以這裡用 f-string 直接組，並原樣保留大括號。
    """
    base = f"http://{host}:{port}"
    srv = server or DEFAULT_SERVER
    return {
        "baseUrl": base + "/cdnconfig_{0}/",
        "configFileUrl": base + "/cdnconfig_{0}/android_tw/stable/release/config.txt",
        "gameReleaseVersion": "X202308261705",
        "updatePackageUrl": base + "/cdnconfig_{0}/android_tw/stable/release/{1}/updatePackage",
        "updateUrl": base + "/cdnconfig_{0}/android_tw/stable/release/{1}/res",
        "useBackup": base + "/|" + base + "/",
        "versionCustomContent": "return {isRelease=true, server='" + srv + "'}",
    }


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else CFG.PUBLIC_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else CFG.CDN_PORT
    server = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_SERVER

    print("=" * 66)
    print("  UrlList_Android.txt 產生器")
    print("=" * 66)
    print(f"  對外主機 : {host}")
    print(f"  CDN 埠號 : {port}")
    print(f"  server   : {server}   {'[開發者模式]' if server == DEFAULT_SERVER else '[注意：非 tw_debug_888，可能跳 SDK 登入]'}")
    print(f"  槽位大小 : {SLOT_SIZE} bytes（OBB 固定值）")
    print()

    obj = build(host, port, server)
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    raw = body.encode("utf-8")

    if len(raw) > SLOT_SIZE:
        print(f"  [X] 內容 {len(raw)} bytes 超過槽位 {SLOT_SIZE} bytes！")
        print("      → IP 太長。請縮短主機字串（例如改用較短的區網 IP）。")
        return 1

    padded = raw + b" " * (SLOT_SIZE - len(raw))

    outdir = os.path.join(ROOT, "output")
    os.makedirs(outdir, exist_ok=True)

    out_txt = os.path.join(outdir, "UrlList_Android.txt")
    with open(out_txt, "wb") as f:
        f.write(padded)

    out_json = os.path.join(outdir, "UrlList_Android.未填充.json")
    with open(out_json, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))

    print(f"  JSON 本體 : {len(raw)} bytes")
    print(f"  空白填充  : {SLOT_SIZE - len(raw)} bytes")
    print(f"  輸出總長  : {len(padded)} bytes  {'[OK] 正確' if len(padded) == SLOT_SIZE else '[X] 錯誤'}")
    print()
    print("  已產生：")
    print(f"    {out_txt}")
    print(f"    {out_json}")
    print()
    print("  下一步：")
    print("    scripts\\4-部署到設備.bat   （用 adb 推到裝置）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

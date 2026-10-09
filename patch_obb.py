# -*- coding: utf-8 -*-
"""patch_obb.py : 在電腦上就地改寫 OBB 內的 UrlList（不需要 root）。

用途
----
`scripts\\4-部署到設備.bat` 是在裝置上直接 `dd` 寫入。
若裝置的 OBB 目錄不給寫（權限不足、或你想先改好再推），就用本工具：

    1) adb pull 把 OBB 拉到電腦
    2) python patch_obb.py <obb檔案> [--which main|patch]
    3) adb push 推回去

已知的 UrlList 位置（實測）
--------------------------
    main.138.com.tw99.no23.an.obb   offset 1528431122   598 bytes
    patch.138.com.tw99.no23.an.obb  offset 1519062275   598 bytes

用法
----
    python patch_obb.py D:\\obb\\main.138.com.tw99.no23.an.obb
    python patch_obb.py D:\\obb\\patch.138.com.tw99.no23.an.obb --which patch
    python patch_obb.py D:\\obb\\xxx.obb --dry-run     # 只檢查，不寫入
"""
import argparse
import os
import shutil
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# OBB 內的 UrlList 槽位（2026-10-10 實測修正，勿改）
#
# ⚠️ 重要修正歷史：
#   原本以為 UrlList 在 main OBB 的 offset 1528431122。
#   實際用 adb exec-out 直接撈位元組驗證後發現：
#     main  @ 1528431122 → "UnityFS..."           ← 這是 assets/Zero/Lua/lua.ab！
#     main  @ 1528431084 → "assets/Zero/Lua/lua.ab" + lua.ab 資料
#     patch @ 1519062275 → {"baseUrl":"http://...  ← ★ UrlList 在這裡
#     patch @ 1519062233 → 檔名區塊 + UrlList 資料
#   所以 UrlList **只存在於 patch OBB**。main OBB 沒有這個檔案。
SLOTS = {
    "patch": {"offset": 1519062275, "size": 598},
    # main 保留 key 以便 --which main 時能給出明確錯誤
    "main":  None,
}


def detect_which(path):
    """依檔名猜是 main 還是 patch。"""
    name = os.path.basename(path).lower()
    if "patch" in name:
        return "patch"
    if "main" in name:
        return "main"
    return None


def main():
    ap = argparse.ArgumentParser(description="就地改寫 OBB 內的 UrlList")
    ap.add_argument("obb", help="OBB 檔案路徑")
    ap.add_argument("--which", choices=["main", "patch"], default=None,
                    help="指定是 main 還是 patch（預設依檔名自動判斷）")
    ap.add_argument("--urllist", default=None,
                    help="要寫入的 UrlList 檔案（預設 output/UrlList_Android.txt）")
    ap.add_argument("--dry-run", action="store_true", help="只檢查不寫入")
    ap.add_argument("--no-backup", action="store_true", help="不要備份原檔（不建議）")
    args = ap.parse_args()

    obb = os.path.abspath(args.obb)
    if not os.path.isfile(obb):
        print(f"[X] 找不到 OBB：{obb}")
        return 1

    which = args.which or detect_which(obb)
    if which is None:
        print("[X] 無法從檔名判斷是 main 還是 patch，請加 --which main 或 --which patch")
        return 1
    slot = SLOTS.get(which)
    if slot is None:
        print(f"[X] {which} OBB 裡【沒有】UrlList_Android.txt。")
        print("    實測：UrlList 只存在於 patch OBB（offset 1519062275）。")
        print("    main OBB 的那個位置是 assets/Zero/Lua/lua.ab，不是 UrlList。")
        print("    → 請改用 patch.138.com.tw99.no23.an.obb")
        return 1

    urllist = args.urllist or os.path.join(ROOT, "output", "UrlList_Android.txt")
    if not os.path.isfile(urllist):
        print(f"[X] 找不到 UrlList：{urllist}")
        print("    請先執行：scripts\\3-產生UrlList.bat")
        return 1

    data = open(urllist, "rb").read()

    print("=" * 68)
    print("  OBB 就地改寫工具")
    print("=" * 68)
    print(f"  OBB 檔案   : {obb}")
    print(f"  大小       : {os.path.getsize(obb):,} bytes")
    print(f"  類型       : {which}")
    print(f"  槽位位移   : {slot['offset']:,}")
    print(f"  槽位大小   : {slot['size']} bytes")
    print(f"  UrlList    : {urllist}")
    print(f"  UrlList 大小: {len(data)} bytes")
    print()

    if len(data) != slot["size"]:
        print(f"  [X] UrlList 大小必須是 {slot['size']} bytes，目前 {len(data)}。")
        print("      這代表產生器參數有誤，或 host 太長。請重新產生。")
        return 1

    # 檢查位移是否在檔案範圍內
    if slot["offset"] + slot["size"] > os.path.getsize(obb):
        print("  [X] 位移超出檔案範圍，這不是預期的 OBB 嗎？")
        return 1

    # 讀出舊內容供對照
    with open(obb, "rb") as f:
        f.seek(slot["offset"])
        old = f.read(slot["size"])
    old_txt = old.decode("utf-8", "replace").rstrip()
    new_txt = data.decode("utf-8", "replace").rstrip()

    print("  改寫前：")
    print(f"    {old_txt[:150]}")
    print("  改寫後：")
    print(f"    {new_txt[:150]}")
    print()

    if old == data:
        print("  [--] 內容相同，不需要改寫。")
        return 0

    if args.dry_run:
        print("  [--] --dry-run 模式，未寫入。")
        return 0

    # 備份
    if not args.no_backup:
        bak = obb + ".bak"
        if not os.path.exists(bak):
            print(f"  備份原檔 → {bak}")
            shutil.copy2(obb, bak)
        else:
            print(f"  備份已存在，沿用 → {bak}")
        print()

    # 就地寫入
    print("  寫入中...")
    t0 = time.time()
    with open(obb, "r+b") as f:
        f.seek(slot["offset"])
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    print(f"  寫入完成（{time.time() - t0:.1f}s）")

    # 驗證
    with open(obb, "rb") as f:
        f.seek(slot["offset"])
        check = f.read(slot["size"])
    if check == data:
        print("  [OK] 驗證通過，寫入內容與來源一致。")
    else:
        print("  [X] 驗證失敗！寫入後讀回不一致，請用備份還原。")
        return 1

    print()
    print("  下一步：")
    print("    adb push \"" + obb + "\" /sdcard/Android/obb/com.tw99.no23.an/")
    print("    adb shell pm clear com.tw99.no23.an")
    return 0


if __name__ == "__main__":
    sys.exit(main())

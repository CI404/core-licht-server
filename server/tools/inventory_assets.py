#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盤點 licht-offline 專案裡已解包的【角色模型資源】，並對應到 children_skin。

用途：回答「到底有多少角色資源可用、能不能做圖鑑」這個問題。
      不做任何修改，只讀取與統計。

★ 2026-10-10：使用者的重要提醒 ——
  `E:\\核心：利希特\\licht-offline` 已由前幾任 AI 解包【完整資源】，
  且前幾任已在 README 中明確否決「用 Web UI 重寫遊戲界面」的路線。
  本工具只做「資源盤點」，供判斷是否值得做圖鑑類的附屬產物。

用法：
    python tools/inventory_assets.py                    # 預設掃描 licht-offline
    python tools/inventory_assets.py --root "E:\\..."   # 指定專案根
    python tools/inventory_assets.py --json out.json
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

import player_data as PD  # noqa: E402

DEFAULT_ROOT = r"E:\核心：利希特\licht-offline"

# 模型目錄命名：a01003_02_body / live2d_a04007_01 / 100101_01 / 9003001
RE_SPINE_PART = re.compile(r"^(?:spine_)?([a-zA-Z]?\d{5,7})(?:_(\w+))?$")
RE_LIVE2D = re.compile(r"^(?:live2d_|TL_)?([a-zA-Z]?\d{5,7})(?:_(\d+))?$")


def count_files(d):
    n = 0
    size = 0
    for _dp, _dn, fns in os.walk(d):
        for fn in fns:
            n += 1
            try:
                size += os.path.getsize(os.path.join(_dp, fn))
            except OSError:
                pass
    return n, size


def list_dirs(d):
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))


def main():
    ap = argparse.ArgumentParser(description="角色模型資源盤點")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()
    root = args.root

    print("=" * 74)
    print("  角色模型資源盤點")
    print("=" * 74)
    print("  根目錄：%s" % root)
    print()

    # ---- 建立 children_skin 索引 ----
    skins = PD.table("children_skin")
    by_head, by_name = {}, collections.defaultdict(list)
    for r in skins:
        try:
            by_head[int(r.get("head_new"))] = r
        except Exception:
            pass
        if r.get("name"):
            by_name[r["name"]].append(r)
    print("  children_skin：%d 筆（%d 個不重複角色名）"
          % (len(skins), len(by_name)))
    print()

    result = {}

    # ---- 1) assets\spine ----
    spine_dir = os.path.join(root, "assets", "spine")
    spine_dirs = list_dirs(spine_dir)
    if spine_dirs:
        # 依「角色編號」聚合（去掉 _bg1/_body 等部件後綴）
        groups = collections.defaultdict(list)
        for name in spine_dirs:
            m = RE_SPINE_PART.match(name)
            key = m.group(1) if m else name
            groups[key].append(name)
        nf, sz = count_files(spine_dir)
        print("  【assets\\spine】模型資料夾 %d 個 → 聚合後角色 %d 個（%d 檔, %.0f MB）"
              % (len(spine_dirs), len(groups), nf, sz / 1e6))
        matched = 0
        for key in sorted(groups):
            hit = by_head.get(_to_int(key))
            if hit:
                matched += 1
        print("     其中能對到 children_skin.head_new 的：%d / %d"
              % (matched, len(groups)))
        result["spine"] = {
            "dir": spine_dir, "folders": len(spine_dirs),
            "groups": {k: v for k, v in sorted(groups.items())},
            "files": nf, "bytes": sz, "matched": matched,
        }
        # 列出前 20 組
        for i, key in enumerate(sorted(groups)):
            if i >= 20:
                print("     …（其餘 %d 組）" % (len(groups) - 20))
                break
            hit = by_head.get(_to_int(key))
            tag = ("→ %s" % hit.get("name")) if hit else "（未對上）"
            print("     %-12s %2d 部件  %s" % (key, len(groups[key]), tag))
        print()

    # ---- 2) assets\live2d ----
    l2d_dir = os.path.join(root, "assets", "live2d")
    l2d_dirs = list_dirs(l2d_dir)
    if l2d_dirs:
        nf, sz = count_files(l2d_dir)
        print("  【assets\\live2d】模型 %d 個（%d 檔, %.0f MB）"
              % (len(l2d_dirs), nf, sz / 1e6))
        matched = 0
        for name in l2d_dirs:
            m = RE_LIVE2D.match(name)
            if m and by_head.get(_to_int(m.group(1))):
                matched += 1
        print("     其中能對到 head_new 的：%d / %d" % (matched, len(l2d_dirs)))
        for name in l2d_dirs:
            m = RE_LIVE2D.match(name)
            hit = by_head.get(_to_int(m.group(1))) if m else None
            tag = ("→ %s" % hit.get("name")) if hit else ""
            print("     %-24s %s" % (name, tag))
        result["live2d"] = {"dir": l2d_dir, "models": l2d_dirs,
                            "files": nf, "bytes": sz, "matched": matched}
        print()

    # ---- 3) raw\lua-src 規模 ----
    for sub in ("lua-src", "lua-src-hoist"):
        d = os.path.join(root, "raw", sub)
        if os.path.isdir(d):
            nf = len([f for f in os.listdir(d) if f.endswith(".lua")])
            print("  【raw\\%s】Lua 模組 %d 個" % (sub, nf))
    print()

    # ---- 4) 音頻 ----
    audio_dir = os.path.join(root, "assets", "audio")
    if os.path.isdir(audio_dir):
        nf, sz = count_files(audio_dir)
        print("  【assets\\audio】%d 檔, %.0f MB" % (nf, sz / 1e6))
        print()

    if args.json_out:
        with io.open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("  [OK] 已寫出 %s" % args.json_out)
    return 0


def _to_int(s):
    m = re.search(r"(\d{5,7})", str(s))
    return int(m.group(1)) if m else -1


if __name__ == "__main__":
    sys.exit(main())

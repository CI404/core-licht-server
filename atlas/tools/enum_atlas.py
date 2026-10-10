#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""適格體圖鑑資料匯出工具。

★ 2026-10-10 由使用者發現的關鍵知識（見 docs/適格體圖鑑-編號對照.md）：

    適格體界面中，每個角色的面板上方會顯示一串編號。
    那串編號是 **`DataTable_children_skin.head_new`**（6 位數）或
    **`DataTable_children_skin.skin_pic`**（5 位數），
    而且**直接對應到反編譯出來的立繪檔名**：

        card_pic_<head_new>.png     ← 卡面小圖（約 100 KB）
        card_<skin_pic>.png         ← 卡面大圖（約 1~3 MB）

    範例（實測）：
        head_new=300501 → skin_id=1430050001 → 角色「林檎」
        head_new=600901 → skin_id=1460090001
        skin_pic=100104 → skin_id=1406100104

本工具把兩邊對起來，輸出 JSON，用來重建適格體圖鑑（web 或任何前端）。

用法：
    python tools/enum_atlas.py                        # 只列統計與對應
    python tools/enum_atlas.py --json out.json        # 匯出完整 JSON
    python tools/enum_atlas.py --live2d "E:\\路徑"    # 指定 live2d 資源目錄
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # atlas/tools
ATLAS_DIR = os.path.dirname(HERE)                          # atlas
PROJ_DIR = os.path.dirname(ATLAS_DIR)                      # 專案根
SERVER_DIR = os.path.join(PROJ_DIR, "server")               # server（player_data 在此）
sys.path.insert(0, SERVER_DIR)

import player_data as PD  # noqa: E402

# 預設的 Live2D / 立繪資源目錄（可用 --live2d 覆寫）
DEFAULT_LIVE2D_DIRS = [
    r"E:\核心：利希特\核心live2d",
    r"C:\licht\raw\obb\main\assets\ZeroThemePark\tw\Zero\UI\Texture",
]

RE_CARD_PIC = re.compile(r"^card_pic_(\d+)\.png$")
RE_CARD = re.compile(r"^card_(\d+)\.png$")
RE_CONFIG = re.compile(r"\.config\.json$")


def scan_live2d(root):
    """掃描資源目錄，回傳 {head_new: [路徑...]}, {skin_pic: [路徑...]}, {模型名: {...}}。"""
    by_head, by_skinpic, models = {}, {}, {}
    if not root or not os.path.isdir(root):
        return by_head, by_skinpic, models

    for dirpath, _dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        for fn in filenames:
            full = os.path.join(dirpath, fn)

            m = RE_CARD_PIC.match(fn)
            if m:
                by_head.setdefault(int(m.group(1)), []).append(full)
                continue
            m = RE_CARD.match(fn)
            if m:
                by_skinpic.setdefault(int(m.group(1)), []).append(full)
                continue
            if RE_CONFIG.search(fn):
                # 模型設定檔 → 記錄模型名（相對目錄名）
                name = os.path.basename(dirpath)
                try:
                    cfg = json.load(io.open(full, encoding="utf-8-sig"))
                except Exception:
                    cfg = {}
                models.setdefault(name, {
                    "dir": dirpath,
                    "config": full,
                    "skeleton": cfg.get("skeleton"),
                    "textures": (cfg.get("atlases") or [{}])[0].get("textures", []),
                    "motions": list((cfg.get("motions") or {}).keys()),
                })
    return by_head, by_skinpic, models


def build_index():
    """建立 children_skin 的兩套編號索引。"""
    by_head, by_skinpic = {}, {}
    for r in PD.table("children_skin"):
        try:
            sid = int(r.get("id"))
        except Exception:
            continue
        for key, bucket in (("head_new", by_head), ("skin_pic", by_skinpic)):
            try:
                bucket.setdefault(int(r.get(key)), []).append(r)
            except Exception:
                continue
    return by_head, by_skinpic


def main():
    ap = argparse.ArgumentParser(description="適格體圖鑑資料匯出")
    ap.add_argument("--live2d", action="append", default=None,
                    help="資源目錄（可多次指定；預設掃描已知路徑）")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="輸出 JSON 檔路徑")
    args = ap.parse_args()

    roots = args.live2d or [d for d in DEFAULT_LIVE2D_DIRS if os.path.isdir(d)]

    print("=" * 72)
    print("  適格體圖鑑資料匯出")
    print("=" * 72)
    print("  掃描目錄：")
    for r in roots:
        print("    %s" % r)
    print()

    all_head, all_skin, all_models = {}, {}, {}
    for r in roots:
        bh, bs, bm = scan_live2d(r)
        for k, v in bh.items():
            all_head.setdefault(k, []).extend(v)
        for k, v in bs.items():
            all_skin.setdefault(k, []).extend(v)
        all_models.update(bm)

    idx_head, idx_skinpic = build_index()

    print("  資源統計：")
    print("    card_pic_<head_new>.png   編號 %d 個" % len(all_head))
    print("    card_<skin_pic>.png       編號 %d 個" % len(all_skin))
    print("    Live2D 模型設定檔          %d 個" % len(all_models))
    print("    children_skin 皮膚總數     %d 個" % len(PD.table("children_skin")))
    print()

    entries = []
    ok = miss = 0
    for n in sorted(all_head):
        hit = idx_head.get(n)
        rec = {
            "head_new": n,
            "card_pic": all_head[n],
            "card": all_skin.get(n, []),
        }
        if hit:
            r = hit[0]
            rec.update({
                "skin_id": int(r.get("id")),
                "name": r.get("name"),
                "painter": r.get("painter"),
                "model": r.get("model"),
                "spine_id": r.get("spine_id"),
                "match": True,
            })
            ok += 1
        else:
            rec["match"] = False
            miss += 1
        entries.append(rec)

    # 只有 card_<skin_pic> 的（5 位數）
    skin_entries = []
    for n in sorted(all_skin):
        if n in all_head:
            continue
        hit = idx_skinpic.get(n)
        rec = {"skin_pic": n, "card": all_skin[n]}
        if hit:
            r = hit[0]
            rec.update({
                "skin_id": int(r.get("id")),
                "name": r.get("name"),
                "painter": r.get("painter"),
                "match": True,
            })
        else:
            rec["match"] = False
        skin_entries.append(rec)

    print("  編號對應（head_new → 角色）：")
    for e in entries:
        if e.get("match"):
            print("    %-8s ✅ skin_id=%-12s %-8s painter=%s"
                  % (e["head_new"], e["skin_id"], e.get("name"), e.get("painter")))
        else:
            print("    %-8s ❌ 對不到 children_skin" % e["head_new"])
    print()
    print("  合計：對上 %d，對不上 %d（head_new）" % (ok, miss))
    print("  另有 skin_pic（5 位）%d 筆" % len(skin_entries))

    models_out = []
    for name, m in sorted(all_models.items()):
        models_out.append({"model": name, **m})
    if models_out:
        print()
        print("  Live2D 模型（%d）：" % len(models_out))
        for m in models_out:
            print("    %-14s skeleton=%s" % (m["model"], m.get("skeleton")))

    if args.json_out:
        payload = {
            "generated_by": "tools/enum_atlas.py",
            "note": "head_new 對應 card_pic_<head_new>.png；skin_pic 對應 card_<skin_pic>.png",
            "scanned_dirs": roots,
            "entries": entries,
            "skin_pic_entries": skin_entries,
            "live2d_models": models_out,
        }
        with io.open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print()
        print("  [OK] 已寫出 %s" % args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

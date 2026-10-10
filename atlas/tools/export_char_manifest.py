#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色資源全清單匯出（適格體圖鑑的正式資料來源）。

★ 2026-10-10 修正：先前 `enum_atlas.py` 只用 `card_pic_<head_new>.png` 猜檔名，
  那只覆蓋 61 個。**正確的權威對照表是 `DataTable_spine`**：

      children_skin.head_new  ==  DataTable_spine.id
                                        │
                                        └──→  DataTable_spine.path
                                                    │
                                                    └──→  assets\\spine\\<path>\\
                                                              ├── *.skel   骨骼
                                                              ├── *.atlas  圖集
                                                              └── *.png    貼圖

  實測：`DataTable_spine` 263 行中
        · 257 行的 path 在磁碟上找得到（99.6%）
        · 204 行的 id 能對到 `children_skin.head_new`

用法：
    python tools/export_char_manifest.py --json out.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # atlas/tools
ATLAS_DIR = os.path.dirname(HERE)                          # atlas
PROJ_DIR = os.path.dirname(ATLAS_DIR)                      # 專案根
SERVER_DIR = os.path.join(PROJ_DIR, "server")               # server（player_data 在此）
sys.path.insert(0, SERVER_DIR)

import player_data as PD  # noqa: E402

DEFAULT_ROOT = r"E:\核心：利希特\licht-offline"


def main():
    ap = argparse.ArgumentParser(description="角色資源全清單匯出")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()
    root = args.root

    spine_dir = os.path.join(root, "assets", "spine")
    on_disk = set(os.listdir(spine_dir)) if os.path.isdir(spine_dir) else set()

    spine_rows = json.load(io.open(
        os.path.join(root, "raw", "decoded", "DataTable_spine.rows.json"),
        encoding="utf-8"))
    skins = PD.table("children_skin")

    by_head = {}
    for r in skins:
        try:
            by_head[int(r.get("head_new"))] = r
        except Exception:
            pass

    entries = []
    for r in spine_rows:
        try:
            sid = int(r.get("id"))
        except Exception:
            continue
        path = r.get("path") or ""
        skin = by_head.get(sid)
        d = os.path.join(spine_dir, path) if path else ""
        files = sorted(os.listdir(d)) if d and os.path.isdir(d) else []
        entries.append({
            "spine_id": sid,
            "path": path,
            "on_disk": bool(path) and path in on_disk,
            "files": files,
            "skin_id": int(skin["id"]) if skin and str(skin.get("id", "")).isdigit() else None,
            "name": (skin or {}).get("name"),
            "painter": (skin or {}).get("painter"),
            "head_new": (skin or {}).get("head_new"),
            "skin_pic": (skin or {}).get("skin_pic"),
            "para": r.get("para"),
            "scenario_para": r.get("scenario_para"),
            "click": [c[0] for c in (r.get("click") or []) if isinstance(c, list) and c],
            "enter_voice_id": r.get("enter_voice_id"),
            "is_show_main_bg": r.get("is_show_main_bg"),
            "need_connect_anim": r.get("need_connect_anim"),
        })

    tot = len(entries)
    named = sum(1 for e in entries if e["name"])
    disk = sum(1 for e in entries if e["on_disk"])
    withskel = sum(1 for e in entries if any(f.endswith(".skel") for f in e["files"]))
    clicks = sum(1 for e in entries if e["click"])

    print("=" * 70)
    print("  角色資源清單（權威來源：DataTable_spine）")
    print("=" * 70)
    print("  總行數            : %d" % tot)
    print("  能對到角色名       : %d  (%.1f%%)" % (named, 100.0 * named / tot))
    print("  path 在磁碟上      : %d  (%.1f%%)" % (disk, 100.0 * disk / tot))
    print("  含 .skel 骨骼檔    : %d" % withskel)
    print("  有 click 互動動作  : %d" % clicks)
    print()
    print("  對照表（前 20 筆）：")
    for e in entries[:20]:
        print("    %-7s %-18s %-8s skel=%s click=%d"
              % (e["spine_id"], e["path"], e["name"] or "-",
                 "Y" if any(f.endswith(".skel") for f in e["files"]) else "N",
                 len(e["click"])))

    if args.json_out:
        with io.open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({
                "generated_by": "tools/export_char_manifest.py",
                "source": "DataTable_spine.rows.json + DataTable_children_skin.rows.json",
                "mapping": "children_skin.head_new == DataTable_spine.id -> DataTable_spine.path -> assets/spine/<path>/",
                "root": root,
                "stats": {"total": tot, "named": named, "on_disk": disk,
                          "with_skel": withskel, "with_click": clicks},
                "entries": entries,
            }, f, ensure_ascii=False, indent=2)
        print()
        print("  [OK] 已寫出 %s" % args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

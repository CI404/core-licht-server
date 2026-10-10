#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「瞳」專項 — 全形態與皮膚對照匯出。

★ 2026-10-10 由使用者發起的專項：
  瞳（Hitomi）是《核芯：利希特》最特殊的角色 ——

    1. **唯一有多個號碼段的角色**
       · 100000 ~ 100007    （8 個，job = 2/1/3/7/4/5/6/9）
       · 9100001 ~ 9100007  （7 個，平行的特殊版，單皮膚）
       其他角色只有 4 位數編號（1001 ~ 9001）。

    2. **fullname 全部是「亞述桐」**（使用者的線索，已驗證）
       在 `DataTable_children` 中，name='瞳' 的 15 行 fullname 都是「亞述桐」。

    3. **有 32 個皮膚**（children_skin），是第二名（舊影 7 個）的 4.5 倍。

    4. **不在 `DataTable_spine` 裡**（其餘角色在那裡有立繪排版資料）
       → 瞳的資源走獨立載入路徑（待查）。

本工具把所有相關編號與皮膚整理成一份 JSON，供專項復刻使用。

用法：
    python tools/hitomi_manifest.py --json ../data/瞳-全形態清單.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 瞳/tools
HITOMI_DIR = os.path.dirname(HERE)                         # 瞳

# `player_data.py` 在專案版的 server\ 底下。
# 本腳本可能放在 E:\核心：利希特\瞳\tools\（與專案不同槽），
# 所以要用候選清單找，不能只靠相對路徑。
_PROJ_CANDIDATES = [
    r"D:\核心：GM服务 打包项目",
    os.path.join(os.path.dirname(HITOMI_DIR), "核心：GM服务 打包项目"),
    os.path.join(os.path.dirname(HITOMI_DIR), "GM服务 打包项目"),
]
PROJ_DIR = next((p for p in _PROJ_CANDIDATES if os.path.isdir(os.path.join(p, "server"))),
                _PROJ_CANDIDATES[0])
SERVER_DIR = os.path.join(PROJ_DIR, "server")
sys.path.insert(0, SERVER_DIR)

import player_data as PD  # noqa: E402

DEFAULT_ROOT = r"E:\核心：利希特\licht-offline"
NAME = "瞳"
CREATOR = "亞述桐"


def main():
    ap = argparse.ArgumentParser(description="瞳 專項對照匯出")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()
    root = args.root

    # ---- 1) 角色（形態）----
    children = PD.table("children")
    forms = sorted([r for r in children if r.get("name") == NAME],
                   key=lambda r: int(r.get("id", 0)))

    # ---- 2) 皮膚 ----
    skins = PD.table("children_skin")
    skin_by_id = {}
    for r in skins:
        try:
            skin_by_id[int(r.get("id"))] = r
        except Exception:
            pass

    # ---- 3) DataTable_spine（瞳預期不在）----
    spine_rows = []
    p = os.path.join(root, "raw", "decoded", "DataTable_spine.rows.json")
    if os.path.exists(p):
        spine_rows = json.load(io.open(p, encoding="utf-8"))
    spine_by_id = {}
    for r in spine_rows:
        try:
            spine_by_id[int(r.get("id"))] = r
        except Exception:
            pass

    # ---- 4) 組裝 ----
    all_skin_ids = set()
    form_out = []
    for r in forms:
        sl = [int(x) for x in (r.get("skin_list") or [])]
        all_skin_ids.update(sl)
        form_out.append({
            "id": int(r.get("id")),
            "fullname": r.get("fullname"),
            "job": r.get("job"),
            "subjob": r.get("subjob"),
            "race": r.get("race"),
            "star": r.get("star"),
            "weight": r.get("weight"),
            "is_hero": r.get("is_hero"),
            "attack_rang": r.get("attack_rang"),
            "attack_speed": r.get("attack_speed"),
            "speed": r.get("speed"),
            "pvp_cost": r.get("pvp_cost"),
            "cost": r.get("cost"),
            "skin_list": sl,
            "fetter_skin_list": [int(x) for x in (r.get("fetter_skin_list") or [])],
            "fetter_break_limit": r.get("fetter_break_limit"),
            "in_spine_table": int(r.get("id", 0)) in spine_by_id,
            "spine_path": (spine_by_id.get(int(r.get("id", 0))) or {}).get("path"),
            "skins": [{
                "id": s,
                "exists": s in skin_by_id,
                "name": (skin_by_id.get(s) or {}).get("name"),
                "head_new": (skin_by_id.get(s) or {}).get("head_new"),
                "skin_pic": (skin_by_id.get(s) or {}).get("skin_pic"),
                "painter": (skin_by_id.get(s) or {}).get("painter"),
                "model": (skin_by_id.get(s) or {}).get("model"),
                "spine_id": (skin_by_id.get(s) or {}).get("spine_id"),
            } for s in sl],
        })

    # 反向：哪些皮膚屬於瞳（children_skin.name == 瞳）
    own_skins = sorted([{
        "id": int(r.get("id")),
        "head_new": r.get("head_new"),
        "skin_pic": r.get("skin_pic"),
        "painter": r.get("painter"),
        "model": r.get("model"),
        "spine_id": r.get("spine_id"),
        "referenced_by_forms": [int(f["id"]) for f in form_out
                                if int(r.get("id", 0)) in f["skin_list"]],
    } for r in skins if r.get("name") == NAME],
        key=lambda x: x["id"])

    missing = sorted(s for s in all_skin_ids if s not in skin_by_id)

    payload = {
        "generated_by": "瞳/tools/hitomi_manifest.py",
        "subject": NAME,
        "creator_alias": CREATOR,
        "note": "瞳的 fullname 全部是「亞述桐」；有兩個平行的號碼段 10000X 與 910000X；"
                "且不在 DataTable_spine 中（獨立資源路徑）。",
        "stats": {
            "forms": len(form_out),
            "forms_main": len([f for f in form_out if f["id"] < 9000000]),
            "forms_special": len([f for f in form_out if f["id"] >= 9000000]),
            "distinct_skin_ids_referenced": len(all_skin_ids),
            "skins_owned": len(own_skins),
            "skins_missing_in_table": missing,
            "forms_in_spine_table": len([f for f in form_out if f["in_spine_table"]]),
        },
        "forms": form_out,
        "skins_owned": own_skins,
    }

    print("=" * 72)
    print("  瞳 專項對照匯出")
    print("=" * 72)
    print("  形態總數            : %d" % len(form_out))
    print("    正式 (10000X)     : %d" % payload["stats"]["forms_main"])
    print("    特殊 (910000X)    : %d" % payload["stats"]["forms_special"])
    print("  引用的皮膚 id（去重）: %d" % len(all_skin_ids))
    print("  children_skin 中屬於瞳: %d" % len(own_skins))
    print("  ❌ 引用但不存在的皮膚  : %s" % (missing or "無"))
    print("  在 DataTable_spine 中  : %d（預期 0）"
          % payload["stats"]["forms_in_spine_table"])
    print()
    print("  形態 ↔ 皮膚：")
    for f in form_out:
        names = ",".join(
            (s["name"] or "?") + ("✅" if s["exists"] else "❌")
            for s in f["skins"])
        print("    %-9s job=%-3s skin_list=%-34s %s"
              % (f["id"], f["job"], str(f["skin_list"]), names))

    if args.json_out:
        with io.open(args.json_out, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        print()
        print("  [OK] 已寫出 %s" % args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

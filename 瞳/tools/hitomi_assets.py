#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「瞳」專項 — 實體資源盤點。

掃描 `licht-offline` 內所有與瞳相關的模型／貼圖／動畫，統計檔案數與大小。

瞳的資源代號（實測）：
    E01001        ← 主系列（16 個模型目錄）
    E01001_f01    ← 戰損／特殊態系列
    E01003        ← 另一系列（有 spine + live2d，但無皮膚引用 → 未實裝？）
    n00003 / n00008 / n00060 / 100101  ← 待確認是否瞳相關

用法：
    python tools/hitomi_assets.py --json ../data/瞳-資源盤點.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

DEFAULT_ROOT = r"E:\核心：利希特\licht-offline"

# 瞳的資源代號前綴
CODES = ("E01001", "E01003")


def scan_dir(path):
    """回傳 (檔案數, 總位元組, 副檔名統計)。"""
    n = size = 0
    ext = {}
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            n += 1
            try:
                size += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
            e = os.path.splitext(fn)[1].lower()
            ext[e] = ext.get(e, 0) + 1
    return n, size, ext


def main():
    ap = argparse.ArgumentParser(description="瞳 實體資源盤點")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()
    root = args.root

    result = {"root": root, "codes": list(CODES), "groups": {}}

    # ---- 1) Avatar prefab ----
    av = os.path.join(root, "raw", "obb", "main", "assets",
                      "EVA", "Characters", "Avatar")
    av_hits = []
    if os.path.isdir(av):
        for lv in sorted(os.listdir(av)):
            lvp = os.path.join(av, lv)
            if not os.path.isdir(lvp):
                continue
            for sub in sorted(os.listdir(lvp)):
                if not any(sub.upper().startswith(c) for c in CODES):
                    continue
                p = os.path.join(lvp, sub)
                if not os.path.isdir(p):
                    continue
                n, size, ext = scan_dir(p)
                av_hits.append({
                    "level": lv, "name": sub, "path": p,
                    "files": n, "bytes": size, "ext": ext,
                })
    result["groups"]["avatar_prefab"] = av_hits

    # ---- 2) spine ----
    sp = os.path.join(root, "assets", "spine")
    sp_hits = []
    if os.path.isdir(sp):
        for d in sorted(os.listdir(sp)):
            if not any(c.lower() in d.lower() for c in CODES):
                continue
            p = os.path.join(sp, d)
            if not os.path.isdir(p):
                continue
            n, size, ext = scan_dir(p)
            skel = [f for f in os.listdir(p) if f.endswith(".skel")]
            sp_hits.append({"name": d, "files": n, "bytes": size,
                            "ext": ext, "skel": skel})
    result["groups"]["spine"] = sp_hits

    # ---- 3) live2d ----
    l2 = os.path.join(root, "assets", "live2d")
    l2_hits = []
    if os.path.isdir(l2):
        for d in sorted(os.listdir(l2)):
            if not any(c.lower() in d.lower() for c in CODES):
                continue
            p = os.path.join(l2, d)
            if not os.path.isdir(p):
                continue
            n, size, ext = scan_dir(p)
            l2_hits.append({"name": d, "files": n, "bytes": size, "ext": ext})
    result["groups"]["live2d"] = l2_hits

    # ---- 4) 音效（檔名含代號）----
    au = os.path.join(root, "assets", "audio")
    au_hits = []
    if os.path.isdir(au):
        for dp, _dn, fns in os.walk(au):
            for fn in fns:
                if any(c.lower() in fn.lower() for c in CODES):
                    fp = os.path.join(dp, fn)
                    try:
                        au_hits.append({"file": fn,
                                        "rel": os.path.relpath(fp, au),
                                        "bytes": os.path.getsize(fp)})
                    except OSError:
                        pass
    result["groups"]["audio"] = au_hits

    # ---- 輸出 ----
    print("=" * 74)
    print("  瞳 實體資源盤點")
    print("=" * 74)

    print()
    print("  【1】Unity Prefab（%s）— %d 個目錄"
          % ("EVA/Characters/Avatar", len(av_hits)))
    tot_n = tot_b = 0
    for h in av_hits:
        tot_n += h["files"]; tot_b += h["bytes"]
        ex = ",".join("%s×%d" % (k or "(無)", v)
                      for k, v in sorted(h["ext"].items(), key=lambda x: -x[1])[:4])
        print("      Avatar\\%s\\%-18s %4d 檔  %7.2f MB   %s"
              % (h["level"], h["name"], h["files"], h["bytes"] / 1e6, ex))
    print("      小計：%d 檔, %.2f MB" % (tot_n, tot_b / 1e6))

    print()
    print("  【2】Spine 資源（assets\\spine）— %d 個目錄" % len(sp_hits))
    n2 = b2 = 0
    for h in sp_hits:
        n2 += h["files"]; b2 += h["bytes"]
        print("      %-30s %3d 檔  %7.3f MB  skel=%d"
              % (h["name"], h["files"], h["bytes"] / 1e6, len(h["skel"])))
    print("      小計：%d 檔, %.2f MB" % (n2, b2 / 1e6))

    print()
    print("  【3】Live2D 資源（assets\\live2d）— %d 個模型" % len(l2_hits))
    n3 = b3 = 0
    for h in l2_hits:
        n3 += h["files"]; b3 += h["bytes"]
        print("      %-30s %4d 檔  %7.3f MB" % (h["name"], h["files"], h["bytes"] / 1e6))
    print("      小計：%d 檔, %.2f MB" % (n3, b3 / 1e6))

    print()
    print("  【4】音效檔名含代號 — %d 個" % len(au_hits))
    for h in au_hits[:12]:
        print("      %-46s %8.1f KB" % (h["rel"], h["bytes"] / 1024))
    if len(au_hits) > 12:
        print("      …（其餘 %d 個）" % (len(au_hits) - 12))

    print()
    print("  ── 總計：%d 檔, %.2f MB ──"
          % (tot_n + n2 + n3 + len(au_hits),
             (tot_b + b2 + b3 + sum(h["bytes"] for h in au_hits)) / 1e6))

    if args.json_out:
        with io.open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print()
        print("  [OK] 已寫出 %s" % args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

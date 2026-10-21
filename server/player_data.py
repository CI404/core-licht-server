# -*- coding: utf-8 -*-
"""player_data.py : 離線「滿級全角色解鎖」玩家資料生成器。

**設計原則（重要）**
------------------
所有數值一律**從遊戲自己的配置表推導**，不手寫魔法數字。
前一版把玩家等級硬寫成 999、精神力 1/1、資源全 0 卻宣稱 113 個滿級角色，
造成資料自相矛盾 —— 客戶端拿去算上限／紅點／可購買狀態就會邏輯錯誤。
現在每一個數字都有出處：

| 數值 | 來源 |
|---|---|
| 玩家等級 100 | `DataTable_lvl` 的最大 `lvl` |
| 精神力上限 140 | 該等級的 `vit_max` |
| 好友上限 10 | 該等級的 `friend_max` |
| 法陣格數 3 | 該等級的 `spell_slots` |
| 升下一級經驗 82740 | 該等級的 `exp` |
| 角色等級 3★100/4★110/5★130/6★150 | `DataTable_children_lvl` 各星級的最大 `lvl` |
| 角色星級 | `DataTable_children.star` |
| 皮膚 | `DataTable_children.skin_list` |
| 屬性 id ↔ 名稱 | `x.Game.PlayerDefine.lua` 的 `ATTR_SERVER_DRIVEN`（→ `proto/playerattrs.json`）|
"""
import json
import os
import sys
import time
import functools

# ---- 可移植化：路徑一律由專案根的 config.py 決定（見 config/server.json）----
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as CFG

DECODED = CFG.DECODED
PROTO = CFG.PROTO

# ---------- 帳號識別（這兩個是「伺服器決定」的值，不是配置表數值）----------
ROLE_ID = 10001
ROLE_NAME = "指揮官"
SERVER_ID = 1

# 預設看板娘（助理）角色 id —— 使用者 2026-10-11 指定為 100001。
# 用於 11_23 children_assist_info_s2c 的 `index`（指向 list 中該角色的第一筆皮膚）。
# 100001 是「正式瞳」（is_informal=0，有 4 個皮膚），資源齊全。
ROLE_ASSIST_DEFAULT_ID = 100001


# ======================================================================
# 配置表存取
# ======================================================================
@functools.lru_cache(maxsize=None)
def table(name):
    p = os.path.join(DECODED, f"DataTable_{name}.rows.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@functools.lru_cache(maxsize=1)
def player_attrs():
    """屬性 id(str) -> 名稱。來自 PlayerDefine.lua。"""
    p = os.path.join(PROTO, "playerattrs.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@functools.lru_cache(maxsize=1)
def attr_id_by_name():
    """名稱 -> 屬性 id(int)。"""
    return {v: int(k) for k, v in player_attrs().items()}


# ======================================================================
# 玩家等級（DataTable_lvl）—— 唯一真實來源
# ======================================================================
@functools.lru_cache(maxsize=1)
def lvl_rows():
    return sorted(table("lvl"), key=lambda r: int(r.get("lvl", 0)))


@functools.lru_cache(maxsize=1)
def max_player_level():
    rows = lvl_rows()
    return int(rows[-1]["lvl"]) if rows else 1


@functools.lru_cache(maxsize=1)
def max_level_row():
    rows = lvl_rows()
    return rows[-1] if rows else {}


def row_for_level(lv):
    """取得某等級的配置列（找不到就回最接近的較低等級）。"""
    best = None
    for r in lvl_rows():
        if int(r.get("lvl", 0)) <= lv:
            best = r
        else:
            break
    return best or (lvl_rows()[0] if lvl_rows() else {})


def vit_max(level=None):
    return int(row_for_level(level or max_player_level()).get("vit_max", 0))


def friend_max(level=None):
    return int(row_for_level(level or max_player_level()).get("friend_max", 0))


def spell_slots(level=None):
    return int(row_for_level(level or max_player_level()).get("spell_slots", 0))


def next_level_exp(level=None):
    return int(row_for_level(level or max_player_level()).get("exp", 0))


# ======================================================================
# 角色（DataTable_children / children_lvl / children_skill_lvl / children_favor_lvl）
# ======================================================================
@functools.lru_cache(maxsize=1)
def children_rows():
    return table("children")


@functools.lru_cache(maxsize=1)
def star_max_lvl():
    """星級 -> 等級上限（DataTable_children_lvl 實測：3★100 / 4★110 / 5★130 / 6★150）。"""
    out = {}
    for r in table("children_lvl"):
        try:
            s, lv = int(r["star"]), int(r["lvl"])
        except Exception:
            continue
        out[s] = max(out.get(s, 0), lv)
    return out


@functools.lru_cache(maxsize=1)
def init_hero_sys_id():
    """預設英雄 id（`DataTable_config` 的 `key='init_hero'`）。

    客戶端 `x.Module.Hero.HeroDefine.lua:5-10` 就是這樣讀的：
        L1_1 = DataBase.GetSysconfigByKey("init_hero")
        L0_1.DefaultHeroSysId = L1_1.value
    實測值 = 1001（角色「厄莉希」，5★，正式角色 is_informal=0）。

    用途：`HeroModel.GetDefaultHeroCardInfo()` 會用這個 id 去查 heroList，
    查不到就 return nil → `L0_3.children_id` 索引 nil → LuaException
    → CardAssistCardSubView.UpdateAssistCardList 中斷 → **助理界面白屏**。
    """
    for r in table("config"):
        if (r.get("_key") or r.get("key")) == "init_hero":
            try:
                return int(r.get("value"))
            except Exception:
                break
    return 1001


@functools.lru_cache(maxsize=1)
def done_scenario_ids():
    """回報給客戶端的「已完成劇本 id 清單」（給 `26_4 scenario_happened_s2c` 用）。

    為什麼需要（完整證據鏈，2026-10-10）：
      客戶端 `x.Module.Scenario.ScenarioModel.lua:769-797` `UpdateFinishedList`：
          for i = 1, #A0_3 do
            finishedList[i].sys_id = A0_3[i].k     -- k = 劇本 id
            finishedList[i].times  = A0_3[i].v     -- v = 完成次數
          end
          finishedListInited = true
      這是**唯一**填充 `finishedList` 的地方，而 `ScenarioControl`（未反編譯的
      82KB 位元組碼，字串表 [133] `IgnoreSend_26_2` 緊鄰 [134] `Send_26_2`）
      用它決定要不要送出 `26_2 scenario_enter_c2s`。

      伺服器原本對 26_4 回**空清單** → `finishedList` 永遠是空的
      → `IgnoreSend_26_2` 判斷失敗 → 客戶端把 `26_2` 連送 **83 次**
      （log 實測：`(無 s2c 對照，略過 26_2)`）。

    取哪些 id：`DataTable_scenario` 的 id 分布為
      1~100（100 個核心劇情，含「序章-作戰指引」id=16、「序章-編隊上厄莉希」id=25）、
      101~1000（442 個）、1001~10000（8 個）、其餘（212 個）。
      這裡回報 1~1000 的核心線性劇情（客戶端要的 id=16 在內），
      不動大型活動/支線 id，避免造出遊戲沒預期的狀態。
    """
    out = []
    for r in table("scenario"):
        v = r.get("id")
        if v is None:
            v = r.get("_key")
        try:
            v = int(v)
        except Exception:
            continue
        if 0 < v <= 1000:
            out.append(v)
    return sorted(set(out))


@functools.lru_cache(maxsize=1)
def valid_skin_ids():
    """`DataTable_children_skin` 裡【真實存在】的皮膚 id 集合。

    為什麼需要它（實測證據，非猜測）：
      `DataTable_children.skin_list` 對「未實裝／佔位角色」含有配置表查不到的 id：
        id=100007  (瞳) skin_list=[701, 702, 703, 1701]           → 1701 不存在
        id=9100007 (瞳) skin_list=[91000071, 91000073, 91000072]  → 三個全不存在
      若照抄推送，客戶端查表拿到 nil 並印出：
        [Logger][ERROR] not find 91000071, in table children_skin
      （logcat 實測出現，每次進皮膚／助理界面都刷一次）
    因此一律以本表為準做白名單過濾。
    """
    out = set()
    for r in table("children_skin"):
        v = r.get("id")
        if v is None:
            v = r.get("_key")
        try:
            out.add(int(v))
        except Exception:
            continue
    return out


@functools.lru_cache(maxsize=1)
def skin_by_child():
    """角色 id -> 皮膚 id 清單（已用 `valid_skin_ids()` 過濾掉配置表不存在的 id）。

    ⚠ 2026-10-11 曾在此加入「跨角色污染」與「id 空間碰撞」兩種過濾，
      但兩者都**經實測否定**，已全部回退（勿再嘗試，詳見 docs §0.5.3）：
        * 「跨角色污染」：誤判 —— `children_skin` 中 `id=101/401/…` 的 `name`
          都是「瞳」、`model` 各異、`spine_id=10000000` ⇒ 都是瞳的合法皮膚。
        * 「id 空間碰撞」（剔除 `1001`）：會**導致瞳無法儲存為看板娘**。
      結論：`DataTable_children.skin_list` 的內容是正確的，不需過濾。
    """
    valid = valid_skin_ids()
    out = {}
    for r in children_rows():
        cid = int(r.get("id") or r["_key"])
        out[cid] = [int(x) for x in (r.get("skin_list") or []) if int(x) in valid]
    return out


@functools.lru_cache(maxsize=1)
def skin_to_child():
    """皮膚 id -> **擁有該皮膚的角色 id**（`skin_by_child()` 的反查）。

    ★ 2026-10-11 新增。用於修「助理設定點瞳的頭像卻顯示厄莉希」。

    為什麼需要反查：客戶端點頭像時送出的 `11_7` 是
        `{ index, id, skin_id }`，其中 **`id` 不可靠** ——
    實測點「瞳」時送來 `id=1001, skin_id=101`，而
        `skin 101`  屬於角色 **100001（瞳）**
        `id 1001`   卻是角色 **1001（厄莉希）**
    兩者相差一個數量級的命名空間。若採信 `id` 就會取到厄莉希。

    反查安全性：實測 328 顆皮膚中**沒有任何一顆被兩個角色引用**（0 筆衝突），
    故可無歧義地由 `skin_id` 決定角色 id。
    驗證：`101→[100001]`、`1001→[100000]`、`1410010001→[1001]`。

    回傳值為 `{skin_id: child_id}`；若同一顆皮膚意外對應多個角色，
    該鍵不會出現（呼叫端應退回其他依據）。
    """
    rev = {}
    for cid, skins in skin_by_child().items():
        for s in skins:
            rev.setdefault(s, []).append(cid)
    return {s: cs[0] for s, cs in rev.items() if len(cs) == 1}


@functools.lru_cache(maxsize=1)
def default_hero_children_id():
    """**預設英雄的 `children_id`**（= 瞳的基礎角色 id，實測 `100000`）。

    ★★ 2026-10-11 新增。這是「助理界面點瞳的頭像卻顯示厄莉希」的**真正根因修復**。

    【為什麼需要這個函式】
      `DataTable_config['init_hero'].value` = **1001**，那是**瞳的「英雄 id」**
      （`hero.id`，見 `DataTable_hero`）。而同表顯示：
          hero.id=1001  children_id=100000  form=1  order=1  name=瞳-強襲形態
          hero.id=1001  children_id=100002  form=2  order=2  瞳-火力形態
          …（共 8 個形態，order 1..8）
      ⇒ **瞳的「角色 id」是 100000，不是 1001。**

      但 `1001` 同時又是**角色 1001（厄莉希）的 children id** —— 兩套 id 撞號。
      先前的 `_handle_35_1()` 直接把 `h.children_id = init_hero`（=1001），
      客戶端拿 `children_id=1001` 去解析 ⇒ 得到**厄莉希** ⇒ 助理大圖顯示厄莉希。
      （這正是使用者觀察到的「點瞳顯示厄莉希」。）

    【取值規則】
      在 `DataTable_hero` 中取 `id == init_hero` 的所有列，
      選 **`order` 最小**者（實測 order=1 ⇒ 瞳-強襲形態），回傳其 `children_id`（=100000）。
      `order` 缺失時退回最小 `children_id`。
    """
    hid = init_hero_sys_id()
    rows = []
    for r in table("hero"):
        try:
            if int(r.get("id")) != int(hid):
                continue
        except Exception:
            continue
        try:
            rows.append((int(r.get("order", 999) or 999),
                         int(r.get("children_id"))))
        except Exception:
            continue
    if not rows:
        return hid
    rows.sort()
    return rows[0][1]


@functools.lru_cache(maxsize=1)
def star_by_child():
    out = {}
    for r in children_rows():
        cid = int(r.get("id") or r["_key"])
        out[cid] = int(r.get("star", 5))
    return out


@functools.lru_cache(maxsize=1)
def max_skill_lvl_by_child():
    out = {}
    for r in table("children_skill_lvl"):
        cid = r.get("children_id")
        if cid is None:
            continue
        out[int(cid)] = max(out.get(int(cid), 0), int(r.get("lvl", 0)))
    return out


@functools.lru_cache(maxsize=1)
def max_favor_lvl_by_child():
    out = {}
    for r in table("children_favor_lvl"):
        cid = r.get("id")
        if cid is None:
            continue
        out[int(cid)] = max(out.get(int(cid), 0), int(r.get("lvl", 0)))
    return out


@functools.lru_cache(maxsize=1)
def max_awake_times_by_child():
    """角色 id -> **該角色在 `children_awake` 的真實覺醒上限（`times`）**。

    ★ 2026-10-11 新增。修「所有角色最後兩條語音永遠上鎖」。

    實測 `DataTable_children_awake`（537 條，欄位含 `id` / `times` / `max_lvl` …）：
        每角色最大 times 分布 = {4: 106, 0: 7}
        瞳(100001) = 4、赫茲(4008) = 4

    用途：`p_children.awake_times`。客戶端 `GetDocumentVoiceInfo` 用它判定
    「突破等級N解鎖」的語音是否開放（詳見 `build_maxed_child` 的註解）。
    """
    out = {}
    for r in table("children_awake"):
        cid = r.get("id")
        if cid is None:
            continue
        try:
            cid = int(cid)
            out[cid] = max(out.get(cid, 0), int(r.get("times", 0) or 0))
        except Exception:
            continue
    return out


@functools.lru_cache(maxsize=1)
def favor_value_by_child():
    """角色 id -> **滿好感度時 `favor` 該填的值**（= 最高等級的 `range_max`）。

    ★ 2026-10-11（使用者指正後定案）：`favor_lvl` 就是該角色的最高等級（多為 **5**），
      **不是畸形** —— 使用者明確指出「上限就是 lv5 而不是 lv4」。
      要讓客戶端顯示 100%，`favor` 必須填該等級的 `range_max`。

    以瞳(100001) 為例（實測資料）：
        lvl=0  [       0 ~    1999]
        lvl=1  [    2000 ~   31999]
        lvl=2  [   32000 ~  111999]
        lvl=3  [  112000 ~  351999]
        lvl=4  [  352000 ~ 1251999]
        lvl=5  [ 1252000 ~ 1252000]   ← 上限

    客戶端公式（`DocumentView` L1187-1246）：
        文本 = (favor - cur.range_min) .. "/" .. (cur.range_max - cur.range_min)
    代入 lvl=5、favor=1252000 ⇒ (1252000-1252000)/(1252000-1252000) = 0/0

    ⇒ **滿級時進度條走另一條分支**（`favor_lvl == DocumentDefine.MaxFavorLvl` ⇒ 直接設 1），
      所以文字為 0/0 是「滿級」的正常表現，不是資料錯誤。

    歷史（勿重蹈）：
      * `favor = 0` 寫死 ⇒ 顯示 `-1252000/0`（明顯錯誤）
      * `favor = range_min` ⇒ 仍 `0/0`
      * 把 `favor_lvl` 改成 1 ⇒ 顯示 `-7%`，且**檔案仍未解鎖**（已回退）
    """
    lvl_of = max_favor_lvl_by_child()
    out = {}
    for r in table("children_favor_lvl"):
        cid = r.get("id")
        if cid is None:
            continue
        try:
            cid = int(cid)
            if int(r.get("lvl", 0)) != lvl_of.get(cid):
                continue
            out[cid] = int(r.get("range_max", 0) or 0)
        except Exception:
            continue
    return out


def all_children():
    return sorted(int(r.get("id") or r["_key"]) for r in children_rows())


@functools.lru_cache(maxsize=1)
def unsafe_children():
    """**資料不全、推送會讓客戶端崩潰**的角色 id 集合。

    ★ 2026-10-11 修訂（使用者要求：未實裝的適格體也應顯示）。

    前一次做法是「排除所有 is_informal == 1」→ 113 個只剩 83 個，
    把 30 個**未實裝但資料完整**的角色（多蘿西、洛思特、霞珀、朱心亞、
    盧卡、維穆爾、荊索、鏡莉、潘昔、妮瑟琳、測試系列…）一起藏掉了。

    實測資料（data/decoded）：
      children            113 筆
      children_favor_lvl  106 筆
      children_favor      106 筆
      → 缺的正是 7 個「瞳」佔位符：9100001 ~ 9100007

    故改為**只排除真正缺資料者**：凡在 children_favor_lvl 或
    children_favor 查不到的 id，開啟檔案時 cfg 為 nil，
    DocumentView.UpdateFavorInfo 會 attempt to index a nil value。
    113 - 7 = **106** 個角色可安全顯示，與 favor 表覆蓋數一致。
    """
    have = set()
    for tname in ("children_favor_lvl", "children_favor"):
        for r in table(tname):
            v = r.get("id")
            if v is None:
                v = r.get("children_id")
            try:
                if v is not None:
                    have.add(int(v))
            except Exception:
                continue
    missing = set()
    for r in children_rows():
        try:
            cid = int(r.get("id") or r["_key"])
        except Exception:
            continue
        if cid not in have:
            missing.add(cid)
    return missing


@functools.lru_cache(maxsize=1)
def formal_children():
    """可安全推送給客戶端的角色 id 清單（106 個）。

    ★ 2026-10-11：改為「排除資料不全者」而非「排除未實裝者」。
      未實裝（is_informal == 1）但資料完整的角色**照樣顯示**。
      113 個角色中只有 7 個「瞳」佔位符缺 favor 資料 → 保留 106 個。

    歷史（保留供回溯）：原本排除全部 is_informal != 0，理由是同批「瞳」
    佔位符缺表會崩潰（DocumentView.lua:891 UpdateFavorInfo）；
    但連帶藏掉了 23 個資料完整的角色，使用者要求改回顯示。
    """
    bad = unsafe_children()
    out = []
    for r in children_rows():
        try:
            cid = int(r.get("id") or r["_key"])
        except Exception:
            continue
        if cid in bad:
            continue
        out.append(cid)
    return sorted(set(out))


@functools.lru_cache(maxsize=1)
def formal_children_set():
    return set(formal_children())


def is_formal_child(cid):
    """該角色是否已實裝（可安全推送給客戶端）。"""
    try:
        return int(cid) in formal_children_set()
    except Exception:
        return False


def all_skins():
    out = []
    for cid in all_children():
        out.extend(skin_by_child().get(cid, []))
    return sorted(set(out))


def formal_skins():
    """**已實裝角色**的皮膚（給 11_46 用）。

    未實裝角色的皮膚 id 就算存在於 `children_skin`，其對應的卡面／Spine
    資源（如 `card_pic_100903.ab`）也不在 OBB 裡，推了只會讓客戶端 404。
    """
    out = []
    for cid in formal_children():
        out.extend(skin_by_child().get(cid, []))
    return sorted(set(out))


def child_level(cid):
    """該角色在自身星級下的滿級。"""
    return star_max_lvl().get(star_by_child().get(cid, 5), 1)


# ======================================================================
# 空島（基建）房間 — DataTable_room
# ======================================================================
# 為什麼需要（2026-10-10 修正「點空島卡 90%」）：
#   客戶端 x.Module.Build.BuildTool.lua:3206-3215 `CheckCanUpgradByCondList`
#   在 cond_type == 1 的分支：
#       L10_2 = BuildModel.GetRoomInfoBySysId(sys_id)
#       L11_2 = L10_2.info          ← 若 GetRoomInfoBySysId 回 false → 崩潰
#   而 GetRoomInfoBySysId 是查 BuildModel.roomModel，該表由 `31_1
#   building_info_s2c` 的 room_list 填充。伺服器原本走通用回應器，
#   room_list 是空的 → 查不到 → `attempt to index a boolean value`
#   → 整個 LoadLandAndRoom 中斷 → 進度條卡 90%。
#
# 房型（實測）：7 種，每種 lvl 1~15
#   10001 中樞房間(type1) / 10002 工作室A / 10003 宅邸A /
#   10004 工作室B / 10005 宅邸B / 10006 工作室C / 10007 宅邸C
@functools.lru_cache(maxsize=1)
def room_tiers():
    """房型 id -> 該房型所有等級的資料列（已排序）。"""
    out = {}
    for r in table("room"):
        try:
            rid = int(r.get("id"))
        except Exception:
            continue
        out.setdefault(rid, []).append(r)
    for rid in out:
        out[rid].sort(key=lambda x: int(x.get("lvl", 0)))
    return out


@functools.lru_cache(maxsize=1)
def maxed_rooms():
    """回傳每個房型的「最高等級」資料，供 `31_1 building_info_s2c` 使用。

    為什麼取最高等級：滿級時所有 `cond_list`（類型 1 = 要求某房型 ≥ N）
    都自然滿足，客戶端不會走進「條件不足」的錯誤分支。

    回傳 [(sys_id, lvl, row), ...]，依 sys_id 排序。
    """
    out = []
    for rid in sorted(room_tiers()):
        rows = room_tiers()[rid]
        if not rows:
            continue
        top = rows[-1]
        out.append((rid, int(top.get("lvl", 1)), top))
    return out


@functools.lru_cache(maxsize=1)
def max_atoms():
    """中樞房間的 atoms 上限（給 p_building_center.highest_atoms / atoms_index）。"""
    best = 0
    for r in table("room"):
        try:
            best = max(best, int(r.get("atoms_max", 0) or 0))
        except Exception:
            pass
    return best


# 空島物件型別（BuildDefine.ObjectType）：1 = Machine（機器）、2 = Furniture（家具）
OBJECT_TYPE_MACHINE = 1
OBJECT_TYPE_FURNITURE = 2


@functools.lru_cache(maxsize=1)
def room_object_ids(obj_type=None):
    """`DataTable_room_object` 的 id 清單（可依 type 過濾）。

    ★ 2026-10-10：為什麼需要這個（修「點空島子項目卡 85%」）
      logcat 崩潰堆疊：
          BuildRoomView.InitMainView → EnterEditMode → CleanObjectStatus
            → UpdateEditRed → GetMachineBagList
          ?:-1: attempt to index a nil value
      `BuildModel.lua:5996-6050` GetMachineBagList：
          for _, obj in pairs(BuildModel.allObjectBagInfo) do
              cfg = DataBase.GetSysroom_objectByKey(obj.sys_id)
              if cfg.type == ObjectType.Machine then ...   -- cfg 是 nil → 崩潰
          end
      `allObjectBagInfo` 由 `31_15 building_spare_object_info_s2c` 填充。
      伺服器原本沒有 31_15 handler → 通用回應器用 `_fill_required` 造出
      「一個假元素」，其 sys_id 被填成 `1001`（那是 DataTable_children 的角色 id）
      → `GetSysroom_objectByKey(1001)` 查不到 → nil.type → 崩潰。

      正解：推 `DataTable_room_object` 裡真實存在的 id（機器 = type 1）。
    """
    out = []
    for r in table("room_object"):
        try:
            oid = int(r.get("id"))
        except Exception:
            continue
        if obj_type is not None and int(r.get("type", 0) or 0) != obj_type:
            continue
        out.append(oid)
    return sorted(out)


@functools.lru_cache(maxsize=1)
def room_object_meta():
    """room_object id -> 該列資料（給組 p_building_object_snap 用）。"""
    out = {}
    for r in table("room_object"):
        try:
            out[int(r.get("id"))] = r
        except Exception:
            continue
    return out


@functools.lru_cache(maxsize=1)
def room_default_objects():
    """房型 sys_id -> 該房型預設物件清單 [(obj_id, lvl, pos), ...]。

    來源 `DataTable_room.object_list`，格式 `[[物件id, 等級, [x,y,z]], ...]`。
    給 `31_1 building_info_s2c` 的 `room_list[].object_list` 用。

    ★ 2026-10-10：先前 `_handle_31_1` 沒填這個欄位 → 房間裡空無一物。
    """
    out = {}
    for r in table("room"):
        try:
            rid = int(r.get("id"))
        except Exception:
            continue
        items = []
        for it in (r.get("object_list") or []):
            if isinstance(it, list) and len(it) >= 2:
                try:
                    items.append((int(it[0]), int(it[1]), it[2] if len(it) > 2 else [0, 0, 0]))
                except Exception:
                    continue
        # 同一房型取「物件最多」的那個等級
        prev = out.get(rid)
        if prev is None or len(items) > len(prev[1]):
            out[rid] = (int(r.get("lvl", 1)), items)
    return out


def build_maxed_child(cid, p_children_cls):
    """建立「滿級、滿星、全皮膚」的 p_children 訊息。"""
    star = star_by_child().get(cid, 5)
    m = p_children_cls()
    m.id = cid
    # ★★ 2026-10-11：`type` 的取值（本專案最曲折的一處，完整證據鏈見下）
    #
    # 【消費方一】適格體卡列表 —— 要求 type == 1
    #   `CardModel.GetCardBagDic(cardList, type)`（proto 0.21）L23-40：
    #       for _, card in pairs(cardList) do
    #           if card.type == type then table.insert(out, card) end
    #       end
    #   適格體界面呼叫 `GetCardBagDic(CardTypeIndex.Common)` ⇒ 只收 `type == 1` 的卡。
    #   另外 `CardModel.UpdateCardInfo`（proto 0.9）L46-53 用
    #       `card.isHadRedPoint = (card.type == CardTypeIndex.Common)`
    #
    # 【消費方二】助理界面 —— 要求 hero.cardType == 7
    #   `HeroModel.UpdateHeroInfo`（proto 0.3）L101-108：
    #       card = CardModel:GetCardInfoById(hero.children_id)
    #       hero.cardType = card and card.type or nil        ← card.type 即本欄位
    #   `HeroModel.GetHeroInfoBySysId(sysId, type, cardType)`（proto 0.7）三條件全匹配，
    #       cardType 預設 = `CardDefine.CardTypeIndex.Hero` = **7**
    #   `HeroModel.GetDefaultHeroCardInfo`（proto 0.14）：
    #       hero = GetHeroInfoBySysId(DefaultHeroSysId)
    #       return CardModel:GetCardInfoById(hero.children_id)   -- hero=nil ⇒ 崩
    #
    # 【CardTypeIndex 完整值】（由 CardDefine 的 `SETFIELD 1 <常量索引> K[<值>]` 序列
    #   + int 常量表雙重驗證；注意第一行 Common 極易漏讀）：
    #       Common=1  Secret=2  Assist=3  Teach=4  Explore=5
    #       WarFight=6  Hero=7  HeroTeach=8  PVP=9
    #
    # 【解法】兩者衝突（同一個 `type` 欄位、相反要求），故**只讓預設英雄那一張卡**取 7：
    #   `DataTable_config['init_hero'].value == 1001`
    #   `CardModel.GetCardInfoById(id)` 按 **`card.id`** 查找（proto 0.46）
    #   ⇒ 只要 `id == 1001` 的卡 type=7，其餘 105 張維持 type=1：
    #       * 助理：`GetCardInfoById(hero.children_id=1001).type == 7` ⇒ 找到 hero ⇒ 不崩
    #       * 適格體：其餘 Common 卡仍在 ⇒ 列表非空
    #   （伺服器 `35_1` 送 `children_id = init_hero`，與此處的 1001 一致。）
    #
    # 【歷史教訓】曾把**全部** 106 張卡改成 7 ⇒ 助理恢復但適格體清單變空
    #   （「暫無適格體」）；改回全 1 ⇒ 適格體恢復但助理白屏。
    #   註：`DataTable_children` 沒有 `type` 欄位，此值純由伺服器決定。
    # 🚫 **紅線：`type` 必須維持 `7 if cid == init_hero_sys_id() else 1`。**
    #
    #   2026-10-12 實驗 5（全部改 `1`）的完整結果 —— **證實兩個消費方互斥**：
    #     | `type` | 適格體界面 | 助理設定界面 |
    #     |---|---|---|
    #     | `7` | ❌ 厄莉希消失 | ✅ 不白屏（但大圖顯示厄莉希） |
    #     | `1` | ✅ 厄莉希出現 | ❌ **白屏** |
    #   ⇒ **無法同時滿足**，這是客戶端兩個界面對同一張卡的 `type` 要求衝突
    #     （`GetCardBagDic(cardList, 1)` 要 Common；`GetHeroInfoBySysId` 要 Hero=7）。
    #   ⇒ 現行取捨：**保助理不白屏**（`type=7` 僅給 `init_hero`）。
    #     代價：厄莉希不出現在適格體列表（但仍持有、可用於戰鬥）。
    #
    # 【歷史教訓】曾把**全部** 106 張卡改成 7 ⇒ 助理恢復但適格體清單變空
    #   （「暫無適格體」）；改回全 1 ⇒ 適格體恢復但助理白屏。
    #   註：`DataTable_children` 沒有 `type` 欄位，此值純由伺服器決定。
    m.type = 7 if cid == init_hero_sys_id() else 1
    m.sys_id = cid
    m.exp = 0
    m.lvl = child_level(cid)
    m.sync_times = 0
    # awake_times 於下方依 `children_awake` 設為該角色真實上限（見 L629 註解）
    m.get_time = 0
    # ★ 2026-10-11：好感度「自洽」修法（依使用者指正：lv5 就是上限，不是畸形）
    #   favor_lvl = 該角色的最高好感度等級（正確值為 5）
    #   favor     = 該等級的 range_max（滿值），使客戶端算出 100%
    #   兩者配對後不再出現 `-1252000/0` 或 `0/0`。
    m.favor_lvl = max_favor_lvl_by_child().get(cid, 1) or 1
    m.favor = favor_value_by_child().get(cid, 0)
    m.fight_skill = 1
    m.skill_lvl = max_skill_lvl_by_child().get(cid, 1) or 1
    skins = skin_by_child().get(cid, [])
    m.use_skin = skins[0] if skins else 0
    for s in skins:
        m.skin_list.append(s)
    m.dispatch_id = 0
    m.star = star
    m.gain_times = 1
    m.power = 0
    m.auth_equip_id = 0
    m.is_new = 0
    # ★ 2026-10-11：修「所有角色最後兩條語音永遠上鎖」。
    #   客戶端 `DocumentModel.GetDocumentVoiceInfo`（proto 0.10）的鎖定判定（逐條讀出）：
    #     limit 類型 5 : if card.fetter_break == 0            then lock  （"觸摸-交談"）
    #     limit 類型 6 : if card.awake_times < need(1)        then lock  （"觸摸-突破1" 312 條）
    #     limit 類型 7 : if card.awake_times < need(2)        then lock  （"突破-1"     2 條）
    #   原本 `awake_times = 0`、`fetter_break = 0` ⇒ 兩類突破語音（共 314 條）永遠鎖定。
    #   修法：awake_times 取該角色在 `children_awake` 的真實上限（實測 106 個角色皆為 4），
    #        fetter_break 設 1（非 0 即解鎖類型 5）。
    m.awake_times = max_awake_times_by_child().get(cid, 0)
    m.fetter_break = 1
    m.patrol_id = 0
    return m


# ======================================================================
# 玩家自身（p_role_info）
# ======================================================================
def fill_role_info(info):
    """填入 p_role_info。等級／上限全部來自 DataTable_lvl。"""
    lv = max_player_level()
    info.role_id = ROLE_ID
    info.name = ROLE_NAME
    info.name_num = 0
    info.level = lv
    info.sex = 1                       # PlayerDefine.SEX_MALE
    info.create_time = 0
    info.head_id = 0
    info.frame_id = 0
    info.signature = ""
    info.children_num = len(all_children())
    info.dup_id = 0
    info.assist_sys_id = 0
    info.assist_skin_id = 0
    return info


def player_resources():
    """主界面要顯示的資源（屬性 id -> 值）。

    值取自配置表的「上限」概念，避免出現 0 造成 UI 顯示異常。
    回傳 [(attr_id, value), ...]
    """
    ids = attr_id_by_name()
    lv = max_player_level()

    out = []

    def put(name, value):
        aid = ids.get(name)
        if aid is not None:
            out.append((aid, int(value)))

    put("lvl", lv)
    put("exp", 0)
    put("vip", max_vip())
    put("vipExp", max_vip_exp())
    put("vipFullExp", max_vip_exp())

    # 貨幣：給足以支撐滿級帳號的數量（0 會讓商店／背包／紅點邏輯異常）
    put("money", 99_999_999)
    put("bindMoney", 99_999_999)
    put("allMoney", 199_999_998)
    put("dollar", 999_999)
    put("skillExp", 99_999_999)
    put("friendPoint", 9_999)
    put("activityCoin", 9_999)
    put("warOrderCoin", 9_999)
    put("creditPoint", 9_999)
    put("secretCoin", 9_999)
    put("pvp_coin", 9_999)
    put("recharge_coin", 0)

    put("roleId", ROLE_ID)
    put("sex", 1)
    put("identity", 0)                 # PlayerDefine.IDENTITY_NORMAL
    put("nameNum", 0)
    # ★★ 2026-10-22 關鍵修復：屬性 **619 `slots_num` 是【編隊隊員槽位數】**，
    #   不是法術槽位！
    #   證據鏈：
    #     1) `x.Game.PlayerDefine` 屬性映射表（反匯編）：`LOADI 5 619` +
    #        `LOADK 7 "slots_num"` ⇒ 屬性 619 名為 `slots_num`。
    #     2) `TeamMainView` 的「確定」按鈕處理器：
    #            for i = 1, Player.slots_num do ... end
    #            TeamControl:Send_15_2(...)
    #        ⇒ `Player.slots_num` 就是編隊隊員槽位數。
    #     3) `DataTable_config.team_slots` 實測：
    #            [[1,0,1],[1,0,2],[1,0,3],[1,20105,4],
    #             [1,20101,5],[1,20002,6],[1,20003,7],[1,20008,8]]
    #        ⇒ 槽位 1~3 免費、4~8 需通關對應副本 ⇒ **共 8 個**。
    #   先前錯用 `spell_slots(lv)`（`DataTable_lvl.spell_slots`）⇒ 值 = 3
    #   ⇒ 編隊只有 3 個槽位可用、4~8 顯示 `LOCKED`（與使用者截圖完全一致）。
    put("slots_num", team_slots_num())
    # 注意：**不要**在這裡塞 dynamicBg（屬性 624）。
    # 曾試過 put("dynamicBg", 1)，結果主界面變全黑（screencap 5896 bytes）。
    # 原因未完全確認（CardModel.playingDynamicBgId / 影片資源可能沒載入），
    # 撤銷後恢復成「白色但可操作」。要再嘗試必須先查清 CardModel 的用法。
    return out


@functools.lru_cache(maxsize=1)
def max_vip():
    """VIP 上限（DataTable_vip 的最大 id）。"""
    return max((int(r.get("id", 0)) for r in table("vip")), default=0)


# ======================================================================
# 頭像 / 頭像框（DataTable_headshots）
# ======================================================================
# ★ 2026-10-21 新增。供 `41_1`（當前頭像）與 `41_5`（全部頭像清單）使用。
#
# `DataTable_headshots`（實測 **220 條**）欄位：id / name / type / attribute /
#   head_show / sprite_name / effect_number / desc / arg / arg2 …
#
# **關鍵欄位 `attribute`（實測分佈）**：
#     `attribute=1` ⇒ **頭像**（204 條）
#     `attribute=2` ⇒ **頭像框**（16 條）
#
# **`type` 分佈**：{1:2, 2:82, 3:81, 4:17, 5:38}（子類型，本專案不細分）
# **`head_show`**：{1:192, 2:28}（顯示方式，本專案不細分）
#
# 客戶端消費（`HeadIconModel`，反匯編逐條讀出）：
#   proto 0.1 `InitMainViewInfo`：`usingItemId[Icon] = msg.id`、`[Frame] = msg.frame_id`
#   proto 0.3 `ParseData`：`AddList2Dict(msg.list, itemList[Icon])` 等四個清單


def _headshot_ids_by_attribute(attr):
    out = []
    for r in table("headshots"):
        if str(r.get("attribute")) != str(attr):
            continue
        try:
            out.append(int(r.get("id")))
        except Exception:
            continue
    return sorted(set(out))


@functools.lru_cache(maxsize=1)
def all_headshot_ids():
    """回傳 `(全部頭像 id 昇冪, 全部頭像框 id 昇冪)`。

    實測：頭像 **204** 個（`attribute=1`）、頭像框 **16** 個（`attribute=2`）。
    本專案為滿進度帳號 ⇒ `41_5` 直接把這兩個清單原樣送出（並同時標記為已獲得）。
    """
    return (_headshot_ids_by_attribute(1), _headshot_ids_by_attribute(2))


@functools.lru_cache(maxsize=1)
def default_headshot_ids():
    """回傳 `(預設頭像 id, 預設頭像框 id)`。

    規則：各取該類別中 **`head_show == "1"` 且 id 最小** 的一筆。
    實測結果：
        頭像   → `10101` = 「瞳」            ← 本專案主角，正好合適
        頭像框 → `10012` = 「基礎頭像框」    ← 初始贈送款
    若配置表異常，則退回各類別的 id 最小值。
    """
    out = []
    for attr in (1, 2):
        best = None
        for r in table("headshots"):
            if str(r.get("attribute")) != str(attr):
                continue
            try:
                rid = int(r.get("id"))
            except Exception:
                continue
            if str(r.get("head_show")) == "1":
                if best is None or rid < best:
                    best = rid
        if best is None:
            ids = _headshot_ids_by_attribute(attr)
            best = ids[0] if ids else 0
        out.append(best)
    return (out[0], out[1])


# ======================================================================
# 空島基建核心 / 房間加成（DataTable_core / core_lvl / room_bonus）
# ======================================================================
# ★ 2026-10-21 新增。供 `31_32`（building_core_list）與 `31_40`（building_notify_bonus）。
#
# **`DataTable_core`（實測 6 條）**：
#     _key=10001 中樞系統 / 10002 貿易系統 / 10003 調度系統
#     _key=10004 通訊系統 / 10005 榮譽系統 / 10006 合成系統
# **`DataTable_core_lvl`（36 條）**：`{id, level, ...}` ⇒ 每個 core 的最大等級
#     實測最大值：10001→1、10002→15、10003→1、10004→15、10005→1、10006→1
#     （另有 20001/20002 各 1 級，不在 DataTable_core 內，屬其他用途，此處不送）
#
# **客戶端消費**（`BuildModel` proto 24.83 = On_31_32）：
#     for _, v in pairs(msg.core_list) do
#         if not allCoreInfo[v.id] then allCoreInfo[v.id] = CoreInfo:New() end
#         allCoreInfo[v.id]:InitInfo(v)      -- InitInfo 複製所有標量欄位
#     end
#   而 `GetCoreInfoBySysId(sysId)`（BuildModel L4218-4224）：
#     for _, v in pairs(allCoreInfo) do
#         if v.sys_id == sysId then return v end
#     end
# **⇒ `id` = 字典鍵（唯一即可）；`sys_id` = `DataTable_core._key`（配置 id）。**


# ----------------------------------------------------------------------
# 當前頭像 / 頭像框（可變狀態）
# ----------------------------------------------------------------------
# ★ 2026-10-21 新增。修「頭像框更改後不生效」。
#
# **根因**（`HeadIconControl` 反匯編，逐條讀出）：
#     `On_41_3`（處理 `headshots_change_frame_s2c`）的實作是
#         HeadIconModel:InitMainViewInfo(msg)      -- ★ 把「換框回應」當完整資訊解析
#     而 `InitMainViewInfo`（`HeadIconModel` proto 0.1）讀的是
#         msg.entry / msg.head / msg.id / msg.frame_id
#     **但 `headshots_change_frame_s2c` 的 proto 只有 `id` 一個欄位**
#     ⇒ `msg.frame_id` = nil ⇒ `usingItemId[Frame] = nil` ⇒ **框不生效**。
#
# **修法**：伺服器保存使用者選擇，並在換頭像/換框後**主動重推 `41_1`**
#   （`headshots_info_s2c` 含完整四欄位）⇒ 客戶端 `InitMainViewInfo` 才會拿到 frame_id。
_CURRENT_HEADSHOT = {"icon": None, "frame": None}


def set_current_headshot(kind, hid):
    """設定當前頭像（`kind="icon"`）或頭像框（`kind="frame"`）。

    由 `_handle_41_2`（換頭像）與 `_handle_41_3`（換框）呼叫。
    """
    global _CURRENT_HEADSHOT
    try:
        hid = int(hid)
    except Exception:
        return _CURRENT_HEADSHOT.get(kind)
    if kind in ("icon", "frame"):
        _CURRENT_HEADSHOT[kind] = hid
    return _CURRENT_HEADSHOT.get(kind)


def current_headshot_ids():
    """回傳 `(當前頭像 id, 當前頭像框 id)`。

    未設定過則退回 `default_headshot_ids()`（瞳的頭像 + 基礎頭像框）。
    """
    di, df = default_headshot_ids()
    return (_CURRENT_HEADSHOT.get("icon") or di,
            _CURRENT_HEADSHOT.get("frame") or df)


@functools.lru_cache(maxsize=1)
def building_core_list():
    """回傳 `[(sys_id, 最大等級), ...]`（來自 `DataTable_core` + `DataTable_core_lvl`）。

    本專案為滿進度帳號 ⇒ 每個 core 都取**配置表最大等級**。
    實測結果：`[(10001,1), (10002,15), (10003,1), (10004,15), (10005,1), (10006,1)]`
    """
    max_lvl = {}
    for r in table("core_lvl"):
        try:
            cid = int(r.get("id"))
            lv = int(r.get("level"))
        except Exception:
            continue
        if lv > max_lvl.get(cid, 0):
            max_lvl[cid] = lv
    out = []
    for r in table("core"):
        try:
            cid = int(r.get("_key"))
        except Exception:
            continue
        out.append((cid, max_lvl.get(cid, 1)))
    return out


@functools.lru_cache(maxsize=1)
def building_bonus_ids():
    """回傳 `DataTable_room_bonus` 的全部 `_key`（昇冪）。

    實測 **13** 條（`_key` 1..13）。
    客戶端 `BonusMgr` proto 0.8：
        for _, v in pairs(buildingBonusInfo) do
            cfg = DataBase:GetSysroom_bonusByKey(v.sys_id)   -- ★ 用 sys_id 查配置
            ... type / can_draw / roleList ...
        end
    ⇒ `p_building_bonus.sys_id` = `room_bonus._key`。
    """
    out = []
    for r in table("room_bonus"):
        try:
            out.append(int(r.get("_key")))
        except Exception:
            continue
    return sorted(set(out))


# ----------------------------------------------------------------------
# 家具 / 機器（DataTable_room_furniture / room_machine_lvl）
# ----------------------------------------------------------------------
# ★ 2026-10-22 新增。修「宅邸沒有解鎖的家具」。
#
# **為什麼需要**：`31_12 building_notify_machine_list` 與
#   `31_13 building_notify_furniture_list` 都是 **notify 型（伺服器主動推）**，
#   而先前服務端從未推送 ⇒ 客戶端 `BuildModel.allFurnitureInfo` /
#   `allMachineInfo` 一直是空的 ⇒ 家具背包/宅邸顯示「沒有解鎖的家具」。
#
# 配置表（實測）：
#   `DataTable_room_furniture`（**81 條**）：`id` = 家具配置 id（100101…）
#   `DataTable_room_machine_lvl`（**12 條**）：`id` = 機器配置 id
#       實測 id：200101~200109、200201、200205、200208
#   客戶端查配置用 `GetSysroom_furnitureByKey(sys_id)` ⇒
#   **`p_building_furniture.sys_id` / `p_building_machine.sys_id` = 配置 id**。
#
# `p_building_furniture { id, dust_lvl, atoms, dust_time, sys_id }`
#   ⇒ 滿進度帳號：全部 81 件家具都「已獲得」；
#     `dust_lvl=0 / dust_time=0`（不髒污）、`atoms=0`。
# `p_building_machine { id, used_elec, output, output_max, output_speed,
#                       default_speed, cost_power, start_time, sys_id }`
#   ⇒ 全部 12 台機器；數值取配置表（`output_limit` / `cost_power`），
#     未運行狀態（`start_time=0`、`output=0`、`used_elec=0`）。


@functools.lru_cache(maxsize=1)
@functools.lru_cache(maxsize=1)
@functools.lru_cache(maxsize=1)
@functools.lru_cache(maxsize=1)
def team_slot_unlocks():
    """回傳 `[(槽位號, 所需副本 id), ...]`（來自 `DataTable_config.team_slots`）。

    ★ 2026-10-22 新增。修「編隊槽位鎖死 / 無法變更角色保存」。

    **`DataTable_config['team_slots']` 實測原值**：
        `[[1, 0, 1], [1, 0, 2], [1, 0, 3], [1, 20105, 4],
          [1, 20101, 5], [1, 20002, 6], [1, 20003, 7], [1, 20008, 8]]`
    格式 = `[type, 所需副本 id, 槽位號]`：
        * 槽位 1~3：所需副本 = 0 ⇒ **默認免費**
        * 槽位 4：需通關副本 **20105**（`DataTable_dungeon` name=「清場」number=「IN-1」）
        * 槽位 5：**20101**（「異能」IN-2）
        * 槽位 6：**20002**（「輕行」IN-3）
        * 槽位 7：**20003**（「戰術」IN-4）
        * 槽位 8：**20008**（「解離」IN-9）
    """
    out = []
    for r in table("config"):
        if str(r.get("key")) != "team_slots":
            continue
        raw = str(r.get("value") or "")
        import json as _json
        try:
            arr = _json.loads(raw)
        except Exception:
            return out
        for item in arr:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            try:
                out.append((int(item[2]), int(item[1])))
            except Exception:
                continue
        break
    out.sort()
    return out


@functools.lru_cache(maxsize=1)
def team_slots_num():
    """已解鎖的編隊槽位數量（**屬性 id 619 `slots_num`**）。

    ★ 2026-10-22 新增。**這是「編隊無法變更角色保存」的根因**。

    【客戶端證據】（`x.Game.PlayerDefine` 屬性映射表反匯編）：
        LOADI 5 619              -- ★ 屬性 id = 619
        LOADK 7 "slots_num"      -- ★ 欄位名
    ⇒ `Player.slots_num` 來自 **`2_2 role_info_s2c` 的 `kv_list`（k=619）**。
    而 `TeamMainView` 的「確定」按鈕：
        for i = 1, Player.slots_num do ... end
        TeamControl:Send_15_2(...)
    ⇒ **`slots_num = 0`（我們從未送 619）⇒ 迴圈不執行 ⇒ 點「確定」無反應。**

    計算方式：`team_slots` 中「所需副本 = 0」的槽位一律解鎖；其餘槽位要求
    對應副本已通關。本專案 `17_1` 已把所有副本標記為滿星通關（且補了 `task`
    ⇒ `dungeonInfo[dup_id] = 3`）⇒ **全部 8 個槽位都算已解鎖**。
    這裡不依賴 17_1 的實際結果，而是按「滿進度帳號」語意直接全開
    （`17_1` 的資料源 `DataTable_dungeon` 已全送）。
    """
    slots = team_slot_unlocks()
    if not slots:
        return 8
    passed = set()
    for r in table("dungeon"):
        try:
            passed.add(int(r.get("id")))
        except Exception:
            continue
    n = 0
    for slot_idx, need_dup in slots:
        if need_dup == 0 or need_dup in passed:
            n = slot_idx if slot_idx > n else n
    return n if n else len(slots)


def hero_default_id():
    """默認英雄 id（`DataTable_hero.id`，實測 **1001**）。

    ★ 2026-10-22 新增。供 `15_4` 的 `p_hero_index.hero_id` 使用。
    """
    ids = []
    for r in table("hero"):
        try:
            ids.append(int(r.get("id")))
        except Exception:
            pass
    return min(ids) if ids else 1001


@functools.lru_cache(maxsize=1)
def hero_default_form():
    """默認英雄形態（`DataTable_hero.form`，`id=1001` 中 `order` 最小的 form）。

    實測 `DataTable_hero` 有 `id=1001` 的 form 1..8，
    其中 `form=1` = 「瞳-強襲形態」（`_key='1001|=|1'`）。
    """
    best = None
    for r in table("hero"):
        try:
            if int(r.get("id")) != hero_default_id():
                continue
            form = int(r.get("form"))
            order = int(r.get("order", 999) or 999)
        except Exception:
            continue
        if best is None or order < best[0]:
            best = (order, form)
    return best[1] if best else 1


def team_default_children(n=4):
    """編隊預設角色 id 清單（默認 **4 個**；可傳 n 指定數量）。

    `_handle_15_4` 目前傳 8（與屬性 619 `slots_num = 8` 對齊）。

    ★ 2026-10-22 新增。

    **為什麼不能用瞳（`100000~100007`）**：它們的 `DataTable_children.is_hero == 1`
    ⇒ 屬「英雄」，客戶端應放在 `p_children_team.hero_list`（`p_hero_index`）而非
    `children_list`。塞進 `children_list` 可能被拒絕。

    **選法**：取 `formal_children()` 中 `is_hero != 1` 的前 4 個（昇冪），
    本專案實測 = `[1001(厄莉希), 1002(牙人), 1003(冰見優奈), 1004(哈提)]`。
    （`1001` 厄莉希的 `is_hero` 為 0，可正常放在編隊裡。）
    """
    out = []
    hero = set()
    for r in table("children"):
        if str(r.get("is_hero")) in ("1", "True", "true"):
            try:
                hero.add(int(r.get("id") or r.get("_key")))
            except Exception:
                pass
    for cid in formal_children():
        if cid in hero:
            continue
        out.append(cid)
        if len(out) >= int(n):
            break
    return out


def all_furniture_ids():
    """回傳 `DataTable_room_furniture` 的全部家具 id（昇冪）。實測 **81** 條。"""
    out = []
    for r in table("room_furniture"):
        try:
            out.append(int(r.get("id")))
        except Exception:
            continue
    return sorted(set(out))


@functools.lru_cache(maxsize=1)
def room_machines():
    """回傳 `[(機器 id, output_limit, cost_power), ...]`（來自 `room_machine_lvl`）。

    同一機器 id 可能有多個 `level` 列；取**最大 level** 那一列作為滿級數值。
    實測 **12** 個不同 id：200101~200109、200201、200205、200208。
    """
    best = {}
    for r in table("room_machine_lvl"):
        try:
            mid = int(r.get("id"))
            lv = int(r.get("level", 0) or 0)
        except Exception:
            continue
        cur = best.get(mid)
        if cur is None or lv > cur[0]:
            best[mid] = (lv,
                         int(r.get("output_limit", 0) or 0),
                         int(r.get("cost_power", 0) or 0))
    return [(mid, v[1], v[2]) for mid, v in sorted(best.items())]


@functools.lru_cache(maxsize=1)
def max_vip_exp():
    return max((int(r.get("exp", 0)) for r in table("vip")), default=0)


# ======================================================================
# 🚫 紅線：**禁止**推送 `dynamicBg`（屬性 624）
# ======================================================================
# 本節僅為警告與證據記錄 —— **此處刻意不提供任何推送函式**。
#
# 客戶端確實需要 `dynamicBg` 才會切換「映像（動態背景）」：
#   `PlayerControl` proto 0.21（處理 `2_2 role_info_s2c`）逐條讀出：
#       for _, v in ipairs(msg.ks_list) do
#           Player[v.k] = v.v                       -- 以【字串鍵】寫入
#       end
#       if v["dynamicBg"] then                      -- ★ 偵測到才觸發
#           EventManager:TriggerEvent(PlayerEvent.DYNAMIC_BG_ATTR_CHANGE)
#       end
#   `MainFrameView.UpdateDynamicBgInfo`（proto 21）：
#       staticBg:SetActive(Player.dynamicBg <= 0)   -- 0 ⇒ 顯示靜態背景
#       dynamicBg:SetActive(Player.dynamicBg > 0)   -- >0 ⇒ 播放影片
#       CardModel.playingDynamicBgId = Player.dynamicBg
#
# ⚠⚠ 但**兩次推送嘗試都破壞了正常功能**：
#     1. 前人 `put("dynamicBg", 1)`            ⇒ **主界面全黑**
#     2. 本輪 `dynamicBg='2'` 進 `ks_list`      ⇒ **登入後主界面卡死**
#   （資源本身存在：`dynamicBg1_HD.mp4` 14.5MB、`dynamicBg2_HD.mp4` 10.4MB，
#     故非缺資源問題；真因未明，可能與 `CardModel.playingDynamicBgId` 的
#     影片解碼路徑／模擬器相容性有關。）
#
# ⇒ **現狀：`player_str_resources()` 只回 `name`，永不推送 `dynamicBg`。**
#   「映像」功能因此為**部分可用**：使用者能看到並選擇兩張映像，
#   但儲存後主界面不切換（**不破壞遊戲**，優於推送後的卡死）。
#   詳見 `docs\知識庫_合併版.md` §0.5.6 與 `解包後資源\README_總索引.md`。


def player_str_resources():
    """字串型屬性（role_info_s2c 的 ks_list）。"""
    ids = attr_id_by_name()
    out = []
    for name, value in (("name", ROLE_NAME),):
        aid = ids.get(name)
        if aid is not None:
            out.append((aid, value))
    # ⚠⚠ 2026-10-11：**不要**在 `ks_list` 塞 `dynamicBg`（屬性 624）。
    #   曾推送 `dynamicBg='2'`，結果使用者**登入後主界面卡死**。
    #   （前人亦曾推 `dynamicBg=1` 導致主界面全黑 —— 見下方舊註解。）
    #   故此處維持「永不推送」，`player_str_resources()` 只回 `name`。
    #   詳見交接文件 §0.5.5。
    return out


# ======================================================================
# 活動（DataTable_activity_main / DataTable_activity）
# ======================================================================
@functools.lru_cache(maxsize=1)
def activity_types():
    out = []
    for r in table("activity_main"):
        try:
            out.append(int(r.get("id") or r["_key"]))
        except Exception:
            pass
    return out


def activity_briefs_for_type(type_id, limit=3):
    """該 type 底下的活動簡表 [(activity_id, end_time, red_point), ...]。

    客戶端 `ActivityModel.UpdateActivity` 會對巢狀 activity_list 做 ipairs，
    因此每個送出的元素至少要有 1 筆，否則 nil 迭代會拋例外。
    """
    out = []
    now = int(time.time())
    for r in table("activity"):
        try:
            aid = int(r.get("uni_act_id") or r["_key"])
            if int(r.get("type", -1)) != int(type_id):
                continue
        except Exception:
            continue
        out.append((aid, now + 86400 * 30, 0))
        if len(out) >= limit:
            break
    return out


# ======================================================================
# 功能開放（DataTable_open_func）
# ======================================================================
@functools.lru_cache(maxsize=1)
def all_func_ids():
    """全部功能 id（DataTable_open_func 的 id）。"""
    out = []
    for r in table("open_func"):
        try:
            out.append(int(r.get("id") or r["_key"]))
        except Exception:
            pass
    return sorted(set(out))


@functools.lru_cache(maxsize=1)
def func_open_conditions():
    """功能 id -> open_limit（開啟條件）。

    open_limit 每項形如 [condType, arg]（見 ScenarioDefine.CondType）：
      1 = enterDup（通關副本 arg）… 等
    我們把「滿級全通關」帳號視為條件全滿足，因此回傳全部 id；
    但保留此函式以便之後要精細控制個別功能時使用。
    """
    out = {}
    for r in table("open_func"):
        try:
            out[int(r.get("id") or r["_key"])] = r.get("open_limit") or []
        except Exception:
            pass
    return out


def unlocked_func_ids():
    """已開放的功能 id 清單（滿級全解鎖帳號 → 全部）。

    客戶端 x.Module.FunOpen.Control.FunOpenControl 用它決定
    主界面按鈕是「可點」還是「暫未連線」；回空清單會讓所有按鈕變灰。
    """
    return all_func_ids()


# ======================================================================
# 通用「真實 id 提供器」
# ======================================================================
# 為什麼需要：通用回應器若憑空填 id（例如 item_id=1），客戶端會拿它去
# DataBase 查表 → 查不到 → nil → 在 Update 迴圈拋例外 → 主界面渲染中斷。
# （實際踩過：item_info_s2c 填 item_id=1 導致 BagModel.InitBagInfo 崩潰）
# 所以任何 *_id 欄位都應該填「配置表裡真的存在的 id」。
_ID_SOURCES = {
    "item": "item", "item_id": "item",
    "children": "children", "children_id": "children", "child_id": "children",
    "sys_id": "children", "hero": "hero", "hero_id": "hero",
    "equip": "equip", "equip_id": "equip",
    "task": "task", "task_id": "task",
    "badge": "badge", "badge_id": "badge",
    "activity": "activity", "act_id": "activity", "activity_id": "activity",
    "dup": "dup", "dup_id": "dup",
    "skill": "children_skill", "skill_id": "children_skill",
    "head": "head", "head_id": "head",
    "sign": "sign",
    "pool": "recruit_pool", "pool_id": "recruit_pool", "sys_pool_id": "lottery",
    "shop": "shop_item", "shop_id": "shop_item",
    "dispatch": "dispatch",
    "patrol": "patrol_path_list", "patrol_id": "patrol_path_list",
    "group": "children_group", "group_id": "children_group",
}


@functools.lru_cache(maxsize=64)
def _ids_of(table_name):
    """某配置表所有合法 id（升序）。"""
    out = []
    for r in table(table_name):
        try:
            out.append(int(r.get("id") or r["_key"]))
        except Exception:
            # 複合鍵（如 "3|=|100012"）取第一段
            try:
                out.append(int(str(r["_key"]).split("|")[0]))
            except Exception:
                pass
    return sorted(set(out))


def real_id_for(field_name, fallback=1):
    """依欄位名回傳一個「配置表真的存在」的 id。

    找不到對應表時回 fallback（呼叫端可自行決定要不要用）。
    """
    name = (field_name or "").lower()
    # 先精確比對，再退化成「包含」
    tname = _ID_SOURCES.get(name)
    if tname is None:
        for k, v in _ID_SOURCES.items():
            if k in name:
                tname = v
                break
    if tname is None:
        return fallback
    ids = _ids_of(tname)
    return ids[0] if ids else fallback


# ======================================================================
# 道具（DataTable_item）
# ======================================================================
@functools.lru_cache(maxsize=1)
def item_rows():
    return table("item")


def bag_items(limit=None):
    """回傳背包道具 [(item_id, count), ...]，item_id 取自 DataTable_item。

    為什麼一定要用配置表的合法 id：客戶端收到 `item_info_s2c` 後會呼叫
    `BagModel.InitBagInfo` → `DataBase.GetItemByKey(item_id)` 查表；
    給了不存在的 id 會讓查表拿到 nil → 在 `Update` 迴圈拋例外 →
    **整個主界面渲染中斷**（實際踩過）。
    """
    out = []
    for r in item_rows():
        try:
            iid = int(r.get("id") or r["_key"])
        except Exception:
            continue
        out.append((iid, 9999))
        if limit is not None and len(out) >= limit:
            break
    return out

@functools.lru_cache(maxsize=1)
def lottery_pools():
    """回傳 [(sys_pool_id, loop_cnt, stime, donate_times), ...]，取自 DataTable_lottery。

    客戶端 x.Module.DailyLuckyDraw.DailyLuckyDrawModel.lua:109  CallBackDrawInfo
        local pool = A0_3.new_pool
        DataBase.GetSyslotteryByKey(pool.sys_pool_id)   ← sys_pool_id 必須存在
    空清單會讓它拿到 nil → 在 Update 迴圈裡拋
    `bad argument #1 to 'for iterator' (table expected, got nil)` →
    整個 Update 中斷、**主界面渲染異常**（實際踩過）。
    """
    out = []
    for r in table("lottery"):
        try:
            pid = int(r.get("id") or r["_key"])
        except Exception:
            continue
        out.append((
            pid,
            int(r.get("loop_cnt", 999)),
            int(r.get("donate_stime", 0)),
            int(r.get("donate_award", 0)),
        ))
    return out


# ======================================================================
# 離線資料補齊：派遣 / 任務 / 簽到 / 交易訂單
# ======================================================================
# 為什麼要這一段：通用填充器會「亂補元素 + 填 id=1」，
# 導致客戶端 `DataBase.GetXxxByKey(id)` 查不到 → nil → 崩潰：
#   InitTeamList  / InitTaskInfo / InitOrderInfo / 簽到「不存在此签到id」
# 這些函式一律要用配置表裡真的存在的 id。

def dispatch_ids(limit=3):
    """派遣任務 id（DataTable_dispatch）。"""
    out = []
    for r in table("dispatch"):
        try:
            out.append(int(r.get("id") or r["_key"]))
        except Exception:
            pass
        if len(out) >= limit:
            break
    return out


def first_task_id():
    """第一個「無前置條件」的任務 id（DataTable_task, type=1）。

    已驗證：id=110001（desc「通關0-1」），可直接當進行中任務。
    """
    for r in table("task"):
        try:
            if int(r.get("type", 0)) == 1 and not r.get("pre_task"):
                return int(r.get("id") or r["_key"])
        except Exception:
            continue
    rows = table("task")
    return int(rows[0].get("id") or rows[0]["_key"]) if rows else 110001


def sign_ids(limit=1):
    """簽到 id（DataTable_sign）。

    ⚠️ 全部 63 筆的 period 都在 2023 年以前就結束了。
    這裡取 id 最小的幾筆（type=1 的月度簽到），
    客戶端若依 period 判斷「本期」可能仍需容錯，但至少 id 是合法存在的。
    """
    out = []
    for r in table("sign"):
        try:
            out.append(int(r.get("id") or r["_key"]))
        except Exception:
            pass
        if len(out) >= limit:
            break
    return out


def order_id():
    """交易訂單 id（DataTable_order）。"""
    rows = table("order")
    if not rows:
        return None
    try:
        return int(rows[0].get("id") or rows[0]["_key"])
    except Exception:
        return None


def event_ids(limit=3):
    """事件 id（DataTable_event）—— 隊伍系統用。"""
    out = []
    for r in table("event"):
        try:
            out.append(int(r.get("id") or r["_key"]))
        except Exception:
            pass
        if len(out) >= limit:
            break
    return out


# ======================================================================
# 新手教程（DataTable_guide）
# ======================================================================
@functools.lru_cache(maxsize=1)
def guide_range():
    ids = []
    for r in table("guide"):
        try:
            ids.append(int(r.get("_key")))
        except Exception:
            pass
    return (min(ids), max(ids), len(ids)) if ids else (0, 0, 0)


if __name__ == "__main__":
    print("=== 玩家（全部來自 DataTable_lvl）===")
    print("  滿級:", max_player_level())
    print("  vit_max:", vit_max(), " friend_max:", friend_max(),
          " spell_slots:", spell_slots(), " next_exp:", next_level_exp())
    print()
    print("=== 角色 ===")
    print("  總數:", len(all_children()), " 皮膚:", len(all_skins()))
    print("  星級上限:", star_max_lvl())
    print()
    print("=== 活動 ===")
    print("  type 清單:", activity_types())
    for t in activity_types()[:3]:
        print("    type", t, "->", activity_briefs_for_type(t))
    print()
    print("=== 資源（屬性 id -> 值）===")
    print(" ", player_resources())
    print()
    print("=== 新手教程 ===")
    print(" ", guide_range())

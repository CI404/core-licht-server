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
    """角色 id -> 皮膚 id 清單（已用 `valid_skin_ids()` 過濾掉配置表不存在的 id）。"""
    valid = valid_skin_ids()
    out = {}
    for r in children_rows():
        cid = int(r.get("id") or r["_key"])
        out[cid] = [int(x) for x in (r.get("skin_list") or []) if int(x) in valid]
    return out


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


def all_children():
    return sorted(int(r.get("id") or r["_key"]) for r in children_rows())


@functools.lru_cache(maxsize=1)
def formal_children():
    """**已實裝**（`is_informal == 0`）的角色 id 清單。

    ★ 2026-10-10：修正「適格體檔案沒解鎖／好感度無法讀取」。

    症狀（logcat）：
        LuaException: attempt to index a nil value
          ?: in method 'UpdateFavorInfo'        （DocumentView.lua:891）
          ?: in method 'HandleAfterOpenView'
          :? in method 'RefreshCardInfoDetail' → RefreshCardGrid → Open

    崩潰點 `DocumentView.lua:891-930`：
        cfg = DataBase.GetSyschildren_favor_lvlByKey(role_sys_id, favor_lvl)
        ...
        L5_2 = A0_2.friendExp
        L6_2 = L1_2.range_min        -- cfg 是 nil → 崩潰

    根因：`DataTable_children` 有 113 個角色，但
      - `DataTable_children_favor_lvl` 只有 106 個 id
      - `DataTable_children_favor`     只有 106 個 id
      缺的正是 **7 個「瞳」佔位符**：9100001~9100007（全都 is_informal=1）。
      伺服器原本把 113 個全推 → 客戶端打開這些角色的檔案 → 查表回 nil → 崩潰。
      （同時這也是適格體列表出現 14 張重複「瞳」的原因）

    過濾依據（實測驗證）：
      `DataTable_children.is_informal`：0 = 正式（83 個）、1 = 未實裝（30 個）。
      **83 個正式角色全部都有 favor_lvl 資料**，交叉驗證無一遺漏。

    注意：`DataTable_children` 的 `id` 與 `_key` 不一定相同，
    這裡以 `id` 為準（`_key` 可能是複合鍵）。
    """
    out = []
    for r in children_rows():
        try:
            if int(r.get("is_informal", 0) or 0) != 0:
                continue
            out.append(int(r.get("id") or r["_key"]))
        except Exception:
            continue
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
    m.type = 1
    m.sys_id = cid
    m.exp = 0
    m.lvl = child_level(cid)
    m.sync_times = 0
    m.awake_times = 0
    m.get_time = 0
    m.favor_lvl = max_favor_lvl_by_child().get(cid, 1) or 1
    m.favor = 0
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
    m.fetter_break = 0
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
    put("slots_num", spell_slots(lv))
    # 注意：**不要**在這裡塞 dynamicBg（屬性 624）。
    # 曾試過 put("dynamicBg", 1)，結果主界面變全黑（screencap 5896 bytes）。
    # 原因未完全確認（CardModel.playingDynamicBgId / 影片資源可能沒載入），
    # 撤銷後恢復成「白色但可操作」。要再嘗試必須先查清 CardModel 的用法。
    return out


@functools.lru_cache(maxsize=1)
def max_vip():
    """VIP 上限（DataTable_vip 的最大 id）。"""
    return max((int(r.get("id", 0)) for r in table("vip")), default=0)


@functools.lru_cache(maxsize=1)
def max_vip_exp():
    return max((int(r.get("exp", 0)) for r in table("vip")), default=0)


def player_str_resources():
    """字串型屬性（role_info_s2c 的 ks_list）。"""
    ids = attr_id_by_name()
    out = []
    for name, value in (("name", ROLE_NAME),):
        aid = ids.get(name)
        if aid is not None:
            out.append((aid, value))
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

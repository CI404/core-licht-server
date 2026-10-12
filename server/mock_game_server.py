# -*- coding: utf-8 -*-
"""mock_game_server.py : 統一 mock 伺服器（9001）— HTTP 登入服 + 遊戲服 TCP 協定

同一埠同時處理：
  1) HTTP 請求（登入服 API：/exe/login_auth、/client/role_region_list、/client/select_region …）→ JSON
  2) 遊戲服 TCP 協定（protobuf 二進位封包）→ 解析框架 → 回應 1_1 等訊息

關鍵修復（2026-10-10）：
  NetNode.SetServerInfo 讀取的是 server 物件的 **serv_ip / serv_port** 欄位
  （不是 ip/port）。select_region 的 server_key 必須包含這兩個欄位，
  否則 IPSelector 的 baseIp/basePort 為 nil → IPEndPoint..ctor 拋 ArgumentNullException。
"""
import os, sys, json, time, socket, struct, threading, datetime, functools

# ---- 可移植化：路徑與網路設定一律由專案根的 config.py 決定 ----
#      （見 config/server.json；可用環境變數 LICHT_* 覆寫）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as CFG

CFG.ensure_runtime_dirs()

PORT = CFG.LOGIN_PORT
LOG = CFG.LOG_PATH

# 回給客戶端的位址（模擬器 MuMu / QEMU user-mode NAT → 宿主機為 10.0.2.2）
HOST_FOR_CLIENT = CFG.PUBLIC_HOST
HOST_PORT = f"{HOST_FOR_CLIENT}:{PORT}"

# ---------- 全部角色解鎖 / 滿級帳號設定 ----------
# ScenarioDefine.BeginnerStageType.Finished = 29（新手教程已完成，不再播引導）
NOOB_STAGE_FINISHED = 29
ROLE_ID = 10001
ROLE_NAME = "指揮官"
ROLE_LEVEL = 1          # 顯示用；實際玩家等級由 player_data.MAX_ROLE_LEVEL 提供
SERVER_ID = 1

first_bytes = [b""]

_log_lock = threading.Lock()


def log(msg):
    line = f"[{datetime.datetime.now().isoformat()}] {msg}\n"
    with _log_lock:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line)
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except Exception:
        pass


# ---------------- 資料表（二維陣列 → 物件） ----------------
# NetNode.SetServerInfo 需要 serv_ip / serv_port
SERVER_KEY = [
    "id", "server_id", "region_id", "name", "state", "status",
    "serv_ip", "serv_port", "ip", "port", "cp",
    "is_new", "is_hot", "open_time", "recommend", "flag",
    "area", "zone", "type", "sort", "convert_ip_port",
]


def server_row(now):
    vals = {
        "id": SERVER_ID,
        "server_id": SERVER_ID,
        "region_id": SERVER_ID,
        "name": "單機服",
        "state": 1,
        "status": 1,
        "serv_ip": HOST_FOR_CLIENT,
        "serv_port": PORT,
        "ip": HOST_PORT,
        "port": PORT,
        "cp": [HOST_PORT],
        "is_new": 0,
        "is_hot": 1,
        "open_time": now - 86400 * 30,
        "recommend": 1,
        "flag": 0,
        "area": "TW",
        "zone": "TW",
        "type": 1,
        "sort": 1,
        "convert_ip_port": "",
    }
    return [vals[k] for k in SERVER_KEY]


# 角色條目：LoginSubViewFirst 以 role.region_id 作為分組鍵（缺 → table index is nil）
ROLE_KEY = ["id", "name", "level", "sex", "last_login_time", "server_id",
            "region_id", "vip", "job", "head", "head_frame", "create_time"]


def role_row(now):
    vals = {
        "id": ROLE_ID,
        "name": ROLE_NAME,
        "level": ROLE_LEVEL,
        "sex": 1,
        "last_login_time": now,
        "server_id": SERVER_ID,
        "region_id": SERVER_ID,
        "vip": 0,
        "job": 1,
        "head": 0,
        "head_frame": 0,
        "create_time": now - 86400 * 30,
    }
    return [vals[k] for k in ROLE_KEY]


# ---------------- HTTP 部分 ----------------
# 讓 /exe/login_auth 的 time 可固定，方便把 TCP 明文變成「完全已知」
FIXED_LOGIN_TIME = os.environ.get("MOCK_FIXED_TIME")
# 最近一次 login_auth 回傳的 time（遊戲會用它當 login_auth_c2s.time）
LAST_LOGIN_TIME = {"v": None}


def json_response(obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    head = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: keep-alive\r\n\r\n"
    ).encode("utf-8")
    return head + body


def handle_http(path, headers, body):
    now = int(time.time())
    if path.endswith("login_auth"):
        t = int(FIXED_LOGIN_TIME) if FIXED_LOGIN_TIME else now
        LAST_LOGIN_TIME["v"] = t
        payload = {"code": 0, "data": {
            "uname": "player", "uid": "player", "p_key": "0", "token": "offline-local-token",
            "time": t, "time_zone": 8, "ios_auth": 0, "is_white_ip": 1,
            "json_data": "{}", "serv_time": t}}
        log(f"  -> login_auth JSON  time={t}  token=offline-local-token")
    elif path.endswith("role_region_list"):
        payload = {"code": 0, "data": {
            "serv_time": now, "time_zone": 8, "notice": "",
            "region_key": SERVER_KEY, "region_list": [server_row(now)],
            "role_key": ROLE_KEY, "role_list": [role_row(now)]}}
        log("  -> role_region_list JSON")
    elif path.endswith("select_region"):
        payload = {"code": 0, "data": {
            "serv_time": now, "time_zone": 8,
            "server_key": SERVER_KEY, "serv_list": [server_row(now)]}}
        log(f"  -> select_region JSON (serv_ip={HOST_FOR_CLIENT} serv_port={PORT})")
    else:
        payload = {"code": 0, "data": {"serv_time": now, "time_zone": 8}}
        log("  -> generic JSON")
    return json_response(payload)


def http_loop(conn, first):
    buf = first
    conn.settimeout(15)
    while True:
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        lines = head.decode("utf-8", "replace").split("\r\n")
        method, path, _ = (lines[0].split(" ") + ["", ""])[:3]
        headers = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        clen = int(headers.get("content-length") or 0)
        while len(rest) < clen:
            chunk = conn.recv(4096)
            if not chunk:
                return
            rest += chunk
        body = rest[:clen]
        buf = rest[clen:]
        log(f"HTTP {method} {path} len={len(body)}")
        conn.sendall(handle_http(path, headers, body))


# ---------------- 遊戲服 TCP 協定 ----------------
# 線格式（已由 libil2cpp.so 反組譯 + 實測驗證）：
#   C2S: [u16 BE len = 總長-2][u16 BE uniq][u8 sId][u8 mId][XOR body]
#        body XOR key = XorCode._passArr[(uniq + i) & 0xFF]
#   S2C: [u16 BE len = 總長-2][u8 sId][u8 mId][u8 zflag][XOR body]
#        body XOR key = XorCode._passArr[((sId*16 + mId) + i) & 0xFF]；zflag!=0 時 body 為 zlib
#   連線建立時客戶端會先送「裸」2 bytes 01 02（無長度頭、無加密）→ 必須丟棄
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lichter_wire as wire  # noqa: E402
import player_data as PD  # noqa: E402
from google.protobuf import message_factory  # noqa: E402

POOL = wire.load_pool(CFG.PROTO)
MSGMAP = json.load(open(os.path.join(CFG.PROTO, "msgmap.json"), encoding="utf-8"))
C2S_NAMES = MSGMAP["c2s"]
S2C_NAMES = MSGMAP["s2c"]
PKG = MSGMAP["packagename"]
log(f"訊息對照表: c2s {len(C2S_NAMES)} 條 / s2c {len(S2C_NAMES)} 條")

CAPTURE = CFG.CAPTURE_PATH


def _pb_cls(name):
    return message_factory.GetMessageClass(POOL.FindMessageTypeByName(PKG + name))


def _capture(rec):
    with _log_lock:
        with open(CAPTURE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _decode_c2s(s_id, m_id, body):
    name = C2S_NAMES.get(f"{s_id}_{m_id}")
    if not name:
        log(f"    (未知 C2S {s_id}_{m_id}，無 descriptor)")
        return None, None
    try:
        m = _pb_cls(name)()
        m.ParseFromString(body)
        return name, m
    except Exception as e:
        log(f"    ({name} 解碼失敗: {e})")
        return name, None


def _send_s2c(conn, s_id, m_id, body, compress=False):
    pkt = wire.encode_s2c(s_id, m_id, body, compress=compress)
    conn.sendall(pkt)
    s2c_name = S2C_NAMES.get(f"{s_id}_{m_id}")
    trig = s2c_to_c2s(s2c_name) if s2c_name else "?"
    callers = _callers(s2c_name) if s2c_name else []
    log(f"  SENT {s_id}_{m_id} ({s2c_name}) by c2s {trig} body={len(body)}B "
        f"wire={len(pkt)}B zflag={1 if compress else 0}"
        + (f"  handlers={callers}" if callers else ""))
    _capture({"t": datetime.datetime.now().isoformat(), "ev": "sent",
              "key": f"{s_id}_{m_id}", "s2c": s2c_name, "by_c2s": trig,
              "handlers": callers,
              "body_hex": body.hex(), "wire_hex": pkt.hex()})
    return pkt


def _send_msg(conn, s_id, m_id, msg):
    """序列化並送出；序列化失敗不讓整個連線中斷，只記錄。

    protobuf 在缺 required 欄位時會拋 EncodeError → 若讓它往上冒，
    socket 會被關掉、玩家被踢回登入（踩過 vitality_info_s2c 這個坑）。
    這裡改成印出缺哪些欄位、然後跳過該封包。
    """
    try:
        body = msg.SerializeToString()
    except Exception as e:
        log(f"  ⚠ s2c {s_id}_{m_id} 序列化失敗，略過此封包: {e}")
        return False
    _send_s2c(conn, s_id, m_id, body)
    return True


def _new_s2c(s_id, m_id):
    name = S2C_NAMES.get(f"{s_id}_{m_id}")
    if not name:
        return None
    try:
        return _pb_cls(name)()
    except Exception as e:
        log(f"    (無法建立 s2c {s_id}_{m_id} / {name}: {e})")
        return None


# ---------------- 各訊息的回應實作 ----------------
def _handle_1_1(conn):
    """login_auth_c2s → login_auth_s2c（角色列表）"""
    now = int(time.time())
    body = wire.build_login_auth_s2c(
        code=0, time_zone=8, serv_id=SERVER_ID, open_time=now - 86400 * 30,
        roles=[dict(id=ROLE_ID, name=ROLE_NAME, sex=1, level=ROLE_LEVEL,
                    last_login_time=now)],
        pool=POOL)
    _send_s2c(conn, 1, 1, body)


def _handle_1_0(conn, msg):
    """login_heart_c2s → login_heart_s2c（心跳；index 原值回傳）"""
    index = 0
    try:
        index = int(msg.index)
    except Exception:
        pass
    m = _new_s2c(1, 0)
    m.index = index
    m.server_time = int(time.time())
    m.run_time = 0
    _send_msg(conn, 1, 0, m)


def _handle_2_1(conn, msg):
    """role_gm_command_c2s → GM 指令（無 s2c，結果由伺服器推送）。

    客戶端 x.Game.Map.MapController.lua:549  Send_2_1(cmd) 送 `{cmd = "#xxx ..."}`。
    這一版是 GM 服，`DataTable_gm`（177 條）定義了完整的指令集，
    其中 #become_god / #all_func / #up_max_all_children 等就是
    「一鍵解鎖全部」——比我們在 Python 裡偽造資料正確得多，
    因為解鎖內容由遊戲自己的邏輯決定。

    實作策略：把指令記下來並依指令推送對應的資料更新，
    而不是假裝執行。未實作的指令只記錄（方便之後逐條補）。
    """
    cmd = ""
    try:
        cmd = str(msg.cmd)
    except Exception:
        pass
    log(f"  ★ GM 指令: {cmd!r}")
    _capture({"t": datetime.datetime.now().isoformat(), "ev": "gm_command", "cmd": cmd})

    parts = cmd.strip().lstrip("#").split()
    name = parts[0] if parts else ""
    args = parts[1:]

    if name in ("become_god", "all_func", "up_max_all_children",
                "add_children_all", "pass_all_dup", "pass_all_scenario"):
        # 這些是「全部解鎖」類：直接推送完整狀態
        _push_player_state(conn)
        _push_children(conn)
        _push_noob_stage(conn)
        # ★ 修正：`#all_func` 的語意是「解鎖全部功能」，必須一併重推
        #   24_1 open_func_all_s2c，否則客戶端的 FunOpenControl 不會重新
        #   評估按鈕開放狀態（先前只推 2_4/2_2/11_1/2_9，漏了這一條）。
        _push_open_func(conn)
        # ★ 2026-10-11：`#pass_all_dup` 的語意是「通關全部副本」，
        #   必須推 17_1 dup_info_s2c（`CheckDungeonPassById` 只看
        #   dungeonInfo 裡有沒有該 dup_id）。先前只推通用狀態 ⇒ 副本仍顯示未通關。
        if name == "pass_all_dup":
            _push_dup_info(conn)
        log(f"  -> 已依 {name} 推送完整狀態"
            f"（等級／資源／113 角色／教程完成／功能全開）")
    elif name == "add_children_all" or name == "add_children":
        _push_children(conn)
    else:
        log(f"  (指令 {name!r} 尚未實作，僅記錄；args={args})")


def _push_children(conn):
    """主動推送 11_1 children_all_s2c（全部角色滿級）。

    ★ 2026-10-11：只排除「缺 favor 資料」者（7 個瞳佔位符），
      未實裝但資料完整的角色照樣顯示 → 106 個。見 PD.formal_children()。
    """
    m = _new_s2c(11, 1)
    cls = _pb_cls("p_children")
    ids = PD.formal_children()
    for cid in ids:
        m.children_list.append(PD.build_maxed_child(cid, cls))
    _send_msg(conn, 11, 1, m)
    log(f"  -> 主動推送 {len(m.children_list)} 個角色"
        f"（只排除缺 favor 資料者，原始 113 個）")


def _push_player_state(conn):
    """主動推送玩家資源與身分屬性。

    為什麼要主動推：`Player.lvl` / `Player.money` 這些欄位是由
    `x.Module.Player.PlayerControl.lua` 的 `On_2_2`(role_info_s2c) 與
    `On_2_4`(role_resource_s2c) 寫入的；但客戶端在這條離線流程裡
    **不會主動請求 2_2 / 2_4**（實測送出 0 次），所以必須由伺服器推送，
    否則主界面的等級與資源會一直是預設值（Lv.999、精神力 1/1、三資源 0）。
    """
    # 2_4 role_resource_s2c：資源（屬性 id → 值）
    m = _new_s2c(2, 4)
    res = PD.player_resources()
    for aid, val in res:
        kv = m.k_v.add()
        kv.k = aid
        kv.v = val
    _send_msg(conn, 2, 4, m)
    log(f"  -> 主動推送資源 {len(res)} 項（lvl={PD.max_player_level()} "
        f"vit_max={PD.vit_max()} vip={PD.max_vip()}）")

    # 2_2 role_info_s2c：整數＋字串屬性
    m2 = _new_s2c(2, 2)
    for aid, val in res:
        kv = m2.kv_list.add()
        kv.k = aid
        kv.v = val
    for aid, sval in PD.player_str_resources():
        ks = m2.ks_list.add()
        ks.k = aid
        ks.s = sval
    _send_msg(conn, 2, 2, m2)
    log(f"  -> 主動推送 role_info：{len(m2.kv_list)} 整數 + {len(m2.ks_list)} 字串")


def _handle_1_3(conn, msg):
    """login_select_role_c2s → login_select_role_s2c（選角）"""
    role_id = PD.ROLE_ID
    try:
        role_id = int(msg.id)
    except Exception:
        pass
    m = _new_s2c(1, 3)
    m.code = 0
    m.id = role_id
    _send_msg(conn, 1, 3, m)
    log(f"  -> 已回覆選角成功 (id={role_id})")
    # 選角成功後推送流程狀態與玩家數值：
    #   _push_noob_stage   -> role_noob_stage_info（stage=29）流程推進，必須保留
    #   _push_player_state -> role_resource_s2c + role_info_s2c（Lv.100、資源…）
    # 客戶端不會主動要 2_4 / 2_2，必須由伺服器推，否則主界面一直是預設值。
    _push_noob_stage(conn)
    _push_player_state(conn)
    # ★ 2026-10-11：登入時一併推 `17_1 dup_info_s2c`（全部副本已通關）。
    #   為什麼必須在登入時推：`DungeonModel.InitDungeonInfo/UpdateDungeonInfo`
    #   只在「收到 17_1 的那一刻」填充 `dungeonInfo`；而 `CheckDungeonPassById`
    #   是查這張表。若等到使用者發 GM 才推，副本介面早已初始化完畢
    #   ⇒ 進度條仍顯示 00/17（實測截圖）。與 `_push_children` 同理。
    _push_dup_info(conn)


def _push_noob_stage(conn):
    """推送 role_noob_stage_info，stage = Finished(29)。

    ScenarioDefine.BeginnerStageType.Finished = 29；ScenarioControl.IsFinishBeginner
    以這個階段判斷教程是否結束，達到後就不再播新手引導。
    """
    try:
        m = _new_s2c(2, 9)
        m.stage = NOOB_STAGE_FINISHED
        _send_msg(conn, 2, 9, m)
        log(f"  -> 已推送新手教程狀態 stage={NOOB_STAGE_FINISHED}（Finished）")
    except Exception as e:
        log(f"  (推送 noob_stage 失敗: {e})")


def _handle_26_4(conn, msg):
    """scenario_happened_c2s → scenario_happened_s2c（已完成劇本清單）。

    ★ 2026-10-10 修正「客戶端把 26_2 連送 83 次」的根因（A 案）。

    客戶端 ScenarioModel.UpdateFinishedList（:769-797）是**唯一**填充
    `finishedList` 的地方，參數格式為 repeated p_key_value：
        finishedList[i].sys_id = A0_3[i].k
        finishedList[i].times  = A0_3[i].v
    `ScenarioControl`（未反編譯的 82KB 位元組碼）用 `finishedList` 判斷
    `IgnoreSend_26_2`，進而決定要不要送出 `26_2 scenario_enter_c2s`。

    原本回空清單 → finishedList 永遠空 → 客戶端反覆送 26_2（實測 83 次）。

    這裡回報 `DataTable_scenario` 中 id 1~1000 的核心線性劇情為「已完成」，
    其中包含客戶端一直在要求的 id=16（序章-作戰指引）。
    """
    m = _new_s2c(26, 4)
    ids = PD.done_scenario_ids()
    for sid in ids:
        kv = m.list.add()
        kv.k = sid
        kv.v = 1
    _send_msg(conn, 26, 4, m)
    log(f"  -> 已回覆劇情完成清單：{len(ids)} 筆"
        f"（含 id=16 序章-作戰指引：{16 in ids}）"
        f" ← 修復客戶端反覆送 26_2 的關鍵")


def _handle_26_1(conn, msg):
    """scenario_status_c2s → scenario_status_s2c（劇情狀態）。

    ★ 2026-10-10 修正（B 案）。

    客戶端 ScenarioModel.UpdateScenarioStatus 會把回傳的 `script_id`
    直接寫進 `curScenarioID`（`ScenarioModel.lua:2863-2865`）：
        L7_3 = L0_2.curScenarioID
        L7_3 = L7_3 == A0_3            -- 比對新舊是否相同
        L0_2.curScenarioID = A0_3      -- 直接覆蓋

    原本 `_generic_reply` + `_fill_required` 會把 script_id 填成 **1**
    （DataTable_scenario 的 id=1 是「參考劇情示例」），把客戶端導向一個
    沒人跑的劇本；而客戶端實際在跑 id=16。這裡明確回報「無進行中劇情」：
        script_id = 0, timepoint = 0, 三個清單留空
    """
    m = _new_s2c(26, 1)
    m.script_id = 0
    m.timepoint = 0
    # cur_sublist / chosen_sublist / next_list 留空 = 沒有進行中的劇情
    _send_msg(conn, 26, 1, m)
    log("  -> 已回覆劇情狀態：script_id=0 timepoint=0（無進行中劇情）")


def _handle_2_9(conn, msg):
    """客戶端查詢新手教程階段 → 回報已完成。"""
    _push_noob_stage(conn)


def _handle_31_1(conn, msg):
    """building_info_c2s → building_info_s2c（空島基建資訊）。

    ★ 2026-10-10 修正「點空島卡 90%」。

    症狀（logcat 完整堆疊）：
        [ERROR] call private._onUnderLoadingView error:
                ?:-1: attempt to index a boolean value
          ?: in field 'CheckCanUpgradByCondList'
          ?: in field 'CheckCanUnlockRoom'
          ?: in field 'CheckRoomStausEffect'
          ?: in field 'LoadRoom'
          ?: in field 'LoadLandAndRoom'

    根因鏈：
      1. 客戶端 `BuildTool.lua:3206-3215`（cond_type == 1 分支）：
             L10_2 = BuildModel.GetRoomInfoBySysId(L8_2)
             L11_2 = L10_2.info            ← 對 false 做索引 → 崩潰
      2. `GetRoomInfoBySysId` 查的是 `BuildModel.roomModel`
      3. `roomModel` 由 `31_1 building_info_s2c` 的 **room_list** 填充
      4. 伺服器原本沒有 `_handle_31_1`，走通用回應器
         → `room_list` 是空的（只填了 required 的 center，59 bytes）
         → 查不到任何房間 → 回 false → 崩潰 → 進度條卡 90%

    修法：明確回報 room_list，每個房型取 `DataTable_room` 的**最高等級**，
    這樣所有 `cond_list`（類型 1 = 要求某房型等級 ≥ N）都自然滿足。
    """
    m = _new_s2c(31, 1)

    # ---- center（REQUIRED）----
    atoms = PD.max_atoms()
    m.center.highest_atoms = atoms
    m.center.atoms_index = atoms
    m.center.pills_num = 0
    m.center.power = 0
    m.center.clean_times = 0
    m.center.next_time = 0
    m.center.power_speed = 0        # 注意：proto 型別是 int64（TYPE_INT64），不是 float
    m.center.next_gain_pill_time = 0
    m.center.end_time = 0

    # ---- room_list ----
    # ★ 2026-10-10 補上 object_list：先前沒填 → 房間裡空無一物。
    #   來源 DataTable_room.object_list（格式 [[物件id, 等級, [x,y,z]], ...]）
    defs = PD.room_default_objects()
    rid = 1
    for sys_id, lvl, row in PD.maxed_rooms():
        r = m.room_list.add()
        r.id = rid
        r.attach_room_id = sys_id       # 客戶端以 sys_id 關聯配置表
        r.sys_id = sys_id
        r.lvl = lvl
        r.atoms = 0
        r.used_elec = 0
        r.max_elec = int(row.get("atoms_max", 0) or 0) or 1000
        r.used_space = 0
        r.name = str(row.get("name") or "")
        r.upgrade_time = 0
        # 該房型的預設物件（object_list 是 repeated uint64，填物件 id）
        _lvl, items = defs.get(sys_id, (lvl, []))
        for obj_id, _olvl, _pos in items:
            r.object_list.append(obj_id)
        rid += 1

    _send_msg(conn, 31, 1, m)
    log(f"  -> 已回覆空島基建：center(highest_atoms={atoms}) + "
        f"{len(m.room_list)} 個房間（各房型最高等級 + 預設物件）"
        f" ← 修復「點空島卡 90%」")


def _handle_31_5(conn, msg):
    """building_place_c2s → building_place_s2c（放置物件到房間）。

    ★ 2026-10-10 修正「放置物品時右上角系統邏輯錯誤」。

    症狀（logcat）：
        LuaException: ?:-1: attempt to index a nil value
          ?: in field 'RefreshData'              （x.Module.Build.MachinePanelMaker.lua:532）
          ?: in method 'UpdateMachineInfoView'
          ?: in method 'OpenMachineInfoView'
          ?: in method 'SetOperateObjectInfo'
          ?: in method 'CheckCanPlace'           （拖曳放置時觸發）
          ?: in method 'Drag'

    根因（抓包解碼 tcp-capture.jsonl）：
        31_5 原本沒有 handler → 通用回應器造出四個清單，每個元素的 sys_id 都被
        `_fill_required` 填成 **1001**（DataTable_children 的角色 id，不是
        room_object）→ 客戶端 `GetSysroom_objectByKey(1001)` 回 nil →
        `nil.sub_type` / `nil.type` → 崩潰。
        （與 31_15 的 bug 同源，見 §3.4b）

    正解：**依客戶端請求回報**。請求格式：
        building_place_c2s { room_id, pos_list[{ id, face, pos_x, pos_y, pos_z }] }
    其中 `pos_list[].id` 是 **31_15 機器背包裡的機器 id**（1-based，與
    room_object_ids(Machine) 的順序一致）。
    """
    room_id = 0
    try:
        room_id = int(msg.room_id)
    except Exception:
        pass

    # id -> sys_id（與 _handle_31_15 推播的順序一致）
    machine_ids = PD.room_object_ids(PD.OBJECT_TYPE_MACHINE)
    meta = PD.room_object_meta()

    result = _new_s2c(31, 5)
    result.result = 0                       # 0 = 成功（明確覆寫填充器的 1）
    result.room_id = room_id

    placed = 0
    for p in msg.pos_list:
        try:
            mid = int(p.id)
        except Exception:
            continue
        idx = mid - 1
        if idx < 0 or idx >= len(machine_ids):
            continue
        sys_id = machine_ids[idx]
        oid = mid

        # p_building_object（房間內物件）
        o = result.object_list.add()
        o.id = oid
        o.room_id = room_id
        o.sys_id = sys_id
        o.lvl = 1
        o.status = 0
        o.is_valid = 1
        o.get_time = 0
        o.face = int(getattr(p, "face", 0) or 0)
        o.pos_x = int(getattr(p, "pos_x", 0) or 0)
        o.pos_y = int(getattr(p, "pos_y", 0) or 0)
        o.pos_z = int(getattr(p, "pos_z", 0) or 0)

        # p_building_machine（機器額外資訊）
        mac = result.mac_list.add()
        mac.id = oid
        mac.sys_id = sys_id
        mac.used_elec = 0
        mac.output = 0
        mac.output_max = 40
        mac.output_speed = 1
        mac.default_speed = 1
        mac.cost_power = 0
        mac.start_time = 0

        placed += 1

    _send_msg(conn, 31, 5, result)
    names = [str(meta.get(machine_ids[int(p.id) - 1], {}).get("name") or "")
             for p in msg.pos_list
             if 1 <= int(getattr(p, "id", 0) or 0) <= len(machine_ids)]
    log(f"  -> 已回覆放置物件：room_id={room_id} 放置 {placed} 台"
        f"（{names}）result=0 ← 修正原本填充器把 sys_id 填成 1001 導致崩潰")


def _handle_31_15(conn, msg):
    """building_spare_object_info_c2s → building_spare_object_info_s2c（備用物件／機器背包）。

    ★ 2026-10-10 修正「點空島子項目卡 85%」的真正根因。

    症狀（logcat）：
        [ERROR] BuildRoomView _sCB running error(?:-1: attempt to index a nil value
          ?: in field 'GetMachineBagList'
          ?: in method 'UpdateEditRed'
          ?: in method 'CleanObjectStatus'
          ?: in method 'EnterEditMode'
          ?: in method 'InitMainView'
          ?: in method 'HandleAfterOpenView'

    崩潰點 `BuildModel.lua:5996-6050` GetMachineBagList：
        for _, obj in pairs(BuildModel.allObjectBagInfo) do
            cfg = DataBase.GetSysroom_objectByKey(obj.sys_id)
            if cfg.type == ObjectType.Machine then ...    -- cfg 是 nil → 崩潰
        end

    `allObjectBagInfo` 由本訊息（31_15）填充。
    伺服器原本沒有 handler → 通用回應器 `_fill_required` 造出「一個假元素」：
        list=[{id=1, sys_id=1001, lvl=1, status=1, get_time=1, default_speed=1}]
    而 **`sys_id=1001` 是 DataTable_children 的角色 id，不是 room_object**！
    → `GetSysroom_objectByKey(1001)` 查不到 → `nil.type` → 崩潰。

    正解：推 `DataTable_room_object` 裡 type=1（Machine）的真實 id。
    """
    m = _new_s2c(31, 15)
    meta = PD.room_object_meta()
    oid = 1
    for sys_id in PD.room_object_ids(PD.OBJECT_TYPE_MACHINE):
        snap = m.list.add()
        snap.id = oid
        snap.sys_id = sys_id
        snap.lvl = 1
        snap.status = 0                 # 0 = 在背包中（未放置）
        snap.get_time = 0
        snap.default_speed = 1
        oid += 1
    _send_msg(conn, 31, 15, m)
    names = [str(meta.get(s, {}).get("name") or "") for s in
             PD.room_object_ids(PD.OBJECT_TYPE_MACHINE)[:3]]
    log(f"  -> 已回覆備用物件（機器背包）：{len(m.list)} 個真實機器 "
        f"sys_id={PD.room_object_ids(PD.OBJECT_TYPE_MACHINE)[:3]}… "
        f"（{names}）← 修復「卡 85%」的關鍵：不可再送 sys_id=1001 假資料")


def _handle_11_46(conn, msg):
    """children_bag_skin_list_c2s → 全部皮膚解鎖。

    兩層過濾：
    1. `DataTable_children_skin` 白名單（`valid_skin_ids()`）—— 濾掉配置表
       查不到的假 id（1701 / 91000071 / 91000072 / 91000073）。
    2. ★ 2026-10-10 新增：只推**已實裝角色**的皮膚（`formal_skins()`）——
       未實裝角色（`is_informal != 0`）的卡面／Spine 資源不在 OBB 裡，
       推了客戶端只會 404：
           [ERROR] card_pic_100903.ab not in res version
           [ERROR] Spine表找不到对应的id 100903
    """
    m = _new_s2c(11, 46)
    skins = PD.formal_skins()
    for s in skins:
        m.skin_list.append(s)
    _send_msg(conn, 11, 46, m)
    valid = PD.valid_skin_ids()
    bad = [s for s in skins if s not in valid]
    log(f"  -> 已回覆 {len(skins)} 個皮膚"
        f"（配置表真實 id {len(valid)} 個；過濾後殘留假 id = {len(bad)}"
        f"{'：' + str(bad) if bad else ' ✅'}）")


def _handle_children_all(conn, s_id, m_id):
    """children_all_s2c：全部角色、滿級滿星（等級來自 children_lvl 的星級上限）。

    ★ 2026-10-11（使用者要求）：改為**只排除資料不全者**，未實裝角色照樣顯示。
      113 個角色 → 106 個（只濾掉 7 個缺 favor 資料的「瞳」佔位符
      9100001~9100007，見 player_data.formal_children / unsafe_children）。

    歷史：2026-10-10 曾排除全部 is_informal != 0（83 個），
      理由是「未實裝角色的卡面／Spine 資源不在 OBB 裡，推了只會 404」。
      但 2026-10-11 實測 OBB 後發現該理由**不成立於真實未實裝角色**：
        id=1008 多蘿西 → 有 10081_f.ab
        id=2002 洛思特 → 有 A02002_kdcommon_ani.ab
        id=3011 維穆爾 / id=4010 荊索 → 均有資源
      只有「測試系列」(80001~80004) 與「瞳」佔位符才真的沒資源。
    """
    m = _new_s2c(s_id, m_id)
    cls = _pb_cls("p_children")
    ids = PD.formal_children()
    for cid in ids:
        m.children_list.append(PD.build_maxed_child(cid, cls))
    _send_msg(conn, s_id, m_id, m)
    log(f"  -> 已回覆 {len(m.children_list)} 個角色（滿級全解鎖；"
        f"只排除缺 favor 資料者，原始 113 個）")


def _push_open_func(conn):
    """主動推送 **24_1 open_func_all_s2c**（已開放功能清單）。

    客戶端 `x.Module.FunOpen.Control.FunOpenControl` 依這份清單決定
    主界面／各頁按鈕是「可點」還是「暫未連線」。功能 id 取自
    `DataTable_open_func`（85 個，id 範圍 1~99），滿級全解鎖帳號＝全部開放。

    ★ 2026-10-10 修正：GM 指令 `#all_func`（解鎖全部功能）原本只推
    2_4 / 2_2 / 11_1 / 2_9，**沒有重推 24_1** → 客戶端不會重新評估
    功能開放狀態。現在由 `_handle_2_1` 的解鎖分支一併呼叫本函式。
    """
    ids = PD.unlocked_func_ids()
    m = _new_s2c(24, 1)
    for i in ids:
        m.list.append(i)
    _send_msg(conn, 24, 1, m)
    log(f"  -> 已推送功能開放清單：{len(ids)} 個（來源 DataTable_open_func）")


def _handle_24_1(conn, msg):
    """open_func_all_c2s → open_func_all_s2c（已開放功能清單）。"""
    _push_open_func(conn)


def _handle_3_1(conn, msg):
    """item_info_c2s → item_info_s2c（背包道具清單）。

    客戶端收到後呼叫 `BagModel.InitBagInfo` → `DataBase.GetItemByKey(item_id)` 查表；
    item_id 必須是 `DataTable_item` 的合法 id，否則查表拿到 nil →
    在 Update 迴圈拋 LuaException → **主界面渲染中斷**（實際踩過 InitBagInfo 例外）。

    1123 個道具全送會讓包太大且拖慢主界面，取前 300 個（涵蓋各分類）。
    """
    items = PD.bag_items(limit=300)
    m = _new_s2c(3, 1)
    for iid, cnt in items:
        it = m.info.add()
        it.id = iid            # 實例 id（離線時與 item_id 相同即可）
        it.item_id = iid
        it.count = cnt
        it.bind = 0
    _send_msg(conn, 3, 1, m)
    log(f"  -> 已回覆背包 {len(m.info)} 個道具（來源 DataTable_item，共 {len(PD.item_rows())} 種）")


def _handle_36_1(conn, msg):
    """dispatch_info_c2s → dispatch_info_s2c（派遣）。

    客戶端 TeamModel.InitTeamData（:271-275）
        DataBase.GetSyseventByKey(event_id).team_num   ← event_id 必須合法
    空清單安全（派遣是可選功能），但若送 doing 就必須用真實 dispatch_id。
    """
    m = _new_s2c(36, 1)
    _send_msg(conn, 36, 1, m)
    log("  -> 已回覆派遣（空清單，避免 InitTeamList 用非法 id 崩潰）")


def _handle_18_1(conn, msg):
    """task_info_c2s → task_info_s2c（任務）。

    客戶端 TaskModel.InitTaskInfoByServer（:63-72）
        L8_3 = A0_3.accept_task; L8_3 = L8_3[1]; L8_3 = L8_3.task_id
    若 accept_task 是空清單 → L8_3[1] 為 nil → 崩潰。
    因此 task_doing 至少給一筆，task_id 取自 DataTable_task（已驗證 110001 合法）。
    """
    tid = PD.first_task_id()
    m = _new_s2c(18, 1)
    # task_done 可留空
    td = m.task_doing.add()
    td.task_id = tid
    td.state = 0
    track = td.track.add()          # 至少一筆 track，欄位齊全
    track.key_id = tid
    track.track_event = 0
    track.num = 0
    track.sum = 1
    _send_msg(conn, 18, 1, m)
    log(f"  -> 已回覆任務：task_doing=1 (task_id={tid}，來源 DataTable_task)")


def _handle_20_2(conn, msg):
    """sign_info_c2s → sign_info_s2c（簽到）。

    客戶端 SignControl.lua:300-312
        L1_3 = DataBase.GetSyssignByKey(A0_3.sign.id)
        L3_3 = L1_3.type          ← id 不存在 → nil → 崩潰
    通用填充器填 id=1，但 DataTable_sign 的 id 是 101..210 → 查不到。
    這裡改用真實 id（101）。

    ★ 2026-10-10 第二個 bug 修正（本次）：
      原本寫 `_new_s2c(20, 1)`，但 msgmap 的真實對照是：
          20_1 -> sign_daily_s2c   （欄位: sign_time / sign_list / month_card_sysids）
          20_2 -> sign_info_s2c    （欄位: sign_records ← 我們要用的）
      所以 `m.sign_records` 每次都在 20_1 的物件上拋
          AttributeError: sign_records
      （log 實測兩次：03:03:56、03:12:45），整個 handler 失效、簽到永遠不回。
      已改為 `_new_s2c(20, 2)` 並改送 `_send_msg(conn, 20, 2, m)`。
    """
    m = _new_s2c(20, 2)          # ★ 修正：20_2 對應 sign_info_s2c（原本誤用 20_1）
    ids = PD.sign_ids(1)
    if m is not None and ids:
        rec = m.sign_records.add()
        rec.code = 0
        rec.id = ids[0]
        rec.can_sign_total = 0
        # sign_indexs 留空：代表本期尚未簽到
    if m is not None:
        _send_msg(conn, 20, 2, m)
    log(f"  -> 已回覆簽到：id={ids}（來源 DataTable_sign，避免「不存在此签到id」）")


def _handle_37_2(conn, msg):
    """trade_order_list_c2s → trade_order_list_s2c（交易訂單）。

    客戶端 TradingNewModel.InitOrderInfo（:115-141）
        L6_3 = count_list 的元素
        L7_3[L6_3.k] = L6_3.v     ← 元素缺 k → table index is nil → 崩潰
    空清單安全（沒有訂單就沒有元素可迭代）。
    """
    m = _new_s2c(37, 2)
    _send_msg(conn, 37, 2, m)
    log("  -> 已回覆交易訂單（空清單，避免 InitOrderInfo 取 nil 的 k/v）")


def _handle_15_4(conn, msg):
    """cost_event_teams_c2s → cost_event_teams_s2c（編隊）。

    ★ 這是 `InitTeamList` 崩潰的來源。
    客戶端 x.Module.Team.TeamControl.lua:334-345
        L1_3 = A0_3.children_team
        if L1_3 then                       -- 非空才進這個分支
            L1_3 = L1_3[1]
            L1_3 = L1_3.event_id           ← event_id 必須存在於 DataTable_event
            TeamModel.InitTeamList(L1_3, A0_3)
        else
            L1_3 = L0_2.event_id           -- 空清單走這條（安全）
        end
    而 TeamModel.InitTeamData（:271-275）
        DataBase.GetSyseventByKey(event_id).team_num   ← id 不存在 → nil → 崩潰

    先前通用填充器會為 children_team 造出一個元素並把 event_id 填成 1，
    但 DataTable_event 的 id 是 10001 起 → 查不到 → 崩潰。
    這裡明確回空清單，讓客戶端走 else 的安全分支。
    """
    m = _new_s2c(15, 4)
    m.default_index = 0
    # children_team 保持空 → 客戶端走 else 分支
    _send_msg(conn, 15, 4, m)
    log("  -> 已回覆編隊（children_team 空清單，避免 InitTeamList 用非法 event_id）")


def _handle_40_1(conn, msg):
    """lottery_pool_c2s → lottery_pool_s2c（抽獎池清單）。

    客戶端 DailyLuckyDrawModel.CallBackDrawInfo 需要 pool_list[1]；
    空清單會 nil 迭代並在 Update 迴圈拋例外 → 主界面渲染異常。
    內容取自 DataTable_lottery。
    """
    pools = PD.lottery_pools()
    m = _new_s2c(40, 1)
    for pid, loop_cnt, stime, donate in pools:
        p = m.pool_list.add()
        p.sys_pool_id = pid
        p.loop_cnt = loop_cnt
        p.stime = stime
        p.donate_times = donate
    if not m.pool_list:
        # 配置表萬一為空也要給一個合法元素，避免客戶端 nil
        p = m.pool_list.add()
        p.sys_pool_id = 101
        p.loop_cnt = 999
        p.stime = 0
        p.donate_times = 0
    _send_msg(conn, 40, 1, m)
    log(f"  -> 已回覆抽獎池 {len(m.pool_list)} 個（來源 DataTable_lottery）")


def _handle_13_1(conn, msg):
    """vitality_info_c2s → vitality_info_s2c（精神力）。

    客戶端 x.Module.Vitality.VitalityControl.lua:198  On_13_1
        VitalityModel.UpdateInfo(A0_3.vitality, A0_3.vit_max, …)
    vit_max 直接取自 DataTable_lvl 的 `vit_max`（等級 100 → 140），
    而不是通用回應器填的 1（那會讓主界面顯示成 1/1）。
    """
    m = _new_s2c(13, 1)
    vmax = PD.vit_max()
    m.vitality = vmax
    m.vit_max = vmax
    m.exchange_num = 0
    m.next_time = 0
    # daily_reward / new_role_reward 是 required uint32（**純量，不是 repeated**，
    # 別用 .clear()）。漏填會讓 SerializeToString() 拋
    #   "missing required fields: daily_reward,new_role_reward"
    # → 連線中斷、玩家被踢回登入（實際踩過）。
    m.daily_reward = 0
    m.new_role_reward = 0
    _send_msg(conn, 13, 1, m)
    log(f"  -> 已回覆精神力 {vmax}/{vmax}（取 DataTable_lvl 的 vit_max）")


def _handle_11_20(conn, msg):
    """children_use_skin_c2s → children_use_skin_s2c（換裝／穿皮膚）。

    ★ 2026-10-11 新增。修復「時裝界面點『穿戴』無反應」。

    為什麼原本無反應（實測證據）：
      `11_20` 沒有明確 handler → 走 `_generic_reply`，只填 required 欄位中的
      `code`（實測回覆 body 僅 **6 bytes** = `08 00`）。
      但 proto 定義要求回三個欄位：
          children_use_skin_s2c {
            required uint32 code    = 1;
            required uint64 id      = 2;   ← 通用回應器沒填
            required uint64 skin_id = 3;   ← 通用回應器沒填
          }
      → 客戶端收到的回應缺 id/skin_id，無法確認換裝結果 → 丟棄 → **看起來無反應**。

    實測請求（logcat/伺服器日誌解碼）：
        FRAME 11_20 body hex = 08c13e1093d2dcc105
          id      = 8001
          skin_id = 1480010003

    修法：明確回 `code=0` + 原樣帶回 `id` / `skin_id`。
    """
    cid = int(getattr(msg, "id", 0) or 0)
    skin = int(getattr(msg, "skin_id", 0) or 0)
    m = _new_s2c(11, 20)
    m.code = 0
    m.id = cid
    m.skin_id = skin
    _send_msg(conn, 11, 20, m)
    log(f"  -> 已回覆換裝成功 id={cid} skin_id={skin}"
        f"（原本通用回應器只回 code，缺 id/skin_id → 客戶端無反應）")


def _handle_11_23(conn, msg):
    """children_assist_info_c2s → children_assist_info_s2c（看板娘／助理清單）。

    ★ 2026-10-11 新增。修復「點個人訊息右側齒輪 → 白屏」。

    為什麼原本會白屏（證據鏈）：
      1. `11_23` 沒有明確 handler → 走 `_generic_reply` → 只填 required 欄位，
         `list` 是空的（實測回覆 body 僅 15 bytes）
      2. 客戶端 `x.Module.Card.CardControl` proto 0.30 處理這個 s2c：
             if <list> then
                 CardModel:InitAssistInfo(<list>, <index>)
                 EventManager:TriggerEvent(CardEvent.SetAssistIndex,
                     <list>[1].id)          ← ★ L1148 GETI 3 3 1
             end
         它直接取 `list[1].id` → list 空 ⇒ index nil 的 .id ⇒
         `attempt to index a nil value` ⇒ CardAssistView 只載入一半 ⇒ 白屏。

    資料結構（from proto，已解碼確認）：
      children_assist_info_s2c {
        required uint32 mode  = 1;   // CardDefine.CardAssistMode = 1
        required uint32 index = 2;   // 當前看板娘在 list 中的位置
        repeated p_assist_info list = 3;
      }
      p_assist_info {
        required uint32 index       = 1;
        required uint64 id          = 2;   // 角色 id
        required uint32 type        = 3;   // 用途未確認，填 0
        required uint64 skin_sys_id = 4;   // 皮膚 id
      }

    設計（依使用者 2026-10-11 說明）：
      * 「理論上點擊看板娘可以設定成任何一個已經擁有的適格體」
        → `list` = 全部可安全顯示的角色（`formal_children()`，106 個）
      * 「每個角色的皮膚理論應該是在選擇角色的時候就可以選擇」
        → `list` 展開為「角色 × 皮膚」的組合，每個皮膚一筆，
          這樣選角色時就能連皮膚一起選
      * 當前看板娘 = `ROLE_ASSIST_DEFAULT_ID`（100001，使用者指定）

    ⚠ `type = 0` 是**推斷值**（依同族 `HeroType.Common = 0` 的慣例），
      不是實測證據。若助理列表仍是空的，優先懷疑這個欄位。
    """
    _build_assist_info(conn)


def _push_assist_info(conn):
    """主動推送 `11_23 children_assist_info_s2c`（看板娘清單）。

    ★ 2026-10-11 由 `_handle_11_23` 抽出來，讓 `_handle_11_7`（設定看板娘）
      也能重推 —— 這是修「助理設定無法儲存」的關鍵：客戶端只有在收到
      `11_23` 時才會更新「當前看板娘 index」，否則 UI 仍顯示舊的。
    """
    _build_assist_info(conn)


def _build_assist_info(conn):
    m = _new_s2c(11, 23)
    m.mode = 1

    # 當前看板娘：優先用使用者剛設定的（_assist_sel），否則用預設
    sel = _assist_sel or {}
    cur_id = int(sel.get("id") or PD.ROLE_ASSIST_DEFAULT_ID)
    cur_skin = sel.get("skin_id") or None
    want_index = int(sel.get("index") or 0)
    idx = 0
    cur_index = 0
    exact_index = 0          # (id, skin) 完全相符的那一筆
    id_index = 0             # 只論 id 相符的第一筆

    # ★★ 2026-10-12 **實驗**：`_assist_ordered_children()` 把瞳系排到最前，
    #   用於測定 `11_23.index` 的語意（詳見該函式的 docstring）。
    #   ⚠ 回退：把 `_assist_ordered_children()` 改成 `list(PD.formal_children())`。
    for cid in _assist_ordered_children():
        skins = PD.skin_by_child().get(cid) or []
        if not skins:
            continue
        # ⚠ 2026-10-11 曾嘗試「每角色一筆（103 筆）」，結果**破壞了使用者確認正常的
        #   「左右箭頭切換該角色皮膚」**（箭頭變成切換角色）⇒ 已回退為「角色×皮膚展開」。
        #   使用者明確表示：左右箭頭切換皮膚是**正常行為**，不可破壞。
        for sk in skins:
            idx += 1
            e = m.list.add()
            e.index = idx
            e.id = cid
            # ★★ 2026-10-12 **實驗 3**：`type` 改用**真實卡牌類型**（原本硬編 `0`）。
            #
            #   為什麼（推論鏈，基於使用者兩個關鍵觀察）：
            #     觀察 A：點瞳的頭像 → 大圖顯示厄莉希（**移除厄莉希後仍如此**）
            #             ⇒ 與清單內容無關，是 `id=1001` 被解析成厄莉希。
            #     觀察 B：厄莉希**不在適格體界面** ⇒ 其卡 `type=7` ≠ `Common(1)`
            #             ⇒ 被 `GetCardBagDic(cardList, 1)` 濾掉。
            #   ⇒ 假設：客戶端解析助理條目時，用 `(id, type)` 去**卡池**查卡；
            #     而瞳的卡 `type=1`、厄莉希的卡 `type=7`。
            #     若我方一律送 `type=0`，客戶端查不到 ⇒ 可能回退到 `id` 命中的卡。
            #   ⇒ 測法：送真實 type（瞳=1、厄莉希=7），看點瞳是否變成瞳。
            #
            #   ⚠ 回退：把下面兩行改回 `e.type = 0`。
            e.type = _card_type_of(cid)
            e.skin_sys_id = sk
            if cid == cur_id:
                if not id_index:
                    id_index = idx
                if cur_skin is not None and sk == cur_skin and not exact_index:
                    exact_index = idx

    # ★ 選定 `m.index`：用「由 skin/id 精確算出」的位置。
    #
    #   ⚠ 2026-10-11 教訓：曾改成「優先採信用戶端回報的 `want_index`」，
    #     結果**退化成「點誰都存成厄莉希」**（因為 `_assist_sel.index` 被存成
    #     用戶端的 1，而 1 = 厄莉希）。
    #     ⇒ **不可採用 `want_index`**。理由：
    #        用戶端的 `index` 是它自己那份清單的位置，而我方 322 筆的展開順序
    #        與它不同（例：skin=401 我方在第 308 筆），採用它就會指向錯誤條目。
    #
    #   現行策略（已驗證：其他角色顯示與儲存皆正確）：
    #     1. `exact_index`（id + skin 都相符）
    #     2. `id_index`（只論 id）
    #     3. 退回第一筆
    cur_index = 0
    if cur_skin is not None:
        cur_index = exact_index
    if not cur_index:
        cur_index = id_index
    if not cur_index:                       # 指定角色不存在 → 退回第一筆
        cur_index = 1
        if len(m.list):
            entry = m.list[0]
            cur_id = entry.id
            cur_skin = entry.skin_sys_id
    else:
        entry = m.list[cur_index - 1]
        cur_id = int(entry.id)
        cur_skin = int(entry.skin_sys_id)
    m.index = cur_index

    _send_msg(conn, 11, 23, m)
    # ★ 2026-10-12：把**實際送出的 11_23** 也寫進捕獲檔，便於核對「服務端發了什麼」
    #   （先前 `_capture` 只記 c2s，導致無法確認回應內容）。截取前 8 筆即可。
    try:
        _capture({"t": datetime.datetime.now().isoformat(), "ev": "s2c",
                  "key": "11_23", "cname": "children_assist_info_s2c",
                  "mode": int(m.mode), "index": int(m.index),
                  "list_len": len(m.list),
                  "list_head": [
                      {"index": int(e.index), "id": int(e.id),
                       "type": int(e.type), "skin": int(e.skin_sys_id)}
                      for e in list(m.list)[:8]],
                  "cur": {"id": cur_id, "skin": cur_skin},
                  "login_time": LAST_LOGIN_TIME["v"]})
    except Exception as _e:
        log(f"  (11_23 捕獲失敗: {_e})")
    log(f"  -> 已回覆看板娘清單：{len(m.list)} 筆 當前 index={m.index} "
        f"id={cur_id} skin={cur_skin}"
        f"（want_index={want_index} exact={exact_index} id_idx={id_index}）")


def _push_dup_info(conn):
    """推送 `17_1 dup_info_s2c`：把全部副本標記為「已通關」。

    ★ 2026-10-11 新增，實作 GM 指令 `#pass_all_dup`（DataTable_gm id=16）。

    為什麼這樣就能「通關」（客戶端位元組碼實證）：
      `x.Module.Dungeon.DungeonModel` `CheckDungeonPassById`（proto 0.40）：
          function CheckDungeonPassById(dupId)
              result = false
              if dungeonInfo[dupId] ~= nil then result = true end
              return result
          end
      ⇒ **只要該 dup_id 存在於 `dungeonInfo` 表就算已通關**，
        而 `dungeonInfo` 正是由本訊息的 `info` 清單填充。

    訊息結構：
      `dup_info_s2c { repeated p_role_dup info = 1 }`
      `p_role_dup { dup_id=1(REQ) star=2(REQ) is_agent=3(REQ)
                    task=4(rep,可空) challenge_times=5(REQ) sweep_lineup=6(rep,可空) }`

    取值依據：
      * `dup_id` 取自 `DataTable_dungeon`（**468 條**），只送配置表真實存在的 id
      * `star` = **3**（滿星；`DataTable_dungeon` 有 `rec_lvl_1_star`/`rec_lvl_2_star`
        與 `first_3_reward`，3 星是通關判定上限）
      * `is_agent` = 0、`challenge_times` = 0（保守值，兩者皆 only-display）
    """
    m = _new_s2c(17, 1)
    n = 0
    for r in PD.table("dungeon"):
        did = r.get("id")
        if did is None:
            continue
        try:
            did = int(did)
        except Exception:
            continue
        e = m.info.add()
        e.dup_id = did
        e.star = 3
        e.is_agent = 0
        e.challenge_times = 0
        n += 1
    _send_msg(conn, 17, 1, m)
    log(f"  -> 已推送 {n} 個副本通關狀態（17_1 dup_info，star=3）")
    return n


def _handle_17_1(conn, msg):
    """dup_info_c2s → dup_info_s2c（副本清單）。

    ★ 2026-10-11 新增。客戶端在此離線流程中會主動請求 17_1（實測日誌 30 次），
      原先前走通用回應器 ⇒ `info` 為空 ⇒ `dungeonInfo` 空 ⇒
      `CheckDungeonPassById` 恆為 false ⇒ 所有副本顯示未通關。

    回全部副本並標記已通關，使 GM 指令 `#pass_all_dup` 的語意成立。
    """
    _push_dup_info(conn)


def _handle_35_1(conn, msg):
    """hero_info_c2s → hero_info_s2c（英雄清單）。

    ★ 2026-10-10 修正「助理界面（齒輪）白屏」的根因。

    為什麼原本會白屏（完整證據鏈）：
      1. 原本 35_1 走通用回應器 `_generic_reply` → `_fill_required`
         `p_hero.type` 不是 *_id 系列欄位 → 被填保守值 **1**
         （見 _fill_required 的 `else: value = 1`）
      2. 但客戶端 `x.Module.Hero.HeroDefine.lua:14-19`：
             HeroType = { Common = 0, Teach = 1, PVP = 2, None = 3 }
         客戶端要的是 **Common = 0**
      3. `HeroModel.GetHeroInfoBySysId(HeroDefine.DefaultHeroSysId, Common, Hero)`
         （HeroModel.lua:210-241）逐項比對：
             sys_id == 1001 ✅ → type == HeroType.Common ❌（實際 1）→ 找不到
         → 回傳 nil
      4. `HeroModel.GetDefaultHeroCardInfo()`（HeroModel.lua:359-372）：
             L0_3 = GetHeroInfoBySysId(1001)   -- nil
             L1_3 = CardModel.GetCardInfoById(L0_3.children_id)   ← ★ 索引 nil
             → LuaException: attempt to index a nil value
      5. `CardAssistCardSubView.UpdateAssistCardList`（:794-796）中斷
         → `UpdateConditionBtnState` 中斷 → `HandleAfterOpenView` 中斷
         → **CardAssistView 只載入一半 → 白屏**
      6. logcat 堆疊實測吻合：
             ?: in field 'GetDefaultHeroCardInfo'
             ?: in method 'UpdateAssistCardList'
             ?: in method 'UpdateConditionBtnState'
             ?: in method 'HandleAfterOpenView'

    修法：明確送 `type = 0`（HeroType.Common），其餘欄位一律查配置表：
      * `sys_id` / `children_id` = `init_hero`（DataTable_config 的 key='init_hero'）
      * `id`        = 該角色在 DataTable_children 的 id
      * `awaketimes`= DataTable_children_awake 的 `times`（該角色全部覺醒段的數量-1，
                      實測 1001 為 times 0..4 → 4）
      * `form_list` = 1 個滿級 form，use_skin 取 `children.skin_list` 第一個合法皮膚
    """
    hid = PD.init_hero_sys_id()
    # ★★ 2026-10-11（**關鍵修復**）：`children_id` 必須是**瞳的角色 id（100000）**，
    #   不是 `init_hero`（1001）。
    #
    #   為什麼（這是「助理界面點瞳卻顯示厄莉希」的真正根因）：
    #     `DataTable_config['init_hero'] = 1001` 是**瞳的「英雄 id」**（`hero.id`）；
    #     `DataTable_hero` 顯示 `hero.id=1001 → children_id=100000`（瞳-強襲形態，order=1）
    #     ⇒ 瞳的**角色 id 是 100000**。
    #     而 `1001` 同時又是**角色 1001（厄莉希）的 children id** —— 兩套 id 撞號。
    #     先前直接 `h.children_id = hid (=1001)` ⇒ 客戶端解析成厄莉希
    #     ⇒ 助理大圖與名字都顯示厄莉希。
    #   ⇒ 改為 `PD.default_hero_children_id()`（由 `hero` 表按 order 最小者解析 = 100000）。
    cid = PD.default_hero_children_id()
    m = _new_s2c(35, 1)
    # 🚫 **紅線：`35_1` 必須送出 1 筆英雄，不可清空。**
    #
    #   2026-10-12 實驗 6：清空 `m.list`（令 `GetHeroInfoBySysId` 回 nil）
    #       ⇒ **助理界面白屏**（使用者實測截圖）
    #   ⇒ 證實 `GetAssistCloneHeroCardInfo()` 的回傳值是**必要欄位**，
    #     清空會讓 `cardInfo.roleImg` 取 nil ⇒ 白屏。
    #   ⚠ 回退開關留在原處（改 `False` 即恢復原邏輯）。
    _SKIP_HERO_LIST = False
    if _SKIP_HERO_LIST:
        _send_msg(conn, 35, 1, m)
        log("  -> [實驗 6] 已回覆**空**英雄清單（35_1 list=0）——測預覽是否依賴 p_hero")
        return
    h = m.list.add()
    # 🚫 **紅線：`h.id` 必須維持 `hid`（= 1001），不可改為 100000。**
    #
    #   2026-10-12 實驗 8b：把 `h.id`（與 `h.sys_id`）改為 `default_hero_children_id()`
    #       （= 100000）⇒ **助理界面白屏**（使用者實測）。
    #   ⇒ 原因：`h.id` 是 `GetHeroInfoBySysId(DefaultHeroSysId=1001)` 的查找鍵，
    #     改成 100000 後客戶端查不到 ⇒ 取 nil ⇒ 白屏。
    #   ⇒ 故 `h.id` 保持 `hid`；但 `h.sys_id` 仍可為 100000（實驗 8c，見下）。
    h.id = hid
    h.type = 0                       # ★ HeroType.Common（客戶端 GetHeroInfoBySysId 的比對條件）
    times = []
    for r in PD.table("children_awake"):
        if r.get("id") == hid:
            try:
                times.append(int(r.get("times", 0)))
            except Exception:
                pass
    h.awaketimes = max(times) if times else 0
    # 🚫 **紅線：`h.id` 與 `h.sys_id` 都必須維持 `hid`（= 1001），皆不可改為 100000。**
    #
    #   2026-10-12 實驗 8b：`h.id` 與 `h.sys_id` 同改 100000 ⇒ **助理界面白屏**
    #   2026-10-12 實驗 8c：只改 `h.sys_id`（`h.id` 保持 1001）⇒ **仍白屏**
    #   ⇒ 兩個欄位**各自**都會造成白屏。
    #
    #   【名字仍為厄莉希的真正原因】
    #     `CardAssistCardSubView` proto 13 L1410-1413：
    #         self:RefreshSkinBtn(cardInfo.sys_id)
    #     proto 14（RefreshSkinBtn）L1494-1502：
    #         skinName.text = DataBase:GetSyschildrenByKey(<參數>).name
    #     ⇒ 名字 = `GetSyschildrenByKey(英雄卡.sys_id).name`
    #     而 `cardInfo` = `HeroModel:GetAssistCloneHeroCardInfo()`（我方 `35_1` 的英雄）。
    #   ⇒ 但 `sys_id` 一改成 100000 就白屏 ⇒ **此欄位無法用來修名字**。
    #   ⇒ 名字與立繪由**不同欄位**驅動：
    #       立繪 ✅ 由 `p_hero.form_list` 的 `skin_list`（實驗 7 已修好）
    #       名字 ❌ 由 `p_hero.sys_id`（改不得）
    _HERO_SYS_SRC = hid                  # ← 實驗 8c 已回退（改 100000 會白屏）
    h.sys_id = _HERO_SYS_SRC
    # 🚫 **紅線：`children_id` 必須維持 `hid`（= 1001），不可改為 100000。**
    #
    #   2026-10-12 實驗 4（只改這一處，其餘 `f.lvl` / `skin_list` 皆保持用 `hid`）：
    #       改為 `PD.default_hero_children_id()`（= 100000，瞳的真實角色 id）
    #       ⇒ **助理界面白屏**（使用者實測截圖）
    #   ⇒ 證實白屏**確由本欄位造成**（2026-10-11 那次三處齊改，元凶就是這裡）。
    #
    #   為什麼不能用 100000（推測）：客戶端 `GetHeroInfoBySysId` 以 `hero.id`/`sys_id`
    #   建索引，`children_id` 必須與其內部「英雄→角色」對應一致；改成 100000 後
    #   客戶端在預載/初始化階段取不到對應項 ⇒ 白屏。
    h.children_id = hid
    f = h.form_list.add()
    f.form = 1
    f.sync_times = 0
    # ★★ 2026-10-12 **實驗 8**：`f.lvl` 也改用瞳（與 `_SKIN_SRC` 同源）。
    #
    #   為什麼：實驗 7 證實「把 `skin_list` 改成瞳的皮膚」**讓預覽立繪恢復正常**（使用者實測），
    #     但**名字仍為厄莉希**（名字走 `RefreshSkinBtn(cardInfo.sys_id)` → `GetSyschildrenByKey`）。
    #   ⇒ 推測 form 內仍有殘留「厄莉希」語意的欄位（`lvl` 目前取 `child_level(1001)`）。
    #   ⇒ 本實驗把整個 form 統一改為瞳，測名字是否跟著變。
    #
    #   ⚠ **回退方法**：把 `_SKIN_SRC` 那行的 `if True` 改為 `if False`。
    _SKIN_SRC = PD.default_hero_children_id() if True else hid   # ← 實驗開關（實驗 7+8）
    f.lvl = PD.child_level(_SKIN_SRC)
    f.exp = 0
    skins = PD.skin_by_child().get(_SKIN_SRC) or []
    f.use_skin = skins[0] if skins else 0
    for s in skins:
        f.skin_list.append(s)
    _send_msg(conn, 35, 1, m)
    log(f"  -> 已回覆英雄清單：{len(m.list)} 個（sys_id={hid} type=0(Common) "
        f"lvl={f.lvl} awaketimes={h.awaketimes} skins={len(skins)}）"
        f"  ← 修復助理界面白屏的關鍵欄位")


def _handle_2_5(conn, msg):
    """role_personal_info_c2s → 玩家個人資料。等級來自 DataTable_lvl（100 級）。"""
    m = _new_s2c(2, 5)
    PD.fill_role_info(m.info)
    _send_msg(conn, 2, 5, m)
    log(f"  -> 已回覆玩家資料 level={PD.max_player_level()} "
        f"children_num={m.info.children_num} "
        f"vit_max={PD.vit_max()} friend_max={PD.friend_max()}")


def _handle_2_4(conn, msg):
    """role_resource_c2s → role_resource_s2c（資源＝屬性 id 鍵值對）。

    客戶端 x.Module.Player.PlayerControl.lua:145  On_2_4
        UpdatePlayerIntValue(A0_3.k_v)  →  Player[屬性名] = 值
    鍵必須是 PlayerDefine.ATTR_SERVER_DRIVEN 的合法 id（501=money、604=lvl…），
    否則會寫進錯誤欄位或 nil。
    """
    m = _new_s2c(2, 4)
    res = PD.player_resources()
    for aid, val in res:
        kv = m.k_v.add()
        kv.k = aid
        kv.v = val
    _send_msg(conn, 2, 4, m)
    log(f"  -> 已回覆 {len(res)} 項資源（lvl={PD.max_player_level()} vit_max={PD.vit_max()}）")


def _handle_2_2(conn, msg):
    """role_info_c2s → role_info_s2c（整數＋字串屬性清單）。"""
    m = _new_s2c(2, 2)
    for aid, val in PD.player_resources():
        kv = m.kv_list.add()
        kv.k = aid
        kv.v = val
    for aid, sval in PD.player_str_resources():
        ks = m.ks_list.add()
        ks.k = aid
        ks.s = sval          # 注意：p_key_string 的值欄位叫 s，不是 v
    _send_msg(conn, 2, 2, m)
    log(f"  -> 已回覆 role_info：{len(m.kv_list)} 整數 + {len(m.ks_list)} 字串屬性")


def _handle_4_17(conn, msg):
    """nf_login_switch_c2s → nf_login_switch_s2c（登入切換地圖）。

    **這是打開主界面的閘門**：
      x.Game.Map.MapController.lua:10988  On_4_17
        if A0_3.type == 0 then
            ...
            if ScenarioModel.BeginnerStageISFinished() then
                OpenStartView()          → UIManager.OpenView("MainFrameView")
            else
                MainFrameModel.SetLoginFadeIn(false)   ← 只關淡入、不開界面 → 黑屏
    ★ 通用回應器會把 required 的 type 填成 1 → 一定走 else 分支 → 永遠黑屏。
      所以這裡必須明確填 0。
    """
    m = _new_s2c(4, 17)
    m.type = 0
    _send_msg(conn, 4, 17, m)
    log("  -> login_switch type=0（讓客戶端走「開主界面」分支）")


def _handle_2_27(conn, msg):
    """role_background_info_c2s → role_background_info_s2c（已解鎖的動態背景清單）。

    ★ 2026-10-11 修「助理設定界面卡死」。

    崩潰堆疊（logcat 實測，每次點該界面必崩）：
        LuaException: bad argument #1 to 'for iterator' (table expected, got nil)
        [C]: in function 'next'
          ?: in field '?'          ← CardControl.On_2_27（proto 0.46）
          ?: in field 'ProcessPacket'

    根因（`CardControl` proto 0.46 逐條讀出）：
        function On_2_27(msg)
            for _, v in pairs(msg.list) do            -- ★ msg.list 為 nil ⇒ pairs(nil) 崩
                CardModel:UpdateUnlockDynamicBg(v)
            end
            EventManager:TriggerEvent(CardEvent.RefreshDynamicBg)
        end

    `role_background_info_s2c { repeated int64 list = 1 }`。
    先前走通用回應器，`_fill_required` 只補 **required** 欄位，而 `list` 是 repeated
    ⇒ 完全不寫 ⇒ 序列化後 body=0B ⇒ 客戶端 C# 端的列表未被初始化為空表而是 nil
    ⇒ `pairs(nil)` 直接崩（注意：空表不會崩，nil 才會）。

    ★★ 2026-10-11 追加修正「助理設定 → 映像（背景）無法儲存」：
      先前只送**空清單**（僅為避免崩潰），導致「映像」格線只有預設的「元」，
      其餘背景全未解鎖 ⇒ 使用者選不到東西 ⇒ 儲存失敗。

      資料源（實測）`DataTable_back_ground` 僅 **2 條**：
          id=1  unlock_type=1  name=「元」             ← default，本來就看得到
          id=2  unlock_type=2  name=「心匣裡的假日」    ← itemUnlock，未解鎖 ⇒ 看不到
      客戶端 `CardAssistBackGroundSubView` proto 6 的判定（逐條讀出）：
          for _, v in pairs(DataBase:GetSysback_ground()) do
              if v.unlock_type == DynamicBgUnlockType.default
                 or CardModel:IsUnlockDynamicBg(v.id) then
                  table.insert(backGroundConfigList, v)
              end
          end
      （`CardDefine.DynamicBgUnlockType` 順序 = default / itemUnlock / conditionUnlock，
        對應 `unlock_type` 1 / 2 / 3。）

      ⇒ 本專案為**滿進度懷舊帳號**，故送出**全部背景 id** ⇒ 兩張映像都可選。
    """
    m = _new_s2c(2, 27)
    n = 0
    for r in PD.table("back_ground"):
        bid = r.get("id")
        if bid is None:
            continue
        try:
            m.list.append(int(bid))
            n += 1
        except Exception:
            continue
    _send_msg(conn, 2, 27, m)
    log(f"  -> 已回覆背景清單（2_27）：{n} 個 id = {list(m.list)}"
        f"（全部視為已解鎖；來源 DataTable_back_ground）")


def _handle_2_23(conn, msg):
    """role_set_background_c2s（設定目前映像／動態背景）。

    ★ 2026-10-11 新增。「助理設定 → 儲存」會依序送出三個包：
        `11_25`（看板娘清單，通知型）
        `11_7` （設定看板娘，有 s2c）
        `2_23` （設定背景／映像，**通知型**）
    協定表中 **沒有 `role_set_background_s2c`**（實測查無）⇒ 屬通知型，不需回應。
    先前走通用回應器路徑（`無 s2c 對照，略過`）其實行為相同，但加上明確 handler 是為了
    **記錄使用者選了哪個背景 id**，方便日後除錯與延續「目前映像」狀態。
    """
    bid = 0
    try:
        bid = int(msg.id)
    except Exception:
        pass
    log(f"  ★ 設定映像／背景：id={bid}（2_23 為通知型，本協定無 s2c，不回應）")
    # ⚠⚠ 2026-10-11：**不要**在這裡重推 `_push_player_state()`。
    #   曾加了 `PD.set_current_dynamic_bg(bid)` + `_push_player_state(conn)`，
    #   結果**主界面卡死**（使用者實測）。詳見交接文件 §0.5.5。
    #   故僅記錄，不推送 —— 也就是回到「儲存只寫本地、主界面不變」的狀態
    #   （該功能暫不可用，但不會破壞遊戲）。


def _handle_11_7(conn, msg):
    """children_set_assistant_c2s → children_set_assistant_s2c（設定當前看板娘）。

    ★ 2026-10-11 新增。修「助理設定無法儲存」。

    客戶端儲存流程（實測日誌）：
        FRAME 11_25 (children_set_assistant_list_c2s)   ← 通知型，無 s2c
        FRAME 11_7  (children_set_assistant_c2s)        ← 本函式
        FRAME 2_23  (role_set_background_c2s)           ← 通知型，無 s2c

    `children_set_assistant_c2s { index, id, type, skin_id }` —— 客戶端把
    「在清單中的位置、角色 id、類型、皮膚 id」送來。

    先前走通用回應器：只填 required 欄位、**不記錄選擇**，且不重推 `11_23`
    ⇒ 客戶端模型仍是舊的 `index`/當前看板娘 ⇒ 使用者看到「存不上」。

    ⇒ 修法：
      1. 記錄使用者選的 `id` / `skin_id`（模組級 `_assist_sel`），
         讓後續 `11_23` 能回報正確的當前看板娘；
      2. 回 `code=0` + 原樣帶回四個欄位（與 11_20 換裝同理，required 都要填）；
      3. 重推 `11_23`，讓客戶端列表／主頁看板娘立即刷新。
    """
    global _assist_sel
    try:
        a_index = int(msg.index)
        a_id = int(msg.id)
        a_type = int(msg.type)
        a_skin = int(msg.skin_id)
    except Exception:
        a_index = a_id = a_type = a_skin = 0

    # ★★ 2026-10-11：**用 `skin_id` 反查角色 id**，不要信任用戶端送的 `id`。
    #
    #   為什麼（實測日誌，這是「點瞳顯示厄莉希」的真正根因）：
    #     用戶端點瞳的頭像時送出 `id=1001, skin_id=101`。
    #     而 `skin 101` 在 `children.skin_list` 中屬於 **角色 100001（瞳）**；
    #     `id=1001` 卻是 **角色 1001（厄莉希）** —— 兩者相差一個數量級的命名空間，
    #     用戶端送的 `id` 在此為不可靠值（疑似它用的是另一套內部 id）。
    #     先前直接採信 `id=1001` ⇒ 取到厄莉希 ⇒ 大圖與名字都顯示厄莉希。
    #
    #   為什麼反查可靠：
    #     `skin_by_child()` 是「角色 → 皮膚」的權威映射（源自 `DataTable_children.skin_list`），
    #     實測 **328 顆皮膚中沒有任何一顆被兩個角色引用**（無歧義，可安全反查）。
    #     驗證：skin=101→[100001]、skin=1001→[100000]、skin=1410010001→[1001]。
    #
    #   策略：若能由 `skin_id` 唯一反查出角色，就以它為準；否則退回用戶端送的 `id`。
    resolved_id = a_id
    if a_skin:
        cand = PD.skin_to_child().get(a_skin)
        if cand is not None:
            resolved_id = cand
            if cand != a_id:
                log(f"  (以 skin={a_skin} 反查角色: 用戶端送 id={a_id} → 修正為 {cand})")

    if resolved_id:
        # ★ 一併記下用戶端送的 `index`：客戶端 `CardControl` proto 0.30（On_11_23）
        #   L1147-1149 是 `TriggerEvent(CardEvent.SetAssistIndex, list[1].id)`
        #   —— 它固定取 `list[1]`，故我方 `11_23` 的 `m.index` 必須與之一致。
        _assist_sel = {"index": a_index, "id": resolved_id,
                       "skin_id": a_skin, "type": a_type}
    log(f"  ★ 設定看板娘：id={a_id} skin={a_skin} type={a_type} index={a_index}"
        f" → 採用角色 id={resolved_id}")

    m = _new_s2c(11, 7)
    # ⚠ `children_set_assistant_s2c` 只有 4 個 required 欄位：
    #     index / id / type / skin_id —— **沒有 `code`**。
    #   先前誤抄 11_20 的模板寫了 `m.code = 0`，導致
    #     AttributeError: Protocol message ... has no "code" field
    #   ⇒ 回應根本沒送出去 ⇒ 使用者看到「點擊無反應、存不上」。
    # ★ 回應必須用**反查後的正確值**，否則大圖會顯示錯角色。
    #
    #   為什麼（這是「瞳顯示厄莉希」的**顯示層根因**）：
    #     使用者點瞳時，用戶端送 `id=1001, skin_id=401, index=1`。
    #     若照抄回 `m.id = a_id (=1001)`，用戶端拿 `1001` 去查卡 ⇒ 顯示**厄莉希**。
    #     （儲存之所以正確，是因為儲存用的是我方反查後的 `resolved_id`；
    #       顯示與儲存走不同欄位 ⇒ 出現「大圖錯、但存對」的怪象。）
    #   ⇒ 回應中的 `id` 用 `resolved_id`，`index` 用「與之一致的清單位置」，
    #     讓用戶端的顯示與儲存來源統一。
    #
    #   ⚠ 注意：**不可**用 `a_index` 當 `m.index` —— 用戶端的 index 是它自己
    #     那份清單的位置，與我方 322 筆展開列表不同（教訓：曾改成用它，
    #     結果退化成「點誰都存成厄莉希」）。
    m.index = _assist_index_of(resolved_id, a_skin) or a_index
    m.id = resolved_id
    m.type = a_type
    m.skin_id = a_skin
    _send_msg(conn, 11, 7, m)
    # 重推 11_23：客戶端才會把「當前看板娘」更新成剛選的這一筆
    _push_assist_info(conn)
    log(f"  -> 11_7 回應已送出（index={m.index} id={m.id} skin={m.skin_id}）")


def _card_type_of(cid):
    """角色 id -> 助理清單（`p_assist_info.type`）該填的值。

    ★★ 2026-10-12 **依客戶端原始碼推導**（實驗 3 的修正版）。

    來源（`CardAssistCardSubView` proto 3.0.1.0，行 704-727 —— 點縮圖時的構造）：
        local info = CardAssistInfo:New()
        info.id     = id                                   -- 被點格子的 id
        info.index  = 1                                    -- ★ 硬編為 1
        info.skin_id = use_skin
        info.type   = (basicConfig.is_hero == 1) and 0 or 1 -- ★★ 就是這條
    ⇒ **`type` = 瞳系（`is_hero==1`）取 `0`；其餘角色（`is_hero==0`）取 `1`。**

    另註：`DataTable_children.is_hero` 是**配置表真實欄位**
    （實測分布 `{0: 98, 1: 15}`，`is_hero==1` 的 15 個**全部是瞳系**
      —— `100000~100007` + `9100001~9100007`）。

    ⚠ 與 `_handle_11_1` 的卡牌 `type`（`CardTypeIndex`）**不是同一個東西**：
      卡牌 `type`：`init_hero(1001)`=7、其餘=1（見 §0.5.1）
      助理 `type`：瞳系=0、其餘=1（本函式）
    """
    try:
        cid = int(cid)
    except Exception:
        return 1
    try:
        rows = PD.children_rows()
        for r in rows:
            if int(r.get("id") or r.get("_key") or 0) == cid:
                return 0 if str(r.get("is_hero")) in ("1", "True", "true") else 1
    except Exception:
        pass
    return 1


def _assist_ordered_children():
    """助理清單的角色順序。

    ⚠ 2026-10-12 **實驗 1 已結束**：曾把瞳系排到最前（測 `index` 語意），
      結果 ⇒ 格線第 1 格確實變瞳，但**點縮圖的大圖預覽仍顯示厄莉希**
      ⇒ 證明預覽與清單順序無關 ⇒ **已恢復原順序**。
      （要重做：把 `return` 改成 `[c for c in kids if is_tong(c)] + [c for c in kids if not is_tong(c)]`。）
    """
    return list(PD.formal_children())


def _assist_index_of(cid, skin):
    """回傳 `(cid, skin)` 在「角色×皮膚展開」清單中的 1-based 位置。

    供 `_handle_11_7` 計算與 `resolved_id` 一致的 `m.index`。
    找不到完全相符的 skin 時，退回該角色的第一筆。
    ⚠ 順序**必須**與 `_build_assist_info()` 相同 ⇒ 一律走 `_assist_ordered_children()`。
    """
    i = 0
    first_of_cid = 0
    for c in _assist_ordered_children():
        for s in (PD.skin_by_child().get(c) or []):
            i += 1
            if c == cid:
                if not first_of_cid:
                    first_of_cid = i
                if skin and s == skin:
                    return i
    return first_of_cid


def _handle_11_25(conn, msg):
    """children_set_assistant_list_c2s（通知型，無 s2c）。

    ★ 2026-10-11 新增。客戶端在儲存看板娘時會把**整份清單**送來
    （`repeated p_assist_info list`）。此訊息在協定表中沒有 s2c
    （`proto_num_map` 查無），屬通知型 —— 回應反而可能造成問題。

    ⇒ 只記錄，不回應。這樣 `11_7` 的重推就能讓 UI 刷新。
    """
    n = 0
    try:
        n = len(msg.list)
    except Exception:
        pass
    log(f"  (11_25 設定看板娘清單：{n} 筆；通知型，不回應)")


def _handle_52_12(conn, msg):
    """common_activity_task_list_c2s → 活動任務清單（必須用配置表真實 sys_id）。

    ★ 2026-10-11 修正「活動面板崩潰」。崩潰堆疊（logcat 實測）：
        LuaException: attempt to index a nil value
            ?: in field 'InitTaskInfo'
            ?: in field 'ProcessPacket'

    根因鏈（客戶端位元組碼 `SummerActivityModel` proto 0.6 `InitTaskInfo`）：
        for _, cur in ipairs(info.task_list or {}) do
            local cfg = DataBase:GetSysactivity_taskByKey(cur.sys_id)   -- L11-14
            ...
        end
      ⇒ `task_list` 的每個元素都必須有**存在於 `DataTable_activity_task` 的 sys_id**。
        查不到 ⇒ cfg 為 nil ⇒ 後續索引崩潰。

    為什麼原本會壞（設計衝突）：
      `52_12` 原本列在 `EMPTY_LIST_REPLY` 裡，流程是
        ① 清空所有 repeated 欄位  ② 呼叫 `_fill_required(m)`
      但 `_fill_required` 的規則之一是「repeated 訊息欄位若子項有 required 欄位，
      就補『一個』最小合法元素」——而 `p_activity_task { sys_id, cur, state }`
      三個都是 required ⇒ **剛清空立刻又被補回一個假元素**，
      其 `sys_id` 是保守預設值（別張表的 id）⇒ 查不到配置 ⇒ 崩潰。

    修法：不再靠「清空 + 自動補」，改為**明確依配置表建構合法任務清單**。
    """
    m = _new_s2c(52, 12)
    n_done = n_doing = 0
    for r in PD.table("activity_task"):
        sid = r.get("id")
        if sid is None:
            continue
        try:
            sid = int(sid)
        except Exception:
            continue
        e = m.task_list.add()
        e.sys_id = sid
        # 狀態：1=已完成（可領獎）、0=進行中。此處給「已完成」，
        # 因為本專案是滿進度懷舊帳號；cur 為已完成次數。
        e.cur = 1
        e.state = 1
        n_done += 1
    _send_msg(conn, 52, 12, m)
    log(f"  -> 已回覆活動任務 {len(m.task_list)} 筆"
        f"（52_12，全部標記為已完成；來源 DataTable_activity_task）")
    return n_done


def _handle_52_3(conn, msg):
    """common_activity_get_activity_list_c2s → 活動列表（必須非空且結構完整）。

    為什麼要這麼講究：
      x.Module.Activity.ActivityControl.lua:570
          ActivityModel.UpdateActivityList(A0_3.activity_list)   ← 沒有 nil 保護
      x.Module.Activity.ActivityModel.lua:486-500
          ipairs(A0_3.activity_list)                              ← 巢狀清單必須存在
    所以：
      1) 外層 activity_list 至少要有一個元素；
      2) 每個 p_common_activity 的巢狀 activity_list 也至少要有一筆。
    內容全部取自遊戲自己的配置表（DataTable_activity_main / DataTable_activity）。
    """
    m = _new_s2c(52, 3)
    brief_cls = _pb_cls("p_activity_brie_info")
    added = 0
    for tid in PD.activity_types():
        briefs = PD.activity_briefs_for_type(tid)
        if not briefs:
            continue                      # 沒有已開啟活動的類別就不要放，免得巢狀清單為空
        entry = m.activity_list.add()
        entry.type_id = tid
        for aid, end_time, red in briefs:
            b = entry.activity_list.add()
            b.activity_id = aid
            b.end_time = end_time
            b.red_point = red
        added += 1
    if added == 0:
        # 保險：真的沒有任何活動時，造一個結構完整的最小元素，避免客戶端炸掉
        entry = m.activity_list.add()
        entry.type_id = (PD.activity_types() or [1001])[0]
        b = entry.activity_list.add()
        b.activity_id = entry.type_id * 100 + 1
        b.end_time = int(time.time()) + 86400 * 30
        b.red_point = 0
        added = 1
        log("  (配置表查無已開啟活動，改回最小合法元素)")
    _send_msg(conn, 52, 3, m)
    log(f"  -> 已回覆活動列表：{added} 個類別、共 {len(m.activity_list)} 筆外層元素")


# 只回一次的訊息：這些訊息的客戶端 handler 本身會「再送一次同一個請求」，
# 若每次都回應就會變成無限 ping-pong（實測 45_6 recharge_new_sync 在 1 秒內
# 送了 2773 次，把主執行緒佔滿 → 畫面全黑）。
# 對照：x.Module.Shop.ShopControl.lua:588  On_Fun_45_6 → Send_45_6（自我重送）
REPLY_ONCE = {"45_6"}
_replied_once = set()
# 完全不回應的訊息（客戶端 self-loop；回應只會讓它再送）
NO_REPLY = set()

# 明確回「空清單」的訊息：這些 s2c 帶有巢狀 repeated 訊息，客戶端會往裡迭代，
# 造出半殘元素會讓它 ipairs(nil) 而中斷整個封包處理（畫面全黑）。
# 注意：`52_3` **不能**放這裡 —— 客戶端 x.Module.Activity.ActivityControl.lua:570
# 直接讀 `A0_3.activity_list` 且沒有 nil 保護，空清單會炸 → 由 _handle_52_3 專門處理。
# ★ 2026-10-11：使用者設定的看板娘（由 `_handle_11_7` 寫入，`_build_assist_info` 讀取）。
#   為什麼需要：客戶端儲存後必須收到重推的 `11_23` 才會更新「當前看板娘」，
#   而重推時要知道「使用者選了哪一筆」⇒ 用這個模組級狀態記住。
#   `None` = 尚未設定過 ⇒ 用 `PD.ROLE_ASSIST_DEFAULT_ID`。
_assist_sel = None

EMPTY_LIST_REPLY = {    "52_1",    # common_activity_get_activity_info_s2c -> gift_list
    # ★ 2026-10-11 移除 "52_12"：它的 task_list 子項 p_activity_task 三個欄位皆 required，
    #   而 _fill_required 會「清空後又補一個最小元素」⇒ 該元素的 sys_id 查不到配置表
    #   ⇒ 客戶端 SummerActivityModel.InitTaskInfo 索引 nil 崩潰。
    #   改由 _handle_52_12() 明確建構合法清單（見該函式註解）。
}


def _pf_cls(name):
    try:
        return message_factory.GetMessageClass(POOL.FindMessageTypeByName(PKG + name))
    except Exception:
        return None


@functools.lru_cache(maxsize=None)
def s2c_to_c2s(s2c_name):
    """反查「哪個 c2s 會讓客戶端處理這個 s2c」——用來對齊 logcat 例外。"""
    for k, v in C2S_NAMES.items():
        if v == s2c_name:
            return k
    # 命名慣例：xxx_info_s2c <- xxx_info_c2s
    for k, v in C2S_NAMES.items():
        if v.endswith("_c2s") and s2c_name == v[:-4] + "_s2c":
            return k
    return "?"


def _callers(s2c_name):
    """找出所有「處理這個 s2c」的 Lua 函式名，寫進 log/擷取檔以備對齊例外。"""
    try:
        return _CALLER_CACHE[s2c_name]
    except KeyError:
        pass
    out = []
    try:
        import re as _re
        pat = _re.compile(r'function (L\d+_\d+)\(A0_3\)')
        for p in _CALLER_FILES:
            try:
                txt = open(p, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            if s2c_name not in txt:
                continue
            for m in pat.finditer(txt):
                seg = txt[m.start():m.start() + 1400]
                if "A0_3." in seg:
                    out.append("%s:%s" % (os.path.basename(p)[:-4], m.group(1)))
    except Exception:
        pass
    out = out[:6]
    _CALLER_CACHE[s2c_name] = out
    return out


_CALLER_CACHE = {}
_CALLER_FILES = []


def _init_caller_files():
    """挑出可能含有 s2c 處理器的模組（Control/Model）以加速反查。

    注意：`data/lua-src` 是**可選**的（反編譯的 Lua 源碼，約 25MB）。
    沒有它也能正常運行，只是 log 裡少了「這個 s2c 被哪個 Lua 函式處理」的對照。
    """
    base = CFG.LUA_SRC
    if not base or not os.path.isdir(base):
        log(f"handler 反查: 略過（{base} 不存在，屬正常）")
        return
    try:
        for fn in os.listdir(base):
            if not fn.endswith(".lua"):
                continue
            if ("Control" in fn) or ("Model" in fn):
                _CALLER_FILES.append(os.path.join(base, fn))
    except Exception:
        pass
    log(f"handler 反查檔數: {len(_CALLER_FILES)}")


_init_caller_files()


def _fill_required(msg, depth=0):
    """遞迴補齊 proto2 required 欄位，避免序列化失敗或客戶端 nil 迭代。

    這批 proto 幾乎全是 required。實測 578 個 s2c 裡有 **443 個**空訊息
    就無法序列化（`SerializeToString()` 拋 "missing required fields"），
    若例外冒到 socket 層就會**中斷連線、把玩家踢回登入**。

    規則（依踩坑經驗調整）：
      * required 純量 → 填保守預設（整數 1、字串 ""、列舉取第一個非 0）
      * required 巢狀訊息 → 遞迴往裡填
      * **repeated 訊息欄位 → 若其子項有 required 欄位，補「一個」最小合法元素**。
        為什麼要補：客戶端常寫 `local p = msg.pool_list[1]; p.sys_pool_id …`，
        或對子清單做迭代；完全空清單會讓它拿到 nil →
        `bad argument #1 to 'for iterator' (table expected, got nil)`。
        （實例：lottery_pool_s2c 空的 → DailyLuckyDrawModel.CallBackDrawInfo 崩潰）
        但也**只補一個**，避免造出大量半殘元素。
    """
    if depth > 5:
        return
    for f in msg.DESCRIPTOR.fields:
        if f.message_type is not None and getattr(f, "is_repeated", False):
            # 只在子項「有 required」時才補元素，否則維持空清單（安全）
            try:
                sub_required = [g for g in f.message_type.fields
                                if getattr(g, "is_required", False)]
            except Exception:
                sub_required = []
            if not sub_required:
                continue
            try:
                if len(getattr(msg, f.name)) == 0:
                    elem = getattr(msg, f.name).add()
                    _fill_required(elem, depth + 1)
            except Exception:
                pass
            continue

        if not getattr(f, "is_required", False):
            continue

        if f.message_type is not None:
            try:
                _fill_required(getattr(msg, f.name), depth + 1)
            except Exception:
                pass
            continue

        if f.type == f.TYPE_STRING:
            value = ""
        elif f.type == f.TYPE_BYTES:
            value = b""
        elif f.type == f.TYPE_BOOL:
            value = False
        elif f.type in (f.TYPE_DOUBLE, f.TYPE_FLOAT):
            value = 0.0
        elif f.enum_type is not None:
            try:
                value = next((v.number for v in f.enum_type.values if v.number != 0), 0)
            except Exception:
                value = 0
        else:
            # 整數欄位：若是 *_id 系列，填「配置表真的存在的 id」。
            # 憑空填 1 會讓客戶端查表失敗 → nil → Update 迴圈拋例外
            # （實際踩過：item_id=1 導致 BagModel.InitBagInfo 崩潰）。
            fname = f.name.lower()
            if fname == "id" or fname.endswith("_id") or fname.endswith("id"):
                value = PD.real_id_for(f.name, 1)
            else:
                value = 1
        try:
            setattr(msg, f.name, value)
        except Exception:
            pass


def _generic_reply(conn, s_id, m_id, cname, msg):
    """通用回應：s2c 的 code 填 0，頂層 required 純量補預設值。

    若 s2c 含有「repeated 巢狀訊息」欄位，客戶端常會對它 ipairs 並再往裡
    ipairs 子清單。這種情況下我們一律回**空清單**（合法且等同「目前沒有
    資料」），而不是造出半殘元素。
    """
    m = _new_s2c(s_id, m_id)
    if m is None:
        return False
    # ★★★ 順序極重要：必須先 _fill_required、後設 code ★★★
    #
    # 症狀：login_repeat_s2c（1_4）回 code=1 → 客戶端印
    #       [LoginControl] 登入出錯 ... #QR系统邏輯錯誤#n → 連線立即關閉。
    #
    # 根因：_fill_required 對「非 *_id 的整數 required 欄位」一律填保守值 1，
    #       而 `code` 正好符合這個條件 → 被填成 1（= 失敗）。
    #       原本的程式碼先設 m.code = 0、才呼叫 _fill_required(m)，
    #       所以 0 被覆寫成 1。
    #
    # 對策：把 _fill_required 提到前面，最後才明確覆寫 code = 0（成功）。
    try:
        _fill_required(m)
    except Exception:
        pass
    try:
        if m.DESCRIPTOR.fields_by_name.get("code") is not None:
            m.code = 0
    except Exception:
        pass
    try:
        _send_msg(conn, s_id, m_id, m)
    except Exception as e:
        log(f"    (s2c {s_id}_{m_id} 序列化/送出失敗: {e})")
        return False
    return True


def game_loop(conn, addr):
    conn.settimeout(300)
    buf = first_bytes[0]
    log(f"GAME PROTO 首包 {len(buf)} bytes: {buf.hex()}")
    reader = wire.FrameReader()          # 會自動丟棄 01 02 banner
    for raw in reader.feed(buf):
        _dispatch(conn, raw)
    while True:
        try:
            chunk = conn.recv(8192)
        except socket.timeout:
            log("GAME PROTO 讀取超時")
            return
        except Exception as e:
            log(f"GAME PROTO 錯誤: {e}")
            return
        if not chunk:
            log("GAME PROTO 連線關閉")
            return
        log(f"GAME PROTO RECV {len(chunk)} bytes: {chunk.hex()}")
        for raw in reader.feed(chunk):
            _dispatch(conn, raw)


def _dispatch(conn, raw):
    """處理一個 C2S 封包（raw 為含長度頭的完整位元組）。"""
    try:
        d = wire.decode_c2s(raw)
    except Exception as e:
        log(f"  (封包解碼失敗: {e}) raw={raw.hex()[:120]}")
        return
    s_id, m_id, uniq, body = d["sId"], d["mId"], d["uniq"], d["body"]
    key = f"{s_id}_{m_id}"
    cname, msg = _decode_c2s(s_id, m_id, body)
    log(f"  FRAME {key} ({cname or '?'}) uniq={uniq} body={len(body)}B")
    _capture({"t": datetime.datetime.now().isoformat(), "ev": "frame", "key": key,
              "cname": cname, "uniq": uniq, "body_hex": body.hex(),
              "text": str(msg).replace("\n", " | ")[:1200] if msg is not None else None,
              "login_time": LAST_LOGIN_TIME["v"]})

    # ---- handler 呼叫鏈保護（見 fix_dispatch_try.py）----
    # 單一 handler 失敗只記錄，不再讓例外冒到 game_loop/handle 而關閉連線。
    try:
        if key == "1_1":
            _handle_1_1(conn)
        elif key == "1_0":
            _handle_1_0(conn, msg)
        elif key == "1_3":
            _handle_1_3(conn, msg)
        elif key == "2_9":
            _handle_2_9(conn, msg)
        elif key == "26_4":                        # scenario_happened → 劇情完成清單
            _handle_26_4(conn, msg)
        elif key == "26_1":                        # scenario_status → 劇情狀態
            _handle_26_1(conn, msg)
        elif key == "31_1":                        # building_info → 空島基建
            _handle_31_1(conn, msg)
        elif key == "31_5":                        # building_place → 放置物件
            _handle_31_5(conn, msg)
        elif key == "31_15":                       # building_spare_object_info → 機器背包
            _handle_31_15(conn, msg)
        elif key == "35_1":                        # hero_info_c2s → 英雄清單
            _handle_35_1(conn, msg)
        elif key == "17_1":                        # dup_info_c2s → 副本清單（已通關）
            _handle_17_1(conn, msg)
        elif key == "11_23":                       # children_assist_info_c2s → 看板娘清單
            _handle_11_23(conn, msg)
        elif key == "11_20":                       # children_use_skin_c2s → 換裝
            _handle_11_20(conn, msg)
        elif key == "11_7":                        # children_set_assistant → 設定看板娘
            _handle_11_7(conn, msg)
        elif key == "11_25":                       # children_set_assistant_list → 通知型
            _handle_11_25(conn, msg)
        elif key == "2_5":
            _handle_2_5(conn, msg)
        elif key == "2_4":
            _handle_2_4(conn, msg)
        elif key == "2_2":
            _handle_2_2(conn, msg)
        elif key == "52_3":
            _handle_52_3(conn, msg)
        elif key == "52_12":                       # common_activity_task_list → 活動任務
            _handle_52_12(conn, msg)
        elif key == "2_27":                        # role_background_info → 動態背景清單
            _handle_2_27(conn, msg)
        elif key == "2_23":                        # role_set_background → 設定映像（通知型）
            _handle_2_23(conn, msg)
        elif key == "4_17":
            _handle_4_17(conn, msg)
        elif key == "13_1":
            _handle_13_1(conn, msg)
        elif key == "24_1":
            _handle_24_1(conn, msg)
        elif key == "2_1":
            _handle_2_1(conn, msg)
        elif key == "40_1":
            _handle_40_1(conn, msg)
        elif key == "36_1":
            _handle_36_1(conn, msg)
        elif key == "15_4":
            _handle_15_4(conn, msg)
        elif key == "18_1":
            _handle_18_1(conn, msg)
        elif key == "20_2":
            _handle_20_2(conn, msg)
        elif key == "37_2":
            _handle_37_2(conn, msg)
        elif key == "3_1":
            _handle_3_1(conn, msg)
        elif key == "11_46":
            _handle_11_46(conn, msg)
        elif key == "11_45":                       # children_num_c2s
            m = _new_s2c(11, 45)
            m.num = len(PD.all_children())
            _send_msg(conn, 11, 45, m)
        elif key in EMPTY_LIST_REPLY:
            # 明確回「空清單」：客戶端會 ipairs 巢狀清單，空清單最安全
            m = _new_s2c(s_id, m_id)
            if m is None:
                log(f"  (無 s2c 對照，略過 {key})")
            else:
                # 清掉所有 repeated 欄位（含巢狀），確保客戶端看到的是空清單而非半殘元素
                for f in m.DESCRIPTOR.fields:
                    if getattr(f, "is_repeated", False):
                        try:
                            getattr(m, f.name).clear()
                        except Exception:
                            pass
                _fill_required(m)
                log(f"  -> 空清單回應（{key} {cname}）；repeated 欄位已清空")
                _send_msg(conn, s_id, m_id, m)
        elif cname == "children_all_c2s" or (cname or "").startswith("children_all"):
            _handle_children_all(conn, s_id, m_id)
        elif key in NO_REPLY:
            pass
        elif key in REPLY_ONCE:
            # 每個連線只回一次，避免客戶端 handler 自我重送造成無限迴圈
            if key not in _replied_once:
                _replied_once.add(key)
                if not _generic_reply(conn, s_id, m_id, cname, msg):
                    log(f"  (無 s2c 對照，略過 {key})")
            # 之後的重送一律靜默丟棄
        else:
            if not _generic_reply(conn, s_id, m_id, cname, msg):
                log(f"  (無 s2c 對照，略過 {key})")
    except Exception as _e:
        import traceback as _tb
        log(f"  ⚠ handler 例外 {key}: {type(_e).__name__}: {_e}")
        for _ln in _tb.format_exc().splitlines()[-14:]:
            log(f"      {_ln}")





def handle(conn, addr):
    log(f"CONNECT from {addr}")
    try:
        conn.settimeout(10)
        first = conn.recv(4096)
        if not first:
            return
        head = first[:4]
        if head.startswith(b"POST") or head.startswith(b"GET ") or head.startswith(b"HEAD"):
            http_loop(conn, first)
        else:
            first_bytes[0] = first
            game_loop(conn, addr)
    except Exception as e:
        # 印完整 traceback：只印 str(e) 會漏掉關鍵資訊
        # （實際踩過：`處理錯誤: sign_records` 看不出是哪一行、什麼型別）
        import traceback as _tb
        log(f"處理錯誤: {type(e).__name__}: {e}")
        for _line in _tb.format_exc().splitlines()[-12:]:
            log(f"    {_line}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", PORT))
srv.listen(16)
log(f"統一 mock 伺服器啟動: 0.0.0.0:{PORT} (HTTP + 遊戲服 TCP) host_for_client={HOST_FOR_CLIENT}")
while True:
    c, a = srv.accept()
    threading.Thread(target=handle, args=(c, a), daemon=True).start()

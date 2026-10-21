# 核心：利希特 — 離線伺服器（Offline Server）

把《核心：利希特》變成**可以離線單機遊玩**的伺服器模擬專案。
遊戲本體完全保持原廠，**不改任何遊戲程式碼** —— 缺的只是「伺服器回應」，本專案負責扮演那個伺服器。

> ## 🚫 職責邊界（請先讀）
>
> **本專案 = 服務端路線：只模擬伺服器回應，不做客戶端補丁。**
>
> 凡屬**客戶端自身缺陷**的問題（客戶端 Lua／C# 的 nil 安全性、UI 時序、配置表欄位無資料等），
> 本專案**不作處理**，僅在 `docs\知识库_合并版.md` 記錄根因與證據，供「客戶端補丁路線」參考。
> 目前屬此類的問題：**啟動白塊**、**檔案無法解鎖**、**瞳的 2 條突破語音**。
>
> 紅線：**禁止推送 `dynamicBg`（屬性 624）** —— 兩次嘗試分別導致主界面全黑／卡死。

> ## 🗓️ 最後除錯：**2026-10-22**（凌晨，實機驗證）
>
> 本輪修復 **作戰進度全解鎖、共鳴/招募解鎖、活動系統可用、編隊 8 槽位解鎖、
> 編隊可加人與保存、頭像/頭像框全部解鎖並可更換、基建核心面板**。
> 詳細證據鏈見 `docs\知识库_合并版.md` §0.5.10 ~ §0.5.13。

```
┌──────────────┐   HTTP 9001（登入服）    ┌─────────────────────┐
│  遊戲客戶端   │ ◄──────────────────────► │  server/            │
│ （原廠 APK）  │   TCP  9001（遊戲服）    │  mock_game_server.py│
│              │                          └─────────────────────┘
│              │   HTTP 8080（CDN 資源）  ┌─────────────────────┐
│              │ ◄──────────────────────► │  cdn/server2.js     │
└──────────────┘                          └─────────────────────┘
```

---

## 快速開始（三步）

### 步驟 0：放入執行環境（讓它變「免安裝」）

從 [Releases](https://github.com/CI404/core-licht-server/releases) 下載兩個附件並解壓到專案根目錄：

| 附件 | 解壓後位置 |
|---|---|
| `runtime-python.zip`（12.8 MB） | `python\python.exe` |
| `runtime-node.zip`（33.4 MB） | `node\node.exe` |

> 沒有這兩個資料夾也能跑，但你得自己安裝 Python（含 `protobuf`）與 Node.js。

### 步驟 1：告訴伺服器「用哪個 IP」

雙擊 `scripts\2-顯示本機IP.bat`，它會列出你電腦的區網 IP。

| 你要用在哪裡 | `config\server.json` 的 `host` 要填 |
|---|---|
| MuMu / 雷電模擬器 | `10.0.2.2`（**不用改**） |
| 真機（與電腦同一個 Wi-Fi） | 你電腦的區網 IP，例如 `192.168.1.100` |

> 也可以直接在 `2-顯示本機IP.bat` 裡輸入 IP，它會幫你寫進設定檔。

### 步驟 2：啟動伺服器

雙擊 **`scripts\1-啟動伺服器.bat`**

會開啟兩個視窗（**不要關掉**）：
- `遊戲服 (Python)` → 監聽 9001
- `CDN 資源服 (Node)` → 監聽 8080

它會先自動檢查環境，有問題會提示。

### 步驟 3：把伺服器位址寫進裝置

```
scripts\3-產生UrlList.bat      ← 產生 output\UrlList_Android.txt
scripts\4-部署到設備.bat        ← 用 adb 推到裝置並清除快取
```

完成後啟動遊戲即可。

---

## 目錄結構

```
licht-offline-server\
├── 1-安裝說明.txt              先讀這個（第一次使用）
├── README.md                   本檔
├── config.py                   設定載入模組（給 Python 用）
├── gen_urllist.py              UrlList 產生器
│
├── config\
│   └── server.json             ★ 唯一需要手動修改的檔案
│
├── scripts\
│   ├── 1-啟動伺服器.bat         啟動遊戲服 + CDN
│   ├── 2-顯示本機IP.bat         查 IP，可順便寫進設定
│   ├── 3-產生UrlList.bat        產生 UrlList_Android.txt
│   ├── 4-部署到設備.bat         adb 推到裝置 + pm clear
│   └── 6-停止伺服器.bat         停止兩個服務
│
├── server\
│   ├── mock_game_server.py     遊戲服 TCP + HTTP 登入服（同一埠）
│   ├── player_data.py          玩家資料產生器（全部取自配置表）
│   └── lichter_wire.py         TCP 協定編解碼（XOR + protobuf）
│
├── cdn\
│   ├── server2.js              CDN 資源伺服器
│   └── cdnroot\                伺服器清單 + 公告（可自訂）
│
├── data\
│   ├── decoded\                365 個遊戲配置表（數值唯一來源）
│   └── proto\                  64 個協定描述 + msgmap + playerattrs
│
├── python\                    內嵌 Python 3.12.14 + protobuf 7.36.2（來自 Release 附件）
├── node\                      內嵌 Node.js v24.21.0（來自 Release 附件）
├── output\                     UrlList 產出位置
├── runtime\                    日誌（mock-server.log / cdn-requests.log / tcp-capture.jsonl）
├── docs\
│   ├── 知识库_合并版.md         ★★ 唯一權威入口（接手前先讀這份，含最新 §0.5 交接）
│   │                              §0.5.3 助理點瞳 bug（9 次失敗嘗試）
│   │                              §0.5.5 啟動白塊（客戶端缺陷）
│   │                              §0.5.6 映像功能（含禁止推送 dynamicBg 紅線）
│   ├── 交接文件-2026-10-10-第二輪.md   環境、六個致命坑、診斷流程
│   ├── 安裝指南.md
│   ├── 新設備部署.md
│   ├── 已完成修復清單.md        本專案修過哪些 bug、證據在哪
│   └── 專案全景與交接.md
│
└── atlas\                      ★ 適格體圖鑑（獨立分支，與伺服器無依賴）
    ├── README.md               分支說明（含開發方向警告）
    ├── docs\適格體圖鑑-編號對照.md
    ├── data\角色資源清單.json   263 筆權威清單
    └── tools\                  匯出／盤點工具
```

> **`atlas\` 是獨立分支**：主題為「角色 ↔ 資源對應關係」，
> 可單獨使用、單獨分享，不影響伺服器運作。詳見 `atlas\README.md`。

---

## 需求

| 項目 | 說明 |
|---|---|
| 作業系統 | Windows 10 / 11（x64） |
| Python / Node | **不需要安裝** —— 從 [Releases](https://github.com/CI404/core-licht-server/releases) 下載附件解壓即可（12.8 + 33.4 MB） |
| 遊戲本體 | 自備原廠 APK + OBB（`com.tw99.no23.an`） |
| OBB 解包資源 | CDN 需要 `obb_main` / `obb_patch` 路徑（見下方） |

### ⚠️ 關於 OBB

CDN 伺服器會從**已解包的原廠 OBB 資源**讀取檔案（約 3.2 GB）。
設定檔 `config\server.json` 的這兩個欄位必須指向真實存在的目錄：

```json
"obb_main":  "obb/main/assets",
"obb_patch": "obb/patch/assets"
```

取得方式：把 `main.138.com.tw99.no23.an.obb` 與 `patch.138.com.tw99.no23.an.obb`
解開（obb 就是 zip）到本專案的 `obb\main\assets` 與 `obb\patch\assets`，
或在設定檔裡改成你自己的路徑（支援相對與絕對路徑）。

### 💡 不想把自己的路徑寫進 repo？用本機覆寫檔

在 `config\` 下建一個 **`server.local.json`**（已列入 `.gitignore`，不會被提交），
只寫要覆寫的欄位即可：

```json
{
  "obb_main": "D:/my-obb/main/assets",
  "obb_patch": "D:/my-obb/patch/assets"
}
```

優先順序：**環境變數 `LICHT_*` > `server.local.json` > `server.json` > 內建預設**

> 這個機制是給「fork 後想保留自己路徑」或「不想讓 `git status` 一直顯示設定檔被改」的人用的。

---

## 目前狀態

### ✅ 已完成（伺服器端）

- 登入 → 選區 → 選角 → 進主界面 **全鏈路打通**
- 玩家等級 100 / 精神力 140 / 113 個適格體 / 328 個皮膚（**全部由配置表推導**）
- 主界面、個人訊息、適格體列表、GM 指令面板（177 條）可正常使用
- 劇情完成狀態、英雄清單、簽到資料
- **作戰**：章節全解鎖（進度 6-10）、468 副本滿星通關
- **共鳴 / 招募**：76 個卡池全部可用
- **活動系統**：40 條活動全部開啟（含「精神溫養」等可領取活動）
- **編隊**：8 個隊員槽位全解鎖、可加人／換人／保存
- **頭像 / 頭像框**：204 頭像 + 16 框全部解鎖，更換即時生效
- **空島基建**：6 個核心（中樞／貿易／調度／通訊／榮譽／合成）

### ✅ 近期修復（2026-10-11，皆經實機驗證）

| 問題 | 根因 | 修法 |
|---|---|---|
| 時裝「穿戴」無反應 | `children_use_skin_s2c` 的 `code`/`id`/`skin_id` 皆 required，通用回應器只填 `code` | `_handle_11_20()` 原樣帶回 `id`/`skin_id` |
| 突破語音上鎖（314 條） | `awake_times=0`／`fetter_break=0`，客戶端類型 5/6/7 判定失敗 | 取 `children_awake` 真實上限（=4）、`fetter_break=1` |
| 好感度顯示畸形 | `favor_lvl=5` 但 `favor=0` 不自洽 | `favor` 取該等級 `range_max` |
| **助理界面（齒輪）白屏** | `p_children.type` 全為 `1`，但助理需 `CardTypeIndex.Hero`(=7) | **僅 `init_hero` 那張卡設 `7`**，其餘維持 `1`（同時滿足適格體） |
| 助理設定界面卡死 | `2_27` 的 `repeated list` 未寫入 ⇒ 客戶端 `pairs(nil)` 崩 | 新增 `_handle_2_27()` |
| 活動面板崩潰 | `52_12` 在 `EMPTY_LIST_REPLY`：`clear()` 後 `_fill_required()` 又補假元素 | 新增 `_handle_52_12()`（52 條真實任務） |
| 看板娘無法儲存 | `children_set_assistant_s2c` 沒有 `code` 欄位（誤填會拋例外） | 新增 `_handle_11_7()`，含以 `skin_id` 反查角色 id |
| **「映像」只有「元」可選** | `2_27` 原本送**空清單** ⇒ 客戶端只顯示 `unlock_type==default` 的背景 | `_handle_2_27()` 改送**全部背景 id**（`DataTable_back_ground` = `[1, 2]`）；新增 `_handle_2_23()` |

### ✅ 近期修復（2026-10-12，皆經實機驗證）

| 問題 | 根因 | 修法 |
|---|---|---|
| **助理界面點「瞳」縮圖 → 大圖預覽顯示厄莉希**（立繪部分） | `35_1` 送出的是**瞳的英雄**（`DataTable_hero`：`hero.id=1001` → 8 個 `children_id` = `100000~100007`，全是瞳），但 `form_list` 的 `skin_list`／`use_skin`／`lvl` 卻查 `hid`(=1001) ⇒ **配上了厄莉希的皮膚**（資料不自洽） | `_SKIN_SRC = PD.default_hero_children_id()`（= `100000` 瞳-強襲）⇒ `f.lvl`／`f.use_skin`／`f.skin_list` 一律改用瞳。**已實機確認立繪恢復正常** |

> **除錯關鍵**：先前 6 輪都以為 bug 在「儲存鏈路」，實則在**預覽的解析路徑**。
> 使用者糾正：「大圖保存到主界面一直是正常的，不正常的是助理界面的點擊大圖預覽。」
> 反匯編 `CardAssistCardSubView` proto 13（行 1359-1377）證實：
> `cardInfo = GetCardInfoById(curSelectId)`，若 `is_hero==1` 則換成
> `HeroModel:GetAssistCloneHeroCardInfo()`，立繪取 `cardInfo.roleImg`。

### ✅ 近期修復（2026-10-22，皆經實機驗證）

> **本輪方法論**：凡是 `notify` / `info` 型協議走「通用回應器」時，客戶端會拿到一堆
> **假 id** → 查配置表得 `nil` → 整塊功能失效（顯示未解鎖／空白／崩潰）。
> 把它換成 `DataTable_*` 裡的**真實配置資料**，功能就通了。

| 問題 | 根因（附證據） | 修法 | 驗證 |
|---|---|---|---|
| **作戰進度永遠卡在 0-1、章節不解鎖、編隊槽位顯示「通關 IN-1 後解鎖」** | `17_1 dup_info` 的 `p_role_dup.task` **完全沒填**。客戶端 `DungeonModel.On_17_1`（反匯編）：`dungeonInfo[v.dup_id] = n`，其中 `n` = `v.task` 裡 `v==1` 的**任務完成數**；`star` 只進 `dungeonServerStarInfo`，**不參與進度判定**。⇒ `n=0` ⇒ 進度不推進（以前只改 `star` 怎麼改都無效） | `_push_dup_info()` 每個副本補 `task = [{k=1..3, v=1}]`（3 星 = 3 任務完成）⇒ `dungeonInfo=3` | ✅ **作戰全解鎖（6-10）**；回應 5527B → **13951B** |
| **共鳴（招募）顯示 `NotActive 暫未連線`、點擊無反應** | `12_1 recruit_pool_s2c` 走通用回應器 ⇒ 只回**一個假卡池**（37B）⇒ 共鳴界面沒有可用卡池。<br>（已先排除 `open_func_id=16`：`open_limit={}`、`24_1` 已送 85 功能含 16 —— **不是功能解鎖問題**） | 新增 `_handle_12_1()`：送 `DataTable_recruit_pool` **全部 76 個卡池** | ✅ **共鳴解鎖、正常顯示卡池** |
| **各類限時活動不出現** | `30_1 open_act_info_s2c` 走通用回應器 ⇒ 只回一個假 `act_id`（12B） | 新增 `_handle_30_1()`：送 `DataTable_open_act` **全部 40 條活動**（`open_time=0`、`close_time=2100-01-01`） | ✅ **「精神溫養 SPIRIT SUPPLY」自動彈出並可領取（+30 精神力 ×2）** |
| **編隊只有 3 個槽位可用、4~8 全 `LOCKED`** | `player_data.player_resources()` 把屬性 **619 `slots_num`** 填成 `spell_slots(lv)`（=3，法術槽位）。但 `PlayerDefine` 屬性映射表（反匯編：`LOADI 5 619` + `LOADK 7 "slots_num"`）證實 619 = `slots_num`，而 `TeamMainView` 用法是 `for i = 1, Player.slots_num` ⇒ 是**編隊隊員槽位數**。`DataTable_config['team_slots']` = 8 槽（1~3 免費、4~8 需通關 `20105/20101/20002/20003/20008`） | 新增 `team_slot_unlocks()` / `team_slots_num()`；`put("slots_num", team_slots_num())` ⇒ **8** | ✅ **8 槽全解鎖** |
| **編隊點「確定」無反應** | 兩個坑：<br>① `15_4` 只要送「帶成員的隊伍」，客戶端 `CompareToTempTeam` 就索引 `nil` 崩潰；<br>② `_fill_required()` 對 **repeated message** 欄位會**自動補一個元素** ⇒ 空清單被它塞進「假隊伍」⇒ 同樣崩 | `_handle_15_4()` 永遠回**空 `children_team`**（客戶端走 `InitTeamData` 安全分支自動建 4 隊）；且該分支**禁止呼叫 `_fill_required()`**。<br>`_handle_15_2()` 的 `result=0` 必須放在 `_fill_required()` **之後**（否則被覆蓋成 1 ⇒ 彈「編隊失敗」） | ✅ **可加人、可保存、不報錯** |
| **頭像框更換後不生效** | `On_41_3`（處理 `headshots_change_frame_s2c`）把回應交給 `InitMainViewInfo(msg)`，它讀 `entry/head/id/frame_id`；但該協議 proto **只有 `id`** ⇒ `frame_id=nil` ⇒ 框不生效 | 新增 `41_1/41_2/41_3/41_4/41_5` 全套；換頭像/換框後**主動重推完整的 `41_1`**（含 `frame_id`）；`player_data` 加 `_CURRENT_HEADSHOT` 狀態 | ✅ **更換頭像框已生效**；頭像 204 + 框 16 全解鎖 |
| **基建核心面板缺項** | `31_32` 走通用回應器 ⇒ body=11B（一個假元素，`sys_id` 查不到 `DataTable_core`） | `_handle_31_32()`：送 6 個核心（`sys_id`=`DataTable_core._key`，`lvl`=`core_lvl` 最大等級） | ✅ body 11B → **72B** |

#### 🔴 本輪最嚴重的踩坑（務必記住）

**`_fill_required()` 會給 `repeated message` 欄位自動補一個元素。**

```python
if f.message_type is not None and getattr(f, "is_repeated", False):
    sub_required = [g for g in f.message_type.fields if getattr(g, "is_required", False)]
    if not sub_required:
        continue
    if len(getattr(msg, f.name)) == 0:
        elem = getattr(msg, f.name).add()      # ★★★ 空清單被塞進一個「最小合法元素」
        _fill_required(elem, depth + 1)
```

`15_4.children_team` 正是 repeated message ⇒ 明明想送**空清單**，卻被塞進
一個「假隊伍」⇒ 客戶端崩潰 ⇒ 點「確定」無反應。

**⇒ 判斷規則：先問「這個 repeated 欄位空著是不是合法語意？」
* 是（如「沒有隊伍」「沒有加成」）⇒ **禁止呼叫 `_fill_required()`**
* 否（客戶端會 nil 迭代崩潰，如 `lottery_pool_s2c`）⇒ 才需要補

### ✅ 新功能

- **GM 指令 `#pass_all_dup`（通關全部副本）** —— 新增 `17_1` 推送（468 副本），登入時一併送出
- **助理清單 `11_23`** —— 106 角色 × 各自皮膚 = 322 筆

### ⚠️ 已知未解

| 問題 | 說明 |
|---|---|
| **啟動後主界面「白塊」** | **每次啟動必現**（非首次才有）。中間內容區全白，頂欄／底部導航正常。<br>根因：`PVPMatchPickView.InitPlayerInfo` 讀空的 `PVPMatchModel.enemyTeam.enemy_lvl` ⇒ `CONCAT` 崩 ⇒ 資源預載中斷。<br>**屬純客戶端缺陷**（原廠伺服器下同樣會崩），**本專案職責為服務端、不打客戶端補丁**。<br>**臨時解法：點「適格體」→ 點左上角「主頁」返回**。<br>詳見 `docs\知识库_合并版.md` §0.5.5 |
| 助理界面點「瞳」顯示厄莉希 | 🟡 **立繪已修復（2026-10-12）、名字仍未修**。<br>**名字**來源（反匯編確認）：`CardAssistCardSubView` proto 13 `RefreshSkinBtn(cardInfo.sys_id)` → proto 14 `GetSyschildrenByKey(sys_id).name`，而 `cardInfo` = `HeroModel:GetAssistCloneHeroCardInfo()`（我方 `35_1` 的英雄）⇒ `sys_id=1001` 查到厄莉希。<br>**但 `h.sys_id` 改 `100000` ⇒ 助理界面白屏**（實驗 8c）⇒ 該欄位不可改。<br>瞳是 **6 位角色代碼**（`100000~100007` + `9100001~9100007`），其皮膚資源為 `e01001_*`（39 筆），與厄莉希的 `1001xx`（4 筆）**無交集**，故非美術混淆。<br>**已嘗試 11 種修法**，詳見 §0.5.3（含「已推翻的錯誤結論」與「勿再重試清單」） |
| 設定「映像」後主界面不切換 | 需在 `2_2 role_info_s2c` 推送 `dynamicBg` 字串屬性；但**兩次推送嘗試分別導致主界面全黑／卡死** ⇒ 列為紅線，**禁止推送**。<br>現狀：可看到並選擇兩張映像，但存後不切換（**不破壞遊戲**）。詳見 §0.5.6 |
| 檔案（適格體檔案）無法解鎖 | 客戶端讀 `children_doc.remember`，但 94 筆資料中 **0 筆**填此欄位（配置表層面無資料）⇒ 伺服器端無法修 |
| 瞳的 2 條突破語音仍鎖 | `limit=[[7,9999,N]]`，`9999` 不存在於任何表；`GetHeroInfoBySysId` 需 `cardType` 而 `p_hero` 無此欄位 |
| GM 資訊欄首次不顯示 | 純客戶端 UI 時序問題，第二次進入即正常，**不影響功能** |
| ~~副本界面進度條仍顯示 0~~ | ✅ **已修復（2026-10-22）**：`17_1` 的 `p_role_dup.task` 未填是根因，補 `task` 後作戰進度正常前進到 6-10 |
| **編隊保存後重進會被重置**（2026-10-22 新增） | `15_4` 只能回**空清單**，否則客戶端必崩。三次嘗試回顯（自造成員／客戶端自存成員+原始 `event_id`／再補 `friend_assist` 14 欄位+`up_flag`+`_fill_required`）**全部崩潰** ⇒ 客戶端對 `p_children_team` 有反匯編描述檔沒列出的隱藏必填子結構。原始伺服器已關，**無真實 s2c 可對照** ⇒ 本路線硬邊界。<br>現狀：可加人／可保存／不報錯，但返回主界面再進會重置 |
| **強制新手引導無法關閉**（2026-10-22 新增） | 引導會隨功能解鎖推進（共鳴鎖著時要求點共鳴、解鎖後改要求點作戰→協同預演 ⇒ 是主線新手教程在按進度前進）。**已排查全部服務端槓桿均無效**：`2_9 noob_stage=29`、`2_2` 112 個屬性（無 guide 欄位）、`24_1` 85 功能全開、GM `#pass_all_scenario`。<br>⇒ 引導進度存在**客戶端本地存檔**，服務端無協議欄位可關 ⇒ 需走「客戶端補丁路線」 |
| **`item config not found` 936 條**（2026-10-22 新增） | 有 **312 個 id** 被當 item 發送但 `DataTable_item` 裡不存在，其中含皮膚 id（`1000001~1000003`、`1001` 等）。來源待查（疑似 `11_1` 的 `skin_list` 被客戶端當 item 查）。目前只刷日誌，未見功能性阻塞 |
| 真機改 OBB | 需要 root；無 root 請見 `docs\新設備部署.md` 的替代做法 |

> **接手前請先讀 `docs\知识库_合并版.md`**（唯一權威入口）——
> 內含六個致命坑、協定規格、診斷流程、失敗嘗試清單（避免重蹈），
> 以及每項修復的**確切證據**（logcat 堆疊／位元組碼行號／配置表來源）。

---

### 🚫 紅線（實測得出，**改動前務必確認**）

以下欄位一旦改動會**直接導致界面白屏或功能損壞**，皆為實機驗證：

| 欄位 | 不可改為 | 後果 |
|---|---|---|
| `p_hero.id`（`35_1`） | `100000` | 助理界面**白屏** |
| `p_hero.sys_id`（`35_1`） | `100000` | 助理界面**白屏** |
| `p_hero.children_id`（`35_1`） | `100000` | 助理界面**白屏** |
| `35_1` 整個英雄清單 | 清空（`list=0`） | 助理界面**白屏** |
| `p_children.type` | 全部 `1` → 助理白屏；全部 `7` → 適格體清單變空 | **兩難**，只能 `init_hero` 設 `7` |
| `2_2 role_info_s2c` 的 `dynamicBg` | 推送字串屬性 | 主界面**全黑／卡死** |
| `p_hero.form_list` 的皮膚 | 用 `hid`（厄莉希）的皮膚 | 助理預覽**立繪顯示厄莉希**（已修為瞳） |

**兩難說明**：厄莉希的 `type` 無法同時滿足兩個界面 ——
適格體要 `1`（`GetCardBagDic(cardList, Common)`）、助理要 `7`（`GetHeroInfoBySysId`）。
現行取捨：**保助理不白屏**（代價：厄莉希不出現在適格體列表，但仍持有可用）。

---

## 授權與免責

本專案**只包含伺服器模擬程式與設定檔**，不含任何遊戲程式、美術、音訊或資料檔案
（`data\decoded` 為逆向分析所得的配置表，僅供個人研究）。
遊戲本體與其所有內容版權屬於原權利人。請勿用於商業用途或散布遊戲資源。

---

## 貢獻者

**CI404** —— 離線伺服器逆向分析與實作

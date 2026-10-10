# 適格體圖鑑（Character Atlas）— 獨立分支

> **這個目錄是一個獨立分支**，主題是「**角色 ↔ 資源的對應關係**」。
>
> 它與主專案（mock 伺服器）**沒有依賴關係**，可以單獨使用、單獨分享。
> 主專案負責「讓遊戲跑起來」，這裡負責「把遊戲的資料與資源整理出來」。

---

## 0. ⚠️ 先讀這段：開發方向警告

本目錄的所有產出，**僅限於「遊戲外」的資料瀏覽與查詢**。

`E:\核心：利希特\licht-offline\README.md:10-21` 明確記載前幾任 AI 的結論：

| 項目 | 說明 |
|---|---|
| ❌ **錯誤路線** | 用 Vite + TypeScript + PixiJS **重寫遊戲界面** |
| ❌ **為何錯誤** | ① 遊戲**本體是完整的**（UI 預製體 **2247 個**、美術、邏輯、劇情全在客戶端），重寫等於把做好的東西再手工做一遍<br>② 重寫的 UI **永遠無法與原版一致**<br>③ 浪費大量成本去「複製」，而非「改造」 |
| ✅ **正確路線** | **直接修補原版客戶端**，讓它在沒有伺服器的情況下運行 |

> **一句話**：不是「重做遊戲」，是「**把聯網遊戲改成單機遊戲**」。

**本目錄的定位**：資料層參考。若要做網頁圖鑑、資料查詢工具，這裡的對照表可直接用；
但**不要**藉此重寫任何遊戲內既有界面。

---

## 1. 核心成果（一句話）

> **適格體界面上方顯示的編號 = `DataTable_children_skin.head_new`**
> **= `DataTable_spine.id`**
> **→ `DataTable_spine.path` = 模型目錄名**
> **→ `assets\spine\<path>\` 內含 `.skel`（骨骼）+ `.atlas`（圖集）+ `.png`（貼圖）**

### 實測數據

| 項目 | 數量 | 比例 |
|---|---|---|
| `DataTable_spine` 總行數 | **263** | — |
| `path` 在磁碟上找得到 | **257** | **97.7%** |
| 含 `.skel` 骨骼檔 | **257** | 97.7% |
| 能對到角色名 | **204** | **77.6%** |
| 有 `click` 互動動作 | **109** | 41.4% |

---

## 2. 目錄結構

```
atlas\
├── README.md                      本檔
├── docs\
│   └── 適格體圖鑑-編號對照.md      ★ 完整技術文件（機制、映射鏈、欄位說明）
├── data\
│   ├── 角色資源清單.json           ★ 263 筆權威清單（261 KB）
│   └── card_pic對照.json           61 筆 card_pic 對照（旁支）
└── tools\
    ├── export_char_manifest.py     ★ 主要工具：由 DataTable_spine 匯出清單
    ├── enum_atlas.py               掃描 card_pic_*.png（旁支）
    └── inventory_assets.py         資產盤點（統計各目錄規模）
```

---

## 3. 快速使用

```cmd
cd /d "D:\核心：GM服务 打包项目\atlas\tools"

:: 1) 匯出完整角色資源清單（263 筆 → JSON）
..\..\python\python.exe export_char_manifest.py --json ..\data\角色資源清單.json

:: 2) 資產盤點（看各目錄有多少東西）
..\..\python\python.exe inventory_assets.py

:: 3) 掃描 card_pic 立繪（旁支，61 個）
..\..\python\python.exe enum_atlas.py --json ..\data\card_pic對照.json
```

**預設掃描的資源目錄**（可用 `--root` 覆寫）：

```
E:\核心：利希特\licht-offline
```

---

## 4. 資料來源（外部依賴）

| 來源 | 路徑 | 說明 |
|---|---|---|
| 配置表 | `licht-offline\raw\decoded\DataTable_spine.rows.json` | ★ 263 行，權威對照表 |
| 配置表 | `licht-offline\raw\decoded\DataTable_children_skin.rows.json` | 333 個皮膚 |
| 配置表 | `licht-offline\raw\decoded\DataTable_children.rows.json` | 113 個角色 |
| 模型資源 | `licht-offline\assets\spine\<path>\` | 782 目錄 / 426 套含骨骼 |
| 卡面小圖 | `licht-offline\assets\spine\*\card_pic_*.png` | 61 個 |
| Live2D | `licht-offline\assets\live2d\` | 12 個模型 |
| 音效 | `licht-offline\assets\audio\` | 8,324 檔 / 3.6 GB |

⚠️ 這些是**外部路徑**，不在本專案內。工具用 `--root` 參數指定。

---

## 5. 關鍵欄位速查（`DataTable_spine`）

| 欄位 | 說明 |
|---|---|
| `id` | ★ == `children_skin.head_new`（6 位，界面顯示的編號） |
| `path` | ★ 模型目錄名，對應 `assets\spine\<path>\` |
| `path2` | 第二模型（少數角色） |
| `click` | ★ 點擊互動動作，如 `[["normal",0],["angry",0],["happy",0],...]` |
| `click2` | 第二組點擊動作 |
| `para` / `para1`~`para4` | 立繪排版 `[x, y, ?, scale]` |
| `scenario_para` | 劇情演出排版 |
| `enter_voice_id` | 登場語音 id |
| `is_show_main_bg` | 是否可作主界面背景 |
| `need_connect_anim` | 是否需拼接分部件（`_body` + `_bg1` + `_bg2`） |

---

## 6. 兩套編號系統（別混淆）

```
children_skin.id         10 位  1430050001   資料庫主鍵
children_skin.head_new    6 位  300501       ★ 界面顯示的編號 == DataTable_spine.id
children_skin.skin_pic    5 位  10101        → card_<skin_pic>.png
children_skin.model       9~10位 201001111   戰鬥模型 id（另一套系統）
```

---

## 7. 待確認事項

| # | 問題 | 已知 |
|---|---|---|
| 1 | 56 行對不到 `head_new` 的是什麼？ | 多為 `n000xx`（NPC）、`war_order_*`（戰場）、未實裝 |
| 2 | `s_l41003_j1_00` 為何不存在？ | OBB 內就沒有這個 bundle |
| 3 | `model`（9~10 位）與 `head_new`（6 位）的關係？ | 見 `DataTable_model`，另一套系統 |
| 4 | `need_connect_anim` 的拼接規則？ | 需讀客戶端 Lua |

---

## 8. 與主專案的關係

| 項目 | 主專案（mock 伺服器） | 本分支（圖鑑） |
|---|---|---|
| 目的 | 讓原版客戶端能離線運行 | 整理角色 ↔ 資源對應 |
| 依賴 | 不需要本分支 | 需要 `licht-offline` 的配置表與資源 |
| 共用 | `server\player_data.py`（讀配置表） | 同上 |
| 產出 | 可遊玩的遊戲 | JSON 清單 + 文件 |

**兩者可獨立使用，互不影響。**

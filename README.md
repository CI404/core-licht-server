# 核心：利希特 — 離線伺服器（Offline Server）

把《核心：利希特》變成**可以離線單機遊玩**的伺服器模擬專案。
遊戲本體完全保持原廠，**不改任何遊戲程式碼** —— 缺的只是「伺服器回應」，本專案負責扮演那個伺服器。

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
└── docs\
    ├── 交接文件-2026-10-10-第二輪.md   ★ 接手前必讀（環境、六個致命坑、診斷流程）
    ├── 安裝指南.md
    ├── 新設備部署.md
    └── 已完成修復清單.md        ★ 本專案修過哪些 bug、證據在哪
```

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

### ⚠️ 已知未解

| 問題 | 說明 |
|---|---|
| 首次登入 GM 資訊欄不顯示 | 純客戶端 UI 時序問題，第二次進入即正常，**不影響功能** |
| 助理界面（齒輪）白屏 | `CardAssistView` 的 C# 物件失效，尚未定位到確切行 |
| 真機改 OBB | 需要 root；無 root 請見 `docs\新設備部署.md` 的替代做法 |

詳見 `docs\已完成修復清單.md`。

---

## 授權與免責

本專案**只包含伺服器模擬程式與設定檔**，不含任何遊戲程式、美術、音訊或資料檔案
（`data\decoded` 為逆向分析所得的配置表，僅供個人研究）。
遊戲本體與其所有內容版權屬於原權利人。請勿用於商業用途或散布遊戲資源。

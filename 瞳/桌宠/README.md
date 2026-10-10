# 瞳 · 桌宠（Hitomi Desktop Pet）

把《核芯：利希特》的角色 **瞳** 放到 Windows 桌面上。

---

## 快速開始

**雙擊 `build\瞳-桌宠.exe`** 即可。不需要安裝任何東西。

（單一檔案，已內嵌立繪素材，約 4.1 MB）

---

## 操作方式

| 動作 | 效果 |
|---|---|
| **左鍵拖曳** | 移動桌宠 |
| **滾輪上/下** | 放大 / 縮小 |
| **雙擊** | 還原預設大小並移到畫面中央 |
| **右鍵** | 開啟選單（見下） |

### 右鍵選單

```
切換立繪     ├─ 瞳 · 形態 A      (card_e01001_00)
             ├─ 瞳 · 形態 B      (card_e01001_01)
             ├─ 瞳 · 形態 C      (card_e01001_02)
             └─ 瞳 · 特殊形態(f01) (card_e01001_f01)
大小         ├─ 300 / 450 / 600 / 720 / 900 / 1200 / 1600 px
呼吸動畫     開 / 關
永遠置頂     開 / 關
開機自動啟動  開 / 關（寫入 HKCU\...\Run）
移到畫面中央
關於
離開
```

**系統匣圖示**（工作列右下角）：雙擊可隱藏／顯示桌宠。

---

## 技術說明

| 項目 | 內容 |
|---|---|
| 語言 | C# 5（.NET Framework 4.8，Windows 內建） |
| UI | WinForms + GDI+ |
| 透明 | `TransparencyKey`（Magenta 鍵控色）+ PNG alpha |
| 編譯器 | `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`（Windows 自帶） |
| 依賴 | **零**（只用系統組件） |

### 為什麼不用 Python / Electron

本機環境沒有 GUI 函式庫：

```
嵌入式 Python 3.12：無 tkinter、無 PIL、無 pip、無 PyInstaller
Node：只有 puppeteer-core
```

而 Windows 自帶 `csc.exe` → **C# 是唯一能產出「零依賴單一 exe」的路徑**。

---

## 檔案結構

```
桌宠\
├── 瞳-桌宠.exe            ← 產出（可直接雙擊）
├── 编译.bat               重新編譯
├── README.md              本檔
├── src\
│   ├── HitomiPet.cs       主程式（單檔，約 700 行）
│   ├── app.manifest       DPI 感知宣告
│   └── app.ico            程式圖示（6 種尺寸）
├── assets\
│   ├── 立绘\              原始立繪（2048×2048，4 張）
│   ├── 头像\              頭像（headicon / card_pic）
│   └── _embed\            裁切+縮放後（900px，嵌入用，4 張）
└── build\
    ├── 瞳-桌宠.exe        編譯產出
    └── 桌宠.log           執行記錄（診斷用）
```

---

## 素材來源

| 素材 | 原始路徑 |
|---|---|
| 立繪 | `licht-offline\assets\ui-themepark\Zero\UI\Texture\CardTexture\card_e01001_*\` |
| 頭像 | `...\CardHeadIcon\headicon_1010*\`、`...\CardPicIcon\card_pic_1010*\` |
| 角色設定 | `raw\decoded\DataTable_children_doc.rows.json` |

**尺寸**：立繪原始 2048×2048 → 裁掉透明邊 → 縮到 900px → 嵌入 exe（4 張共 3.91 MB）

### ⚠️ 版權

所有素材版權歸原開發／發行方所有。本程式僅供**技術研究與紀念**，非官方作品，不提供任何遊戲資源下載。

---

## 重新編譯

```cmd
雙擊 编译.bat
```

需要：
- Windows 內建的 `csc.exe`（`%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\`）
- 素材已放在 `assets\_embed\`（4 張 PNG）

編譯參數（見 `编译.bat`）：

```
/nologo /target:winexe /platform:anycpu /optimize+
/out:build\瞳-桌宠.exe
/win32icon:src\app.ico
/win32manifest:src\app.manifest
/resource:assets\_embed\card_e01001_00.png,HitomiPet.assets.card_e01001_00.png
/resource:assets\_embed\card_e01001_01.png,HitomiPet.assets.card_e01001_01.png
/resource:assets\_embed\card_e01001_02.png,HitomiPet.assets.card_e01001_02.png
/resource:assets\_embed\card_e01001_f01.png,HitomiPet.assets.card_e01001_f01.png
/resource:assets\头像\headicon_10101.png,HitomiPet.assets.headicon_10101.png
src\HitomiPet.cs
```

> `/resource:檔案,資源名` 的第二個參數是**邏輯資源名**，程式用 `GetManifestResourceStream` 讀取時必須完全一致。

---

## 已知問題

| # | 問題 | 說明 |
|---|---|---|
| 1 | **高 DPI 螢幕上尺寸偏小** | 系統 150% 縮放時，設定的虛擬像素會被系統再縮一次。程式已用 `GetDeviceCaps(LOGPIXELSX)` 做補償，但 `SetProcessDPIAware()` 在此環境無效（manifest 被忽略）。**可用滾輪自行放大**。 |
| 2 | 記憶體約 67 MB | 4 張 900px PNG 解碼後佔用。可接受。 |
| 3 | 桌面寵物與全螢幕遊戲衝突 | 遊戲全螢幕時桌宠會被蓋住（正常）。建議關閉「永遠置頂」或使用無邊框視窗模式。 |

---

## 除錯

程式會在 exe 旁寫 `桌宠.log`：

```
00:00:30.049  === 啟動 ===
00:00:30.051  AppDir = ...
00:00:30.093  載入形態數 = 4
00:00:30.094    pose='card_e01001_00' size=664x900
...
00:00:30.217  OnPaint 首次: _scaled=310x420  ClientSize=...
```

若顯示「找不到立繪」，檢查：
1. `assets\_embed\*.png` 是否存在（或 exe 是否含嵌入資源）
2. 用 `dumpbin` 或重新編譯確認 `/resource` 參數生效

---

## 後續可加功能

- [ ] 點擊反應（切換表情／播放語音，需 FMOD bank 提取）
- [ ] 多角色（其他適格體）
- [ ] 定時問候（依時間顯示不同台詞）
- [ ] 拖到邊緣自動隱藏
- [ ] 桌面遊走（隨機走動動畫）
- [ ] Spine 骨骼動畫（需 Spine 3.8.97 runtime）

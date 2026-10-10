// ============================================================================
//  瞳 · 桌宠（Hitomi Desktop Pet）
//  ---------------------------------------------------------------------------
//  用途：把《核芯：利希特》的角色「瞳」放到 Windows 桌面上。
//  技術：C# + WinForms + GDI+（.NET Framework 4.8，Windows 內建，無需安裝）
//  編譯：編譯.bat（呼叫 Windows 內建的 csc.exe）
//
//  ★ 功能
//    · 無邊框透明視窗，只顯示角色本體（PNG alpha 通道）
//    · 滑鼠左鍵拖曳移動
//    · 滾輪縮放 / 雙擊還原
//    · 右鍵選單：切換立繪、調整大小、置頂、開機自動啟動、離開
//    · 呼吸 + 漂浮動畫（計時器驅動）
//    · 系統匣圖示（工作列右下角）
//
//  ★ 素材來源
//    遊戲《核芯：利希特》v0.1.38 客戶端（已解包）
//    立繪：ui-themepark/Zero/UI/Texture/CardTexture/card_e01001_*.png（2048×2048）
//    所有素材版權歸原開發／發行方所有，本程式僅供技術研究與紀念。
// ============================================================================
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

namespace HitomiPet
{
    /// <summary>單一形態（立繪 + 顯示名稱）</summary>
    internal class Pose
    {
        public string Key;          // 檔名（不含副檔名）
        public string Label;        // 選單顯示名稱
        public Image Source;        // 原始大圖
        public Pose(string k, string l) { Key = k; Label = l; }
    }

    internal class PetForm : Form
    {
        // ---- 資料 ----
        private readonly List<Pose> _poses = new List<Pose>();
        private int _poseIndex = 0;
        private Image _scaled;              // 目前縮放後的圖
        private int _displayH = 720;        // 顯示高度（像素；考量高 DPI 螢幕，預設加大）
        private const int MIN_H = 150;
        private const int MAX_H = 2000;

        // ---- 動畫 ----
        private readonly Timer _anim = new Timer();
        private double _phase = 0;
        private bool _animated = true;

        // ---- 拖曳 ----
        private bool _dragging = false;
        private Point _dragOffset;

        // ---- 系統匣 ----
        private NotifyIcon _tray;
        private ContextMenuStrip _menu;

        // ---- 隨機 ----
        private readonly Random _rnd = new Random();

        // ---- DPI ----
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern IntPtr GetDC(IntPtr hWnd);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);
        [System.Runtime.InteropServices.DllImport("gdi32.dll")]
        private static extern int GetDeviceCaps(IntPtr hdc, int nIndex);

        private double _dpiScale = 1.0;

        /// <summary>取得螢幕水平 DPI 相對 96 的倍率</summary>
        private void DetectDpi()
        {
            try
            {
                IntPtr hdc = GetDC(IntPtr.Zero);
                if (hdc != IntPtr.Zero)
                {
                    int dpi = GetDeviceCaps(hdc, 88);   // LOGPIXELSX
                    ReleaseDC(IntPtr.Zero, hdc);
                    if (dpi > 0) _dpiScale = dpi / 96.0;
                }
            }
            catch { }
            Log("系統 DPI 倍率 = " + _dpiScale.ToString("0.###"));
        }

        /// <summary>把「想要的像素尺寸」換算成 WinForms 設定值</summary>
        private int Px(double want)
        {
            return (int)Math.Round(want / _dpiScale);
        }

        public PetForm()
        {
            DetectDpi();                        // 先量 DPI，後面所有尺寸都要換算

            // 視窗基本設定
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.Magenta;          // 透明鍵控色（會被 TransparencyKey 去除）
            TransparencyKey = Color.Magenta;
            TopMost = true;
            Text = "瞳 · 桌宠";
            DoubleBuffered = true;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer |
                     ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);

            Log("=== 啟動 ===");
            Log("AppDir = " + AppDir);
            Log("DPI 虛擬化 AutoScaleMode=" + AutoScaleMode);

            LoadPoses();
            Log("載入形態數 = " + _poses.Count);
            foreach (Pose p in _poses)
                Log("  pose='" + p.Key + "' size=" + (p.Source != null ?
                    (p.Source.Width + "x" + p.Source.Height) : "null"));

            BuildMenu();
            BuildTray();
            Log("選單/系統匣 完成");

            _anim.Interval = 50;                // 20 FPS
            _anim.Tick += AnimTick;
            _anim.Start();

            // 預設位置：畫面中央偏下（第一次啟動最容易看到）
            var wa = Screen.PrimaryScreen.WorkingArea;
            Log("螢幕 WorkingArea = " + wa.ToString());
            Location = new Point(wa.Left + (wa.Width - Px(400)) / 2,
                                 wa.Top + (wa.Height - Px(600)) / 2);

            ApplyPose(0);
            Log("ApplyPose(0) 完成  Location=" + Location.ToString() + " Size=" + Size.ToString());
        }

        // ---- 診斷記錄（寫在 exe 旁，失敗則忽略）----
        private static void Log(string msg)
        {
            try
            {
                File.AppendAllText(Path.Combine(AppDir, "桌宠.log"),
                    DateTime.Now.ToString("HH:mm:ss.fff") + "  " + msg + Environment.NewLine,
                    System.Text.Encoding.UTF8);
            }
            catch { }
        }

        // ====================================================================
        //  載入素材
        // --------------------------------------------------------------------
        //  兩種模式：
        //    ① 單一 exe（推薦）：立繪已嵌入資源，直接從組件讀取
        //    ② 資料夾模式：exe 與 assets\ 放在一起
        //  先試 ①，失敗才試 ②。
        // ====================================================================
        private void LoadPoses()
        {
            // 立繪標籤（依檔名給中文名稱）
            var labels = new Dictionary<string, string>();
            labels["card_e01001_00"] = "瞳 · 形態 A";
            labels["card_e01001_01"] = "瞳 · 形態 B";
            labels["card_e01001_02"] = "瞳 · 形態 C";
            labels["card_e01001_f01"] = "瞳 · 特殊形態 (f01)";

            var found = new Dictionary<string, Image>();

            // ---- ① 嵌入資源 ----
            Assembly asm = Assembly.GetExecutingAssembly();
            string[] resNames = asm.GetManifestResourceNames();
            Log("  嵌入資源數 = " + resNames.Length);
            foreach (string rn in resNames)
            {
                if (!rn.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
                {
                    Log("    [略] 非 png: " + rn);
                    continue;
                }
                // 資源名格式：HitomiPet.assets.<key>.png
                // 去掉結尾的 ".png" 後，取最後一段
                string noExt = rn.Substring(0, rn.Length - 4);
                int j = noExt.LastIndexOf('.');
                string key = (j >= 0) ? noExt.Substring(j + 1) : noExt;
                try
                {
                    using (Stream s = asm.GetManifestResourceStream(rn))
                    {
                        if (s == null)
                        {
                            Log("    [失敗] 取不到流: " + rn);
                            continue;
                        }
                        var ms = new MemoryStream();
                        s.CopyTo(ms);
                        ms.Position = 0;
                        found[key] = Image.FromStream(ms);
                        Log("    [OK] key=" + key + "  size=" +
                            found[key].Width + "x" + found[key].Height);
                    }
                }
                catch (Exception ex)
                {
                    Log("    [例外] " + rn + " : " + ex.Message);
                }
            }

            // ---- ② 外部資料夾 ----
            if (found.Count == 0)
            {
                foreach (string sub in new string[] { "_embed", "立绘" })
                {
                    string dir = Path.Combine(AppDir, "assets", sub);
                    if (!Directory.Exists(dir)) continue;
                    foreach (string f in Directory.GetFiles(dir, "*.png"))
                    {
                        string key = Path.GetFileNameWithoutExtension(f);
                        if (found.ContainsKey(key)) continue;
                        try
                        {
                            using (var fs = new FileStream(f, FileMode.Open, FileAccess.Read))
                                found[key] = Image.FromStream(fs);
                        }
                        catch { }
                    }
                    if (found.Count > 0) break;
                }
            }

            // ---- 組裝（依檔名排序，順序固定）----
            var keys = new List<string>(found.Keys);
            keys.Sort(StringComparer.OrdinalIgnoreCase);
            foreach (string key in keys)
            {
                // 頭像不用作形態（只給系統匣圖示）
                if (key.StartsWith("headicon", StringComparison.OrdinalIgnoreCase)) continue;

                string label;
                if (!labels.TryGetValue(key, out label)) label = key;
                Pose p = new Pose(key, label);
                p.Source = found[key];
                _poses.Add(p);
            }

            if (_poses.Count == 0)
            {
                // 沒有素材時給一個提示方塊，避免完全空白
                var bmp = new Bitmap(300, 300);
                using (var g = Graphics.FromImage(bmp))
                {
                    g.Clear(Color.Transparent);
                    using (var br = new SolidBrush(Color.FromArgb(230, 40, 44, 52)))
                        g.FillEllipse(br, 10, 10, 280, 280);
                    using (var f = new Font("Microsoft JhengHei UI", 14))
                    using (var br = new SolidBrush(Color.White))
                    {
                        var sf = new StringFormat();
                        sf.Alignment = StringAlignment.Center;
                        sf.LineAlignment = StringAlignment.Center;
                        g.DrawString("找不到立繪\n請確認 exe 旁有 assets\\_embed\\*.png", f, br,
                                     new RectangleF(0, 0, 300, 300), sf);
                    }
                }
                Pose p = new Pose("placeholder", "（無素材）");
                p.Source = bmp;
                _poses.Add(p);
            }
        }

        private static string AppDir
        {
            get
            {
                // 單檔 exe：組件所在目錄
                string d = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                if (string.IsNullOrEmpty(d)) d = Environment.CurrentDirectory;
                return d;
            }
        }

        // ====================================================================
        //  縮放（高品質，含 alpha）
        // ====================================================================
        private void RebuildScaled()
        {
            if (_poses.Count == 0) return;
            Image src = _poses[_poseIndex].Source;
            if (src == null) return;

            double ratio = (double)_displayH / src.Height;
            int w = Math.Max(1, (int)Math.Round(src.Width * ratio));
            int h = Math.Max(1, _displayH);

            var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                g.SmoothingMode = SmoothingMode.HighQuality;
                g.CompositingQuality = CompositingQuality.HighQuality;
                // ImageAttributes：避免邊緣出現黑邊
                using (var ia = new ImageAttributes())
                {
                    ia.SetWrapMode(WrapMode.TileFlipXY);
                    g.DrawImage(src, new Rectangle(0, 0, w, h),
                                0, 0, src.Width, src.Height, GraphicsUnit.Pixel, ia);
                }
            }

            Image old = _scaled;
            _scaled = bmp;
            if (old != null) old.Dispose();
        }

        // ====================================================================
        //  套用形態
        // ====================================================================
        private void ApplyPose(int index)
        {
            if (index < 0 || index >= _poses.Count) return;
            _poseIndex = index;
            RebuildScaled();
            ApplyWindowSize();
            Invalidate();
        }

        private void ApplyWindowSize()
        {
            if (_scaled == null) return;
            int padding = 24;                 // 留邊給動畫位移
            Size = new Size(Px(_scaled.Width + padding * 2),
                            Px(_scaled.Height + padding * 2));
            Invalidate();
        }

        // ====================================================================
        //  繪製
        // ====================================================================
        protected override void OnPaint(PaintEventArgs e)
        {
            if (_scaled == null)
            {
                Log("OnPaint: _scaled == null");
                base.OnPaint(e);
                return;
            }

            if (!_paintLogged)
            {
                _paintLogged = true;
                Log("OnPaint 首次: _scaled=" + _scaled.Width + "x" + _scaled.Height +
                    "  ClientSize=" + ClientSize.ToString() +
                    "  Visible=" + Visible + "  Location=" + Location.ToString());
            }

            Graphics g = e.Graphics;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.SmoothingMode = SmoothingMode.HighQuality;

            // 呼吸 / 漂浮：垂直位移 + 輕微縮放
            double floatY = 0, scale = 1.0;
            if (_animated)
            {
                floatY = Math.Sin(_phase) * 10.0;              // ±10 px 上下
                scale = 1.0 + Math.Sin(_phase * 2.0) * 0.012;  // ±1.2% 呼吸
            }

            int w = (int)Math.Round(_scaled.Width * scale);
            int h = (int)Math.Round(_scaled.Height * scale);
            int x = (ClientSize.Width - w) / 2;
            int y = (ClientSize.Height - h) / 2 + (int)floatY;

            g.DrawImage(_scaled, new Rectangle(x, y, w, h));
        }

        private bool _paintLogged = false;

        private void AnimTick(object sender, EventArgs e)
        {
            if (!_animated) return;
            _phase += 0.045;
            if (_phase > Math.PI * 2) _phase -= Math.PI * 2;
            Invalidate();
        }

        // ====================================================================
        //  滑鼠互動
        // ====================================================================
        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button == MouseButtons.Left)
            {
                _dragging = true;
                _dragOffset = new Point(e.X, e.Y);
                Cursor = Cursors.SizeAll;
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            if (_dragging)
            {
                Point p = PointToScreen(new Point(e.X, e.Y));
                Location = new Point(p.X - _dragOffset.X, p.Y - _dragOffset.Y);
            }
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            base.OnMouseUp(e);
            if (e.Button == MouseButtons.Left)
            {
                _dragging = false;
                Cursor = Cursors.Default;
            }
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            base.OnMouseWheel(e);
            int step = (e.Delta > 0) ? 60 : -60;
            _displayH = Math.Max(MIN_H, Math.Min(MAX_H, _displayH + step));
            RebuildScaled();
            ApplyWindowSize();
            Invalidate();
        }

        protected override void OnDoubleClick(EventArgs e)
        {
            base.OnDoubleClick(e);
            // 雙擊：還原預設大小並回到中央偏下
            _displayH = 720;
            RebuildScaled();
            ApplyWindowSize();
            var wa = Screen.PrimaryScreen.WorkingArea;
            Location = new Point(wa.Right - Width - 60, wa.Bottom - Height - 20);
            Invalidate();
        }

        // ====================================================================
        //  右鍵選單
        // ====================================================================
        private void BuildMenu()
        {
            _menu = new ContextMenuStrip();
            _menu.ShowImageMargin = false;

            // -- 切換立繪 --
            var miPose = new ToolStripMenuItem("切換立繪");
            for (int i = 0; i < _poses.Count; i++)
            {
                int idx = i;
                var mi = new ToolStripMenuItem(_poses[i].Label);
                mi.Checked = (i == _poseIndex);
                mi.Click += delegate { ApplyPose(idx); RefreshMenuChecks(); };
                miPose.DropDownItems.Add(mi);
            }
            _menu.Items.Add(miPose);

            // -- 大小 --
            var miSize = new ToolStripMenuItem("大小");
            int[] sizes = new int[] { 300, 450, 600, 720, 900, 1200, 1600 };
            foreach (int s in sizes)
            {
                int sz = s;
                var mi = new ToolStripMenuItem(sz + " px");
                mi.Click += delegate
                {
                    _displayH = sz;
                    RebuildScaled();
                    ApplyWindowSize();
                    Invalidate();
                };
                miSize.DropDownItems.Add(mi);
            }
            _menu.Items.Add(miSize);

            // -- 動畫開關 --
            var miAnim = new ToolStripMenuItem("呼吸動畫");
            miAnim.Checked = _animated;
            miAnim.Click += delegate
            {
                _animated = !_animated;
                miAnim.Checked = _animated;
                if (!_animated) { _phase = 0; Invalidate(); }
            };
            _menu.Items.Add(miAnim);

            // -- 置頂 --
            var miTop = new ToolStripMenuItem("永遠置頂");
            miTop.Checked = TopMost;
            miTop.Click += delegate
            {
                TopMost = !TopMost;
                miTop.Checked = TopMost;
            };
            _menu.Items.Add(miTop);

            _menu.Items.Add(new ToolStripSeparator());

            // -- 開機自動啟動 --
            var miBoot = new ToolStripMenuItem("開機自動啟動");
            miBoot.Checked = IsAutoStart();
            miBoot.Click += delegate
            {
                bool want = !IsAutoStart();
                if (SetAutoStart(want))
                {
                    miBoot.Checked = want;
                }
                else
                {
                    MessageBox.Show("設定失敗（可能被系統權限阻擋）", "瞳 · 桌宠",
                                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            };
            _menu.Items.Add(miBoot);

            // -- 置中 --
            var miCenter = new ToolStripMenuItem("移到畫面中央");
            miCenter.Click += delegate
            {
                var wa = Screen.PrimaryScreen.WorkingArea;
                Location = new Point((wa.Width - Width) / 2 + wa.Left,
                                     (wa.Height - Height) / 2 + wa.Top);
            };
            _menu.Items.Add(miCenter);

            _menu.Items.Add(new ToolStripSeparator());

            // -- 關於 --
            var miAbout = new ToolStripMenuItem("關於");
            miAbout.Click += delegate
            {
                MessageBox.Show(
                    "瞳 · 桌宠（Hitomi Desktop Pet）\n\n" +
                    "角色：瞳（《核芯：利希特》）\n" +
                    "製造者設定：亞述桐\n\n" +
                    "素材版權歸原開發／發行方所有。\n" +
                    "本程式僅供技術研究與紀念，非官方作品。\n\n" +
                    "操作：左鍵拖曳移動 · 滾輪縮放 · 右鍵選單 · 雙擊還原",
                    "關於", MessageBoxButtons.OK, MessageBoxIcon.Information);
            };
            _menu.Items.Add(miAbout);

            // -- 離開 --
            var miExit = new ToolStripMenuItem("離開");
            miExit.Click += delegate { Close(); };
            _menu.Items.Add(miExit);

            ContextMenuStrip = _menu;
        }

        private void RefreshMenuChecks()
        {
            if (_menu == null || _menu.Items.Count == 0) return;
            var miPose = _menu.Items[0] as ToolStripMenuItem;
            if (miPose == null) return;
            for (int i = 0; i < miPose.DropDownItems.Count; i++)
            {
                var mi = miPose.DropDownItems[i] as ToolStripMenuItem;
                if (mi != null) mi.Checked = (i == _poseIndex);
            }
        }

        // ====================================================================
        //  系統匣
        // ====================================================================
        private void BuildTray()
        {
            _tray = new NotifyIcon();
            _tray.Text = "瞳 · 桌宠";
            _tray.Visible = true;
            _tray.ContextMenuStrip = _menu;

            // 用頭像當圖示（找不到就用預設）
            Icon ico = null;
            try
            {
                string head = Path.Combine(AppDir, "assets", "头像", "headicon_10101.png");
                if (File.Exists(head))
                {
                    using (var bmp = new Bitmap(head))
                    {
                        ico = IconFromBitmap(bmp);
                    }
                }
            }
            catch { }
            if (ico == null) ico = SystemIcons.Application;
            _tray.Icon = ico;

            _tray.DoubleClick += delegate
            {
                Visible = !Visible;
                if (Visible) Activate();
            };
        }

        private static Icon IconFromBitmap(Bitmap src)
        {
            // 縮到 32x32 並轉成 Icon
            using (var bmp = new Bitmap(32, 32, PixelFormat.Format32bppArgb))
            {
                using (var g = Graphics.FromImage(bmp))
                {
                    g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                    g.Clear(Color.Transparent);
                    g.DrawImage(src, new Rectangle(0, 0, 32, 32));
                }
                IntPtr h = bmp.GetHicon();
                return Icon.FromHandle(h);
            }
        }

        // ====================================================================
        //  開機自動啟動（登錄檔 Run）
        // ====================================================================
        private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        private const string RunName = "HitomiDesktopPet";

        private static bool IsAutoStart()
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(RunKey, false))
                {
                    if (k == null) return false;
                    object v = k.GetValue(RunName);
                    return v != null && v.ToString().Length > 0;
                }
            }
            catch { return false; }
        }

        private static bool SetAutoStart(bool on)
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(RunKey, true))
                {
                    if (k == null) return false;
                    if (on)
                    {
                        string exe = Assembly.GetExecutingAssembly().Location;
                        k.SetValue(RunName, "\"" + exe + "\"");
                    }
                    else
                    {
                        if (k.GetValue(RunName) != null) k.DeleteValue(RunName, false);
                    }
                }
                return true;
            }
            catch { return false; }
        }

        // ====================================================================
        //  清理
        // ====================================================================
        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            _anim.Stop();
            if (_tray != null) { _tray.Visible = false; _tray.Dispose(); }
            if (_scaled != null) { _scaled.Dispose(); _scaled = null; }
            foreach (Pose p in _poses)
                if (p.Source != null) p.Source.Dispose();
            base.OnFormClosed(e);
        }
    }

    internal static class Program
    {
        // 讓視窗在 高 DPI 螢幕上不被系統縮放（桌宠需要精確像素）
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        static void Main(string[] args)
        {
            // 只允許一個實例
            bool created;
            using (var mutex = new System.Threading.Mutex(true, "HitomiDesktopPet_SingleInstance", out created))
            {
                if (!created) return;

                try { SetProcessDPIAware(); } catch { }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                try
                {
                    Application.Run(new PetForm());
                }
                catch (Exception ex)
                {
                    try
                    {
                        System.IO.File.AppendAllText(
                            System.IO.Path.Combine(
                                System.IO.Path.GetDirectoryName(
                                    System.Reflection.Assembly.GetExecutingAssembly().Location),
                                "桌宠.log"),
                            "FATAL: " + ex.ToString() + Environment.NewLine,
                            System.Text.Encoding.UTF8);
                    }
                    catch { }
                    MessageBox.Show("啟動失敗：\n" + ex.Message, "瞳 · 桌宠",
                                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
        }
    }
}

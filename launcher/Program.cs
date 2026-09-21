using System.Diagnostics;
using System.Drawing;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Win32;

internal static class Program
{
    private const string AppUrl = "http://127.0.0.1:3000/";

    [STAThread]
    private static void Main(string[] args)
    {
        // 更新执行器模式：必须赶在拿单实例互斥量之前处理 ——
        // 此时旧启动器可能还没退干净，走正常分支会被互斥量挡下并弹「已在运行中」。
        // 这一路也不需要 WinForms，故不调 ApplicationConfiguration.Initialize()。
        if (UpdateApplier.IsApplyMode(args))
        {
            Environment.Exit(UpdateApplier.Run(args));
            return;
        }

        ApplicationConfiguration.Initialize();
        using var mutex = new Mutex(true, "InfiniteCanvasLauncher.SingleInstance", out var isOwner);
        if (!isOwner)
        {
            MessageBox.Show("Infinite Canvas 已经在运行中。", LauncherHost.Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var root = ResolveProjectRoot();
        CleanupStaleAppliers(root);
        CleanupStaleDownloads(root);
        using var host = new LauncherHost(root, AppUrl);
        Application.Run(host.Form);
    }

    /// <summary>
    /// 清理上次更新留下的执行器副本。它跑完无法自删（自己就是正在运行的映像），
    /// 所以交给下一次启动的启动器收尾。正在跑的那份删不掉，属正常。
    /// </summary>
    private static void CleanupStaleAppliers(string root)
    {
        try
        {
            var dataDir = Path.Combine(root, "data");
            if (!Directory.Exists(dataDir)) return;
            foreach (var f in Directory.EnumerateFiles(dataDir, "_apply_update_*.exe"))
            {
                try { File.Delete(f); } catch { }
            }
        }
        catch { /* 清理失败不影响启动 */ }
    }

    /// <summary>
    /// 清理更新下载目录里的垃圾：
    /// · `*.part` 是没下完的半成品，任何时刻都是垃圾（单实例互斥量保证同时只有一个启动器在下载）
    /// · `*.zip` 正常会被执行器删掉；删不掉（被占用 / 中途崩溃）就会残留 111 MB
    /// ⚠️ **不能无条件删 `*.zip`** —— 用户可能刚点完更新又立刻重开启动器，此时执行器
    ///    正在读那个包，删掉会让更新中途失败。所以只清 2 天前的。
    /// </summary>
    private static void CleanupStaleDownloads(string root)
    {
        try
        {
            var dir = Path.Combine(root, "data", "update_download");
            if (!Directory.Exists(dir)) return;

            foreach (var f in Directory.EnumerateFiles(dir, "*.part"))
            {
                try { File.Delete(f); } catch { }
            }

            var cutoff = DateTime.UtcNow.AddDays(-2);
            foreach (var f in Directory.EnumerateFiles(dir, "*.zip"))
            {
                try
                {
                    if (File.GetLastWriteTimeUtc(f) < cutoff) File.Delete(f);
                }
                catch { }
            }
        }
        catch { /* 清理失败不影响启动 */ }
    }

    /// <summary>
    /// 是否已有执行器在跑。用户点完「立即更新」后启动器会在 1.5s 内退出，
    /// 若他马上重开启动器再点一次，就会起第二个执行器同时往同一个目录解包 →
    /// 安装目录会被写坏。这里用「正在运行的映像文件删不掉」当判据拦下来。
    /// </summary>
    internal static bool IsUpdateInProgress(string root)
    {
        try
        {
            var dataDir = Path.Combine(root, "data");
            if (!Directory.Exists(dataDir)) return false;
            foreach (var f in Directory.EnumerateFiles(dataDir, "_apply_update_*.exe"))
            {
                try { File.Delete(f); }
                catch { return true; }
            }
        }
        catch { }
        return false;
    }

    private static string ResolveProjectRoot()
    {
        var executableDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        if (File.Exists(Path.Combine(executableDir, "main.py"))) return executableDir;
        var parent = Directory.GetParent(executableDir)?.FullName;
        if (parent is not null && File.Exists(Path.Combine(parent, "main.py"))) return parent;
        return executableDir;
    }
}

internal sealed class LauncherForm : Form
{
    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int x;
        public int y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MINMAXINFO
    {
        public POINT ptReserved;
        public POINT ptMaxSize;
        public POINT ptMaxPosition;
        public POINT ptMinTrackSize;
        public POINT ptMaxTrackSize;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int left;
        public int top;
        public int right;
        public int bottom;
    }

    // ⚠️ 旧的 SetWindowRgn / CreateRoundRectRgn / DeleteObject 三个 P/Invoke 已随「1 位掩码圆角」
    // 一起移除（它天生无抗锯齿）。圆角改由网页 CSS border-radius + DWM 逐像素合成实现，
    // 见 EnablePerPixelCorners()。需要回退时不要只把这三行加回来，还要把 OnHandleCreated /
    // UpdateFormRegion / WebView2 背景色 / 注入的 CSS 一并改回。

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

    [StructLayout(LayoutKind.Sequential)]
    private struct MARGINS
    {
        public int cxLeftWidth;
        public int cxRightWidth;
        public int cyTopHeight;
        public int cyBottomHeight;
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref MARGINS margins);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    private const int GWL_EXSTYLE = -20;
    private const int WS_EX_LAYERED = 0x00080000;
    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOZORDER = 0x0004;
    private const uint SWP_NOACTIVATE = 0x0010;
    private const uint SWP_FRAMECHANGED = 0x0020;

    /// <summary>
    /// CSS 里圆角的像素值。真正的圆角由网页绘制（border-radius 自带抗锯齿），
    /// 再靠 DWM 的逐像素合成透出桌面 —— 详见 <see cref="EnablePerPixelCorners"/>。
    /// </summary>
    public const string CornerRadiusCss = "18px";

    // ⚠️ 这里曾有 `public const string CornerInsetCss = "2px";`（右/下内缩量）。
    // 2026-09-21 改为**由网页按 devicePixelRatio 自己算**（见注入脚本里的
    // __launcherApplyCornerInset）：压平只发生在非整数 DPI 缩放，而修好它需要的
    // 「设备像素」内缩量基本恒定（实测 2 设备px 在 1.25 / 1.665 下都最优），
    // 所以 CSS 值必须是 2/dpr，不能写死 2px —— 固定值在 125% 缩放下偏小（弧仍被
    // 压平）、在 150% 缩放下偏大（把本来正常的四角反而弄坏：极差 0 → 2）。
    // 详见注入样式里的 ③ 段与 tools/__probe.py 的实测表。

    /// <summary>
    /// 圆角状态变化时回调（true = 圆角，false = 最大化贴边）。
    /// 由宿主在创建 WebView2 之后挂上，这样窗体不必直接依赖 WebView2 字段。
    /// </summary>
    public Action<bool>? CornerRadiusChanged { get; set; }

    /// <summary>当前网页里生效的圆角状态（最大化时贴边、圆角归零）。</summary>
    private bool cornersRounded = true;

    private const int WM_GETMINMAXINFO = 0x24;
    private const int WM_SIZING = 0x0214;
    private const int WS_MINIMIZEBOX = 0x20000;
    private const int WS_MAXIMIZEBOX = 0x10000;

    // ⚠️ 这里曾有 `private const int CS_DROPSHADOW = 0x20000;` 并在 CreateParams 里
    // `cp.ClassStyle |= CS_DROPSHADOW;`。2026-09-21 老板反馈「启动器有三个角出现了奇怪的边」，
    // 逐像素取证（读老板截图 output/__corners_2x2.png）结论：
    //   · 四角圆弧本身**完全对称且平滑**（左/右内缩量 18→17→12→11→9→7→6→5→4→2→2→1→1→0）；
    //   · 但**右边和底边各多出一条 4~6px 浅灰渐变带**（亮度 12→45→156→193→229→247→255），
    //     **左边和上边完全没有**。
    // 这正是 CS_DROPSHADOW 的行为 —— 它画的是**右下偏移投影**（"shadow is drawn on the right
    // and bottom edges"），不是 DWM 那种四边对称阴影。偏移投影是**按窗口矩形**投的，
    // 网页画的圆角它不知道，于是圆角外侧的透明区被方形阴影填上 → 右上 / 左下 / 右下
    // 三个角出现"方形浅色角"（老板圈出的正好是这三个角，左上角干净）。
    // ⇒ 圆角要平滑，**窗口就不能有 CS_DROPSHADOW**。改回圆角方案时也不要把它加回来。
    // 若日后想要阴影，只能用「窗口比内容大一圈 + 网页 box-shadow 自绘」（阴影跟随 border-radius），
    // 不能再依赖 CS_DROPSHADOW。

    private const int WMSZ_LEFT = 1;
    private const int WMSZ_RIGHT = 2;
    private const int WMSZ_TOP = 3;
    private const int WMSZ_TOPLEFT = 4;
    private const int WMSZ_TOPRIGHT = 5;
    private const int WMSZ_BOTTOM = 6;
    private const int WMSZ_BOTTOMLEFT = 7;
    private const int WMSZ_BOTTOMRIGHT = 8;

    private const double TargetAspectRatio = 16.0 / 9.0;

    /// <summary>
    /// ⚠️ 这里曾经用 <c>SetWindowRgn(CreateRoundRectRgn(...))</c> 做圆角，老板反馈「依旧有锯齿」——
    /// 因为 Region 是 <b>1 位掩码</b>，圆弧上的像素只能整块取舍，<b>天生没有抗锯齿</b>，
    /// 把半径按 DPI 放大也只是让锯齿颗粒变小，消不掉。
    ///
    /// 现在改成「逐像素透明」方案：<see cref="EnablePerPixelCorners"/> 把 DWM 玻璃框扩到整窗，
    /// 网页用 CSS <c>border-radius</c> 画圆角（浏览器自带抗锯齿，边缘是部分透明像素），
    /// 由 DWM 按 alpha 通道逐像素合成 → 圆角平滑。<b>不再调用 SetWindowRgn。</b>
    /// </summary>
    public LauncherForm()
    {
        FormBorderStyle = FormBorderStyle.None;
        DoubleBuffered = true;
        SetStyle(ControlStyles.ResizeRedraw | ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint, true);
    }

    protected override CreateParams CreateParams
    {
        get
        {
            var cp = base.CreateParams;
            cp.Style |= WS_MINIMIZEBOX | WS_MAXIMIZEBOX;
            // ⚠️ 不要加 `cp.ClassStyle |= CS_DROPSHADOW;` —— 它的右下偏移投影会盖在
            // 网页圆角外侧的透明区上，形成方形浅色角。原因详见上面 CS_DROPSHADOW 的注释。
            return cp;
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        try
        {
            // Windows 11 rounded corners (DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2)
            int preference = 2;
            DwmSetWindowAttribute(Handle, 33, ref preference, sizeof(int));
        }
        catch {}
        EnablePerPixelCorners();
        UpdateFormRegion();
    }

    /// <summary>
    /// 开启「逐像素透明」合成，让网页画的圆角能带抗锯齿。
    ///
    /// 原理：<c>DwmExtendFrameIntoClientArea</c> 传 -1 边距 = 告诉 DWM「整个客户区都当玻璃处理」，
    /// 于是 DWM 不再按矩形裁剪窗口，而是按客户区的 alpha 通道逐像素合成。配合
    /// WebView2 的 <c>DefaultBackgroundColor = Transparent</c>，网页里 CSS border-radius
    /// 产生的**部分透明边缘像素**会被原样保留 → 圆角是平滑的，不再是 1 位掩码的台阶。
    ///
    /// ⚠️ 副作用与配套要求（改这里前务必一起看）：
    ///   1. 客户区里「纯黑」的像素会被 DWM 判为完全透明 → 窗体的 BackColor 必须是黑，
    ///      否则 WebView2 透明区域透不出桌面（圆角就白设了）。
    ///   2. 网页的 html/body 背景必须透明，背景色只能画在带 border-radius 的根容器上。
    ///   3. 与 WS_EX_LAYERED 互斥：分层窗口用 LWA_ALPHA 整窗统一透明度，会盖掉逐像素 alpha。
    ///      所以淡入结束后必须 <see cref="EnsurePerPixelAlpha"/> 把该样式摘掉。
    /// </summary>
    private void EnablePerPixelCorners()
    {
        try
        {
            var margins = new MARGINS
            {
                cxLeftWidth = -1,
                cxRightWidth = -1,
                cyTopHeight = -1,
                cyBottomHeight = -1,
            };
            DwmExtendFrameIntoClientArea(Handle, ref margins);
        }
        catch {}
        // 黑色 = 透明色（见上面第 1 条）
        BackColor = Color.Black;
    }

    /// <summary>
    /// 摘掉 WS_EX_LAYERED。WinForms 的 Form.Opacity 淡入靠的是分层窗口，
    /// 而 LWA_ALPHA 是「整窗一个透明度」，会让 DWM 的逐像素 alpha 失效（圆角又变回方块）。
    /// 淡入收尾（Opacity 到 1.0）后调用一次，之后圆角才真正平滑。
    /// </summary>
    public void EnsurePerPixelAlpha()
    {
        if (!IsHandleCreated) return;
        try
        {
            int exStyle = GetWindowLong(Handle, GWL_EXSTYLE);
            if ((exStyle & WS_EX_LAYERED) != 0)
            {
                SetWindowLong(Handle, GWL_EXSTYLE, exStyle & ~WS_EX_LAYERED);
                SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
            }
        }
        catch {}
    }

    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        UpdateFormRegion();
    }

    /// <summary>
    /// 圆角改由网页绘制，这里只负责「最大化时贴边、还原时回到圆角」——
    /// 通过改 CSS 变量 <c>--launcher-corner</c> 实现（注入的样式表里用的是
    /// <c>border-radius: var(--launcher-corner, 18px) !important</c>）。
    /// </summary>
    public void UpdateFormRegion()
    {
        bool rounded = WindowState != FormWindowState.Maximized;
        if (rounded == cornersRounded) return;
        cornersRounded = rounded;
        try { CornerRadiusChanged?.Invoke(rounded); } catch {}
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == WM_GETMINMAXINFO)
        {
            var screen = Screen.FromHandle(Handle);
            var workingArea = screen.WorkingArea;
            var minMax = Marshal.PtrToStructure<MINMAXINFO>(m.LParam);
            minMax.ptMaxPosition.x = Math.Abs(screen.Bounds.Left - workingArea.Left);
            minMax.ptMaxPosition.y = Math.Abs(screen.Bounds.Top - workingArea.Top);
            minMax.ptMaxSize.x = workingArea.Width;
            minMax.ptMaxSize.y = workingArea.Height;
            minMax.ptMinTrackSize.x = 960;
            minMax.ptMinTrackSize.y = 540;
            Marshal.StructureToPtr(minMax, m.LParam, true);
        }
        else if (m.Msg == WM_SIZING)
        {
            // 锁定 16:9 比例拖拽缩放
            var rect = Marshal.PtrToStructure<RECT>(m.LParam);
            int width = rect.right - rect.left;
            int height = rect.bottom - rect.top;
            int edge = m.WParam.ToInt32();

            switch (edge)
            {
                case WMSZ_LEFT:
                case WMSZ_RIGHT:
                    int newH = (int)Math.Round(width / TargetAspectRatio);
                    rect.bottom = rect.top + newH;
                    break;

                case WMSZ_TOP:
                case WMSZ_BOTTOM:
                    int newW = (int)Math.Round(height * TargetAspectRatio);
                    rect.right = rect.left + newW;
                    break;

                case WMSZ_BOTTOMRIGHT:
                case WMSZ_BOTTOMLEFT:
                    int targetHBottom = (int)Math.Round(width / TargetAspectRatio);
                    rect.bottom = rect.top + targetHBottom;
                    break;

                case WMSZ_TOPLEFT:
                case WMSZ_TOPRIGHT:
                    int targetHTop = (int)Math.Round(width / TargetAspectRatio);
                    rect.top = rect.bottom - targetHTop;
                    break;
            }

            Marshal.StructureToPtr(rect, m.LParam, true);
        }
        base.WndProc(ref m);
    }
}

sealed class LauncherHost : IDisposable
{
    public const string Title = "CANVAS · LOCHOU LAUNCHER";
    private readonly string root;
    private readonly string appUrl;
    private readonly LauncherForm form;
    private readonly Icon applicationIcon;
    private readonly WebView2 webView;
    private readonly NotifyIcon tray;
    private readonly string preferencePath;
    private readonly string apiProvidersPath;
        private readonly string apiEnvPath;
        private static readonly HttpClient _pingHttpClient = new HttpClient();
        private Process? server;
    private bool ownsServer;
    private bool forceExit;
    private bool disposed;
    private bool keepRunningInBackground = true;
    private bool launchAtStartup = false;

    [DllImport("user32.dll")]
    private static extern bool ReleaseCapture();

    [DllImport("user32.dll")]
    private static extern IntPtr SendMessage(IntPtr hWnd, int Msg, IntPtr wParam, IntPtr lParam);

    private const int WM_NCLBUTTONDOWN = 0xA1;
    private const int HT_CAPTION = 0x2;

    public Form Form => form;

    public LauncherHost(string projectRoot, string canvasUrl)
    {
        root = projectRoot;
        appUrl = canvasUrl;
        preferencePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "InfiniteCanvasLauncher", "preferences.json");
        apiProvidersPath = Path.Combine(root, "data", "api_providers.json");
        apiEnvPath = Path.Combine(root, "API", ".env");

        applicationIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? (Icon)SystemIcons.Application.Clone();

        var screenArea = Screen.PrimaryScreen?.WorkingArea ?? new Rectangle(0, 0, 1920, 1080);
        int initialWidth = 1920;
        int initialHeight = 1080;

        // 若当前显示器可用区域小于 1920x1080，则按 16:9 比例等比适配工作区
        if (screenArea.Width < 1920 || screenArea.Height < 1080)
        {
            double scale = Math.Min((double)(screenArea.Width - 40) / 1920.0, (double)(screenArea.Height - 40) / 1080.0);
            scale = Math.Max(scale, 0.5);
            initialWidth = (int)Math.Round(1920 * scale);
            initialHeight = (int)Math.Round(1080 * scale);
        }

        form = new LauncherForm
        {
            Text = LauncherHost.Title,
            Width = initialWidth,
            Height = initialHeight,
            MinimumSize = new Size(960, 540),
            StartPosition = FormStartPosition.CenterScreen,
            // ⚠️ BackColor 必须是**纯黑**：启用逐像素透明后（EnablePerPixelCorners），
            // DWM 把客户区里的纯黑像素判为完全透明。若这里填 #090a0f，WebView2 的透明区域
            // （圆角外那几块）就透不出桌面，圆角等于没做。
            BackColor = Color.Black,
            Icon = applicationIcon,
            Opacity = 0.0 // 初始完全透明，等页面渲染就绪后平滑渐显，杜绝白屏/黑屏闪烁
        };

        webView = new WebView2
        {
            Dock = DockStyle.Fill,
            // 透明背景 → WebView2 会把网页的真实 alpha 交给合成器，
            // CSS border-radius 的抗锯齿边缘才能保留（这是圆角不再锯齿的关键一环）。
            DefaultBackgroundColor = Color.Transparent
        };
        form.Controls.Add(webView);
        // 最大化 / 还原时同步网页里的圆角与内缩量（网页侧靠 CSS 变量 --launcher-corner /
        // --launcher-inset 生效）。最大化时必须**同时**把内缩归零，否则右/下会露出 2px 桌面。
        // 最大化 / 还原时同步网页里的圆角。内缩量**不在这里写死** —— 它要按
        // devicePixelRatio 换算成「2 设备px 的 CSS 等值」，所以交给网页侧的
        // __launcherApplyCornerInset() 自己算（见注入脚本）。这里只要改完
        // --launcher-corner 再让它重算一次即可。
        form.CornerRadiusChanged = rounded =>
        {
            try
            {
                webView?.CoreWebView2?.ExecuteScriptAsync(
                    "document.documentElement.style.setProperty('--launcher-corner', '"
                    + (rounded ? LauncherForm.CornerRadiusCss : "0px") + "');"
                    + "if (window.__launcherApplyCornerInset) { window.__launcherApplyCornerInset(); }");
            }
            catch {}
        };
        form.FormClosing += OnFormClosing;
        form.Shown += async (_, _) => await InitializeLauncherAsync();

        tray = new NotifyIcon { Icon = applicationIcon, Text = LauncherHost.Title, Visible = false };
        var menu = new ContextMenuStrip();
        menu.Items.Add("打开启动器面板", null, (_, _) => RestoreWindow());
        menu.Items.Add("在浏览器中打开无限画布", null, (_, _) => OpenInDefaultBrowser(appUrl));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("彻底退出并关闭服务", null, (_, _) => ExitFromTray());
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += (_, _) => RestoreWindow();

        LoadPreferences();
    }

    private async Task InitializeLauncherAsync()
    {
        try
        {
            await webView.EnsureCoreWebView2Async();
            webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            webView.CoreWebView2.Settings.IsStatusBarEnabled = false;

            var windowBridgeScript = @"
(function() {
    function injectGlobalStyles() {
        if (!document.getElementById('launcher-corner-style')) {
            const style = document.createElement('style');
            style.id = 'launcher-corner-style';
            style.textContent = `
                /* ⚠️ 圆角靠「DWM 逐像素合成」实现，所以：
                   ① html/body 必须透明，背景色只能画在带 border-radius 的根容器上，
                      否则圆角外面那几块仍然是不透明的深色 → 看不出圆角；
                   ② 半径走 CSS 变量 --launcher-corner，最大化时由宿主改成 0px 贴边。
                   ③ 🚨 右/下各内缩 --launcher-inset（由 __launcherApplyCornerInset()
                      按 devicePixelRatio 算成 2 设备px 的 CSS 等值）：Chromium 在
                      **非整数 DPI 缩放**下会把贴住视口右/下边缘的圆角弧压平 ——
                      实测（窗口 1161x730 逻辑px）四角「对角透明长度」d 为
                        dsf=1.25  贴边 7/6/6/5（极差 2）→ 内缩 2 设备px 后 7/7/7/7（0）
                        dsf=1.5   贴边 8/8/8/8（极差 0）→ 内缩 2 设备px 后 8/8/9/10（2）
                        dsf=1.665 贴边 9/8/7/6（极差 3）→ 内缩 2 设备px 后 9/9/8/8（1）
                      内缩 2 设备px 是三个 dsf 下的综合最优（最差极差 2，且只有 1.5
                      会退化）；3 设备px 能让 1.665 变 0/0，但会让 1.25/1.5 明显变差。
                      ⚠️ 换裁切机制无效：clip-path:inset(0 round 18px)、mask-image
                      （内联 SVG 圆角矩形 / 四角 radial-gradient）、clip-path:url(#svg)
                      在真实启动器页面上都仍被压平。
                   ④ 🚨 内缩留下的缝用两条**直边补条**补（body::before 补右 /
                      body::after 补底），两端各避开 --launcher-corner。
                      ⚠️ 补条必须是**纯矩形**（加圆角会被压平得更狠），且**相切点一端
                      必须用 linear-gradient 渐显**：2026-09-21 老板反馈「圆角边缘
                      （除左上角）都还存在小尖角」，根因就是补条从相切点突然开始，
                      形状边界从「弧（内缩 N px）」在 1 行内跳到「直边（贴边）」，
                      留下一个 N 设备px 的 90° 台阶（左上角两条边都不内缩、没有补条，
                      所以只有它干净）。渐显后台阶被抹成柔和过渡，肉眼不可见。 */
                html, body {
                    background: transparent !important;
                }
                #root {
                    border-radius: var(--launcher-corner, 18px) !important;
                    overflow: hidden !important;
                    background-color: #090a0f !important;
                    width: calc(100vw - var(--launcher-inset, 0px)) !important;
                    height: calc(100vh - var(--launcher-inset, 0px)) !important;
                }
                /* 补条：竖条补右侧、横条补底部。两端各避开 --launcher-corner，正好接在
                   圆角弧的相切点上；相切点一端用 linear-gradient 渐显（透明 → 不透明），
                   把「弧 → 直边」的硬台阶抹成柔和过渡。
                   ⚠️ 必须用单引号：这里是 C# verbatim 字符串，写双引号会被解成单引号，
                       CSS 声明失效 → 补条整条不生效（这个坑真踩过）。 */
                body::before, body::after {
                    content: '';
                    position: fixed;
                    background-color: #090a0f;
                    pointer-events: none;
                }
                body::before {
                    right: 0;
                    top: calc(var(--launcher-corner, 18px) - var(--launcher-inset, 0px));
                    bottom: calc(var(--launcher-corner, 18px) + var(--launcher-inset, 0px));
                    width: var(--launcher-inset, 0px);
                    background: linear-gradient(to bottom,
                        rgba(9, 10, 15, 0) 0,
                        rgba(9, 10, 15, 1) var(--launcher-inset, 0px));
                }
                body::after {
                    bottom: 0;
                    left: calc(var(--launcher-corner, 18px) - var(--launcher-inset, 0px));
                    right: calc(var(--launcher-corner, 18px) + var(--launcher-inset, 0px));
                    height: var(--launcher-inset, 0px);
                    background: linear-gradient(to right,
                        rgba(9, 10, 15, 0) 0,
                        rgba(9, 10, 15, 1) var(--launcher-inset, 0px));
                }
                *:focus, *:focus-visible, button:focus, button:focus-visible {
                    outline: none !important;
                    box-shadow: none !important;
                }
            `;
            document.head.appendChild(style);
        }

        /* 再把 html/body 的背景压成透明（每次调用都设，幂等）。
           两层保险：
             ① 注入样式表里的 `html, body { background: transparent !important }` 本身就够 ——
                页面自带的内联 `<style>html,body,#root{background-color:#090a0f!important}</style>`
                是个**选择器列表**，对 `html` 元素只有 `html` 这一支生效，特异性同样是 (0,0,1)，
                与注入规则**打平** → 靠**源顺序**决胜。所以注入样式**必须追加在 head 末尾**
                （`document.head.appendChild` / `</head>` 前插入），否则会输给页面的 `<style>`。
                已实测：只注入样式表、完全不跑 JS，`getComputedStyle(html).backgroundColor`
                就是 `rgba(0, 0, 0, 0)`（技能脚本 verify-launcher-corners-web.py）。
             ② 这里再用**行内 + !important** 兜一层（author 层最高优先级），
                这样即使以后页面把自带 `<style>` 挪到注入样式之后、或加了更强的规则，也压得过。
           ⚠️ 注意 `#root` 的 (1,0,0) 那条**不能**压掉 —— 圆角盒的背景必须留它。 */
        document.documentElement.style.setProperty('background-color', 'transparent', 'important');
        if (document.body) {
            document.body.style.setProperty('background-color', 'transparent', 'important');
        }
    }

    /* 把「右/下内缩量」写成 CSS 变量 --launcher-inset。
       🚨 为什么按 devicePixelRatio 算：压平只发生在**非整数 DPI 缩放**下，而且修好它
          需要的「设备像素」内缩量基本恒定（实测 2 设备px 在 1.25 / 1.665 下都是最优）。
          所以内缩量应该用设备px 表达，即 2 / dpr 个 CSS px。
       最大化（--launcher-corner = 0px）时归零，否则右/下会露出 2 设备px 的桌面。
       ⚠️ setProperty 改的是 documentElement.style，而 MutationObserver 只监听
          childList/subtree（不含 attributes），所以不会自激。 */
    function applyCornerInset() {
        const root = document.documentElement;
        // ⚠️ 变量**未设置**时（宿主还没同步过）必须按「有圆角」处理 —— CSS 里的
        // var(--launcher-corner, 18px) 就是这个语义。否则初始状态下不内缩 → 弧被压平。
        const raw = getComputedStyle(root).getPropertyValue('--launcher-corner').trim() || '18px';
        const radius = parseFloat(raw);
        if (isNaN(radius) || radius <= 0) {
            root.style.setProperty('--launcher-inset', '0px');
            return;
        }
        const dpr = window.devicePixelRatio || 1;
        root.style.setProperty('--launcher-inset', (2 / dpr) + 'px');
    }
    window.__launcherApplyCornerInset = applyCornerInset;

    /* ⚠️ setupWindowBridge 会被 MutationObserver 反复调用，这里必须自己加锁，
       否则每次 DOM 变动都会再挂一个 resize 监听。 */
    if (!window.__launcherInsetBound) {
        window.__launcherInsetBound = true;
        window.addEventListener('resize', applyCornerInset);
    }

    function setupWindowBridge() {
        injectGlobalStyles();
        applyCornerInset();

        // 绑定 Header 拖拽与双击最大化
        const header = document.querySelector('header');
        if (header && !header.dataset.launcherDragBound) {
            header.dataset.launcherDragBound = 'true';
            header.style.userSelect = 'none';

            header.addEventListener('mousedown', function(e) {
                if (e.button !== 0) return;
                if (e.target.closest('button, input, select, textarea, a, .cursor-pointer, [role=""button""]')) {
                    return;
                }
                window.chrome?.webview?.postMessage({ type: 'WINDOW_DRAG' });
            });

            header.addEventListener('dblclick', function(e) {
                if (e.target.closest('button, input, select, textarea, a, .cursor-pointer, [role=""button""]')) {
                    return;
                }
                window.chrome?.webview?.postMessage({ type: 'WINDOW_TOGGLE_MAXIMIZE' });
            });
        }

        // 绑定右上角最小化、最大化/还原、关闭按钮
        if (header) {
            const btnGroup = header.querySelector('.border-l') || header.querySelector('div.flex.items-center.gap-1');
            if (btnGroup) {
                const buttons = btnGroup.querySelectorAll('button');
                if (buttons.length >= 3) {
                    const minBtn = buttons[0];
                    const maxBtn = buttons[1];
                    const closeBtn = buttons[2];

                    if (!minBtn.dataset.bound) {
                        minBtn.dataset.bound = 'true';
                        minBtn.setAttribute('title', '最小化');
                        minBtn.addEventListener('click', function(e) {
                            e.preventDefault();
                            e.stopPropagation();
                            window.chrome?.webview?.postMessage({ type: 'WINDOW_MINIMIZE' });
                        });
                    }

                    if (!maxBtn.dataset.bound) {
                        maxBtn.dataset.bound = 'true';
                        maxBtn.setAttribute('title', '最大化 / 还原');
                        maxBtn.addEventListener('click', function(e) {
                            e.preventDefault();
                            e.stopPropagation();
                            window.chrome?.webview?.postMessage({ type: 'WINDOW_TOGGLE_MAXIMIZE' });
                        });
                    }

                    if (!closeBtn.dataset.bound) {
                        closeBtn.dataset.bound = 'true';
                        closeBtn.setAttribute('title', '关闭');
                        closeBtn.addEventListener('click', function(e) {
                            e.preventDefault();
                            e.stopPropagation();
                            window.chrome?.webview?.postMessage({ type: 'WINDOW_CLOSE' });
                        });
                    }
                }
            }
        }

        // 四角与边缘拖拽等比缩放抓手 (Corner Resizing Handles)
        setupResizeHandles();
    }

    function setupResizeHandles() {
        if (document.getElementById('launcher-resize-handles')) return;

        const container = document.createElement('div');
        container.id = 'launcher-resize-handles';
        container.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:999999;';

        const handles = [
            { id: 'tl', edge: 'TOP_LEFT', cursor: 'nwse-resize', style: 'top:0;left:0;width:14px;height:14px;' },
            { id: 'tr', edge: 'TOP_RIGHT', cursor: 'nesw-resize', style: 'top:0;right:0;width:14px;height:14px;' },
            { id: 'bl', edge: 'BOTTOM_LEFT', cursor: 'nesw-resize', style: 'bottom:0;left:0;width:14px;height:14px;' },
            { id: 'br', edge: 'BOTTOM_RIGHT', cursor: 'nwse-resize', style: 'bottom:0;right:0;width:14px;height:14px;' },
            { id: 'b', edge: 'BOTTOM', cursor: 'ns-resize', style: 'bottom:0;left:14px;right:14px;height:6px;' },
            { id: 'r', edge: 'RIGHT', cursor: 'ew-resize', style: 'top:14px;right:0;bottom:14px;width:6px;' },
            { id: 'l', edge: 'LEFT', cursor: 'ew-resize', style: 'top:14px;left:0;bottom:14px;width:6px;' }
        ];

        handles.forEach(h => {
            const el = document.createElement('div');
            el.id = 'resize-handle-' + h.id;
            el.style.cssText = 'position:absolute;pointer-events:auto;user-select:none;' + h.style + 'cursor:' + h.cursor + ';';
            el.addEventListener('mousedown', function(e) {
                if (e.button !== 0) return;
                e.preventDefault();
                e.stopPropagation();
                window.chrome?.webview?.postMessage({ type: 'WINDOW_RESIZE', edge: h.edge });
            });
            container.appendChild(el);
        });

        document.body.appendChild(container);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupWindowBridge);
    } else {
        setupWindowBridge();
    }

    if (!window._launcherBridgeObs) {
        window._launcherBridgeObs = true;
        const obs = new MutationObserver(setupWindowBridge);
        obs.observe(document.documentElement, { childList: true, subtree: true });
    }
})();";

            await webView.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(windowBridgeScript);
            webView.NavigationCompleted += async (_, _) =>
            {
                try
                {
                    await webView.CoreWebView2.ExecuteScriptAsync(windowBridgeScript);
                }
                catch {}

                // 当页面 HTML/CSS 加载完毕，触发启动器窗口平滑渐显动画
                FadeInWindow();
            };

            // Resolve dist directory across various single-file extract and project directory structures
            var candidatePaths = new[]
            {
                Path.Combine(root, "dist", "launcher"),
                Path.Combine(AppContext.BaseDirectory, "dist", "launcher"),
                Path.Combine(root, "launcher", "dist"),
                Path.Combine(AppContext.BaseDirectory, "launcher", "dist"),
                Path.Combine(root, "dist"),
                Path.Combine(AppContext.BaseDirectory, "dist")
            };

            var distDir = candidatePaths.FirstOrDefault(p => File.Exists(Path.Combine(p, "index.html")));

            if (distDir != null)
            {
                webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
                    "launcher.local",
                    distDir,
                    CoreWebView2HostResourceAccessKind.Allow
                );
                webView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;
                webView.Source = new Uri("http://launcher.local/index.html");
            }
            else
            {
                webView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;
                webView.Source = new Uri("http://localhost:5173/");
            }
            // 超时保底淡入机制（避免网络或极端情况下页面加载事件未触发导致一直透明）
            _ = Task.Delay(1200).ContinueWith(_ => FadeInWindow());
        }
        catch (Exception ex)
        {
            // ⚠️ 兜底：逐像素透明方案下，客户区里的纯黑像素会被 DWM 判为完全透明。
            // 万一页面根本没加载出来（没有内容覆盖客户区），窗口就会变成「一片透明」，
            // 看起来像没启动。所以失败时立刻把底色改回不透明深色，保证窗口可见。
            try { form.BackColor = Color.FromArgb(9, 10, 15); } catch {}
            FadeInWindow();
            MessageBox.Show($"启动器界面初始化失败: {ex.Message}", LauncherHost.Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            var json = e.WebMessageAsJson;
            using var doc = JsonDocument.Parse(json);
            var rootEl = doc.RootElement;
            var requestId = rootEl.TryGetProperty("requestId", out var reqProp) ? reqProp.GetString() : "";
            var type = rootEl.TryGetProperty("type", out var typeProp) ? typeProp.GetString() : "";
            var payload = rootEl.TryGetProperty("payload", out var payloadProp) ? payloadProp : default;
            var edge = rootEl.TryGetProperty("edge", out var edgeProp) ? edgeProp.GetString() : "";

            object? result = null;
            bool success = true;
            string error = "";

            try
            {
                switch (type)
                {
                    case "WINDOW_DRAG":
                        HandleWindowDrag();
                        result = new { acknowledged = true };
                        break;
                    case "WINDOW_RESIZE":
                        HandleWindowResize(edge);
                        result = new { acknowledged = true };
                        break;
                    case "WINDOW_MINIMIZE":
                        HandleWindowMinimize();
                        result = new { acknowledged = true };
                        break;
                    case "WINDOW_MAXIMIZE":
                        HandleWindowMaximize();
                        result = new { acknowledged = true };
                        break;
                    case "WINDOW_RESTORE":
                        HandleWindowRestore();
                        result = new { acknowledged = true };
                        break;
                    case "WINDOW_TOGGLE_MAXIMIZE":
                        HandleToggleMaximize();
                        result = new { acknowledged = true };
                        break;
                    case "WINDOW_CLOSE":
                        HandleWindowClose();
                        result = new { acknowledged = true };
                        break;
                    case "GET_CONFIG":
                        result = HandleGetConfig();
                        break;
                    case "SAVE_CONFIG":
                        HandleSaveConfig(payload);
                        result = new { saved = true };
                        break;
                    case "START_SERVER":
                        result = await HandleStartServerAsync();
                        break;
                    case "STOP_SERVER":
                        result = HandleStopServer();
                        break;
                    case "SAVE_PREFERENCES":
                        HandleSavePreferences(payload);
                        result = new { saved = true };
                        break;
                    case "CREATE_SHORTCUT":
                        HandleCreateShortcut();
                        result = new { created = true };
                        break;
                    case "TEST_PING":
                        result = await HandleTestModelPingAsync(payload);
                        break;
                    case "FETCH_MODELS":
                        result = await HandleFetchModelsAsync(payload);
                        break;
                    case "GET_VERSION":
                        // 只读本地 VERSION，不走网络。胶囊上的版本号靠它即时填上，
                        // 不必等 UPDATE_CHECK 的联网往返（且断网时也能正确显示）。
                        result = new { ok = true, version = LocalVersion() };
                        break;
                    case "UPDATE_CHECK":
                        result = await HandleCheckUpdateAsync();
                        break;
                    case "UPDATE_START":
                        result = await HandleStartUpdateAsync(payload);
                        break;
                    default:
                        result = new { acknowledged = true };
                        break;
                }
            }
            catch (Exception ex)
            {
                success = false;
                error = ex.Message;
            }

            // Post response back to webview
            if (!string.IsNullOrEmpty(requestId))
            {
                var response = JsonSerializer.Serialize(new
                {
                    requestId,
                    success,
                    result,
                    error
                });
                webView.CoreWebView2.PostWebMessageAsJson(response);
            }
        }
        catch (Exception ex)
        {
            SendLog($"[Bridge Error] {ex.Message}");
        }
    }

    private void HandleWindowDrag()
    {
        form.BeginInvoke(() =>
        {
            if (form.WindowState == FormWindowState.Normal)
            {
                ReleaseCapture();
                SendMessage(form.Handle, WM_NCLBUTTONDOWN, (IntPtr)HT_CAPTION, IntPtr.Zero);
            }
        });
    }

    private void HandleWindowResize(string? edge)
    {
        form.BeginInvoke(() =>
        {
            if (form.WindowState == FormWindowState.Normal)
            {
                ReleaseCapture();
                int hitTest = edge switch
                {
                    "TOP_LEFT" => 13,     // HTTOPLEFT
                    "TOP_RIGHT" => 14,    // HTTOPRIGHT
                    "BOTTOM_LEFT" => 16,  // HTBOTTOMLEFT
                    "BOTTOM_RIGHT" => 17, // HTBOTTOMRIGHT
                    "TOP" => 12,          // HTTOP
                    "BOTTOM" => 15,       // HTBOTTOM
                    "LEFT" => 10,         // HTLEFT
                    "RIGHT" => 11,        // HTRIGHT
                    _ => 17
                };
                SendMessage(form.Handle, WM_NCLBUTTONDOWN, (IntPtr)hitTest, IntPtr.Zero);
            }
        });
    }

    private void HandleWindowMinimize()
    {
        form.BeginInvoke(() =>
        {
            form.WindowState = FormWindowState.Minimized;
        });
    }

    private void HandleWindowMaximize()
    {
        form.BeginInvoke(() =>
        {
            form.WindowState = FormWindowState.Maximized;
        });
    }

    private void HandleWindowRestore()
    {
        form.BeginInvoke(() =>
        {
            form.WindowState = FormWindowState.Normal;
        });
    }

    private void HandleToggleMaximize()
    {
        form.BeginInvoke(() =>
        {
            form.WindowState = form.WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized;
        });
    }

    private void HandleWindowClose()
    {
        form.BeginInvoke(() =>
        {
            form.Close();
        });
    }

    private object HandleGetConfig()
    {
        var providersList = new List<JsonNode>();
        if (File.Exists(apiProvidersPath))
        {
            try
            {
                var content = File.ReadAllText(apiProvidersPath, Encoding.UTF8);
                var parsed = JsonNode.Parse(content);
                if (parsed is JsonArray arr)
                {
                    foreach (var item in arr)
                    {
                        if (item is not null)
                        {
                            var pObj = item.AsObject();
                            var pId = pObj["id"]?.GetValue<string>() ?? "";
                            // Read API key from API/.env
                            var envKey = GetEnvKeyForProvider(pId);
                            var apiKey = ReadEnvValue(envKey);
                            pObj["api_key"] = apiKey;
                            providersList.Add(pObj);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                SendLog($"[配置] 读取 api_providers.json 失败: {ex.Message}");
            }
        }

        return new
        {
            providers = providersList,
            preferences = new
            {
                launchAtStartup,
                keepRunningInBackground
            }
        };
    }

    private void HandleSaveConfig(JsonElement payload)
    {
        if (payload.TryGetProperty("providers", out var providersElem))
        {
            var rawJson = providersElem.GetRawText();
            var docNode = JsonNode.Parse(rawJson);
            if (docNode is JsonArray arr)
            {
                var activeEnvKeys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var item in arr)
                {
                    if (item is JsonObject obj)
                    {
                        var pId = obj["id"]?.GetValue<string>() ?? "";
                        var apiKey = obj["api_key"]?.GetValue<string>() ?? "";
                        if (!string.IsNullOrEmpty(pId))
                        {
                            var envKey = GetEnvKeyForProvider(pId);
                            activeEnvKeys.Add(envKey);
                            WriteEnvValue(envKey, apiKey);
                        }
                        // Remove api_key from json storage for safety
                        obj.Remove("api_key");
                    }
                }

                // Clean up orphaned provider keys in API/.env
                CleanOrphanedEnvKeys(activeEnvKeys);

                Directory.CreateDirectory(Path.GetDirectoryName(apiProvidersPath)!);
                var utf8NoBom = new UTF8Encoding(false);
                File.WriteAllText(apiProvidersPath, arr.ToJsonString(new JsonSerializerOptions { WriteIndented = true }), utf8NoBom);
                SendLog("✅ 已同步写入源项目 data/api_providers.json 与 API/.env 配置");
            }
        }
    }

    // 对话模型测速：解析模型所属通道的 OpenAI 兼容地址（仅限 chat_models，落实「仅对话模型」）
    private sealed class ChatTestEndpoint
    {
        public string Url = "";
        public string ApiKey = "";
        public string Model = "";
    }

    private ChatTestEndpoint? ResolveChatTestEndpoint(string model, string channel)
    {
        if (string.IsNullOrEmpty(model) || !File.Exists(apiProvidersPath)) return null;
        try
        {
            var parsed = JsonNode.Parse(File.ReadAllText(apiProvidersPath, Encoding.UTF8));
            if (parsed is not JsonArray arr) return null;
            foreach (var item in arr)
            {
                if (item is not JsonObject p) continue;
                // 只认 chat_models（对话模型），图像/视频模型不测速
                bool isChat = false;
                if (p["chat_models"] is JsonArray cms)
                {
                    foreach (var cm in cms)
                    {
                        if (string.Equals(cm?.GetValue<string>() ?? "", model, StringComparison.OrdinalIgnoreCase))
                        {
                            isChat = true;
                            break;
                        }
                    }
                }
                if (!isChat) continue;

                // 同名模型可能挂在多个通道，按通道名精确匹配（若前端传了 channel）
                if (!string.IsNullOrEmpty(channel))
                {
                    var pName = p["name"]?.GetValue<string>() ?? "";
                    var pId = p["id"]?.GetValue<string>() ?? "";
                    if (!string.Equals(pName, channel, StringComparison.OrdinalIgnoreCase) &&
                        !string.Equals(pId, channel, StringComparison.OrdinalIgnoreCase))
                        continue;
                }

                var baseUrl = (p["base_url"]?.GetValue<string>() ?? "").Trim().TrimEnd('/');
                if (string.IsNullOrEmpty(baseUrl)) return null;
                var protocol = (p["protocol"]?.GetValue<string>() ?? "").ToLowerInvariant();
                string chatBase;
                if (protocol == "volcengine")
                    chatBase = baseUrl.EndsWith("/api/v3") ? baseUrl : baseUrl + "/api/v3";
                else if (protocol == "gemini")
                    chatBase = baseUrl.EndsWith("/v1beta") ? baseUrl : baseUrl + "/v1beta";
                else
                    chatBase = baseUrl.EndsWith("/v1") ? baseUrl : baseUrl + "/v1";

                var pIdForKey = p["id"]?.GetValue<string>() ?? "";
                var apiKey = ReadEnvValue(GetEnvKeyForProvider(pIdForKey));
                return new ChatTestEndpoint
                {
                    Url = chatBase + "/chat/completions",
                    ApiKey = apiKey,
                    Model = model
                };
            }
        }
        catch (Exception ex)
        {
            SendLog($"[测速] 解析通道配置失败: {ex.Message}");
        }
        return null;
    }

    // 对话模型测速：按 OpenAI 兼容格式向模型发送一条最小对话请求，以「请求发出→收到完整回复」的耗时作为结果
    private async Task<object> HandleTestModelPingAsync(JsonElement payload)
    {
        var model = payload.TryGetProperty("model", out var mProp) ? (mProp.GetString() ?? "").Trim() : "";
        var channel = payload.TryGetProperty("channel", out var cProp) ? (cProp.GetString() ?? "").Trim() : "";
        if (string.IsNullOrEmpty(model))
            return new { latency = 0, ok = false, error = "缺少模型名称" };

        var endpoint = ResolveChatTestEndpoint(model, channel);
        if (endpoint is null)
            return new { latency = 0, ok = false, error = "未找到该对话模型对应的通道配置（仅对话模型支持测速）" };
        if (string.IsNullOrEmpty(endpoint.ApiKey))
            return new { latency = 0, ok = false, error = "该通道未配置 API Key，请先在 API 管理中填写" };

        // 与启动器前端约定的参考请求一致：model / stream:false / 单条 user 消息
        var body = new
        {
            model = endpoint.Model,
            stream = false,
            messages = new[] { new { role = "user", content = "你好" } }
        };
        var json = JsonSerializer.Serialize(body);
        using var req = new HttpRequestMessage(HttpMethod.Post, endpoint.Url)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json")
        };
        req.Headers.TryAddWithoutValidation("Authorization", "Bearer " + endpoint.ApiKey);
        req.Headers.TryAddWithoutValidation("Accept", "application/json");
        // 显式 UA：避免部分网关（如 Cloudflare 前置）对无 UA / Python-urllib 类客户端返回 1010 拦截
        req.Headers.TryAddWithoutValidation("User-Agent", "InfiniteCanvasLauncher/1.0");

        var sw = Stopwatch.StartNew();
        try
        {
            // 上限 25s：部分通道（如 Grsai）模型回复较慢，需给足时间；前端 callNative 上限 30s
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(25));
            using var resp = await _pingHttpClient.SendAsync(req, cts.Token);
            // 必须读完响应体：模型「回复完成」这一刻才算计时结束（非流式，等完整回复）
            var bodyText = await resp.Content.ReadAsStringAsync();
            sw.Stop();
            if (!resp.IsSuccessStatusCode)
            {
                // 带上游返回片段，便于区分「模型不存在」「Key 无效」等（如 Grsai 的 rix_api_error）
                var snippet = (bodyText ?? "").Trim().Replace("\r", " ").Replace("\n", " ");
                if (snippet.Length > 160) snippet = snippet.Substring(0, 160);
                return new { latency = 0, ok = false, error = $"模型返回错误 ({(int)resp.StatusCode})" + (snippet.Length > 0 ? $"：{snippet}" : "") };
            }
            return new { latency = (long)Math.Round(sw.Elapsed.TotalMilliseconds), ok = true };
        }
        catch (OperationCanceledException)
        {
            sw.Stop();
            return new { latency = 0, ok = false, error = "测速超时（>25s）" };
        }
        catch (Exception ex)
        {
            sw.Stop();
            return new { latency = 0, ok = false, error = ex.Message };
        }
    }

    // 拉取并自动归类模型：向通道真实的 /models 接口发起 GET，取回模型 id 列表（替换原前端 mock）
    private sealed class ModelsEndpoint
    {
        public string Url = "";
        public string ApiKey = "";
    }

    // Grsai 专有服务没有 /models 接口（实测 GET/POST /v1/models、/v1/api/models 等全部 404），只能返回内置清单。
    // 清单经实测校验：图像模型取自项目 grsai-image-gen skill 的 references/api.md；
    // 文本模型逐个打 /v1/chat/completions 验证，只有返回 200 的才收录。
    //
    // ⚠️ 2026-09-17 的 commit a94a050 曾把 gpt-5.5 / gpt-5.6-* / gpt-6-astra 判为「实测 400，已剔除」，
    //    导致启动器拉取不到任何 GPT 对话模型。
    //    2026-09-20 串行复测（间隔 1.5s）推翻了该结论：gpt-6-astra 18.7s / gpt-5.6-terra 25.2s / gpt-5.6-sol 19.0s /
    //    gpt-5.5 18.6s 全部 HTTP 200 可用；而 gpt-5.6-luna / gpt-5.6 / gpt-6 / gpt-5.5-pro / gpt-4o 返回明确的
    //    "model not found"（负对照有效）→ 当时拿到的 400 是上游抖动，不是模型不存在。
    //    📌 教训：Grsai 的 400 有两种含义 —— "model not found"（真不存在）与上游抖动；判「不存在」必须看到前者，否则重试。
    //    gemini-*-image-* 未收录：名字含 "image" 会被前端归类为图像模型，不应出现在对话清单里。
    //    修改本清单前请先跑技能 gateway-model-probe 的探测流程（串行、间隔 1~1.5s、看 error.message）。
    private static bool IsGrsaiProvider(string protocol, string baseUrl)
    {
        var p = (protocol ?? "").ToLowerInvariant();
        var b = (baseUrl ?? "").ToLowerInvariant();
        return p.Contains("grsai") || b.Contains("grsai");
    }

    private static string[] GrsaiCuratedModels() => new[]
    {
        // Video
        "minimax-h3",
        // Image
        "gpt-image-2.5",
        "gpt-image-2.5-sunburst",
        "gpt-image-2.5-flare",
        "gpt-image-2-vip",
        "gpt-image-2",
        "nano-banana",
        "nano-banana-fast",
        "nano-banana-2",
        "nano-banana-2-lite",
        "nano-banana-2-cl",
        "nano-banana-2-2k-cl",
        "nano-banana-2-4k-cl",
        "nano-banana-pro",
        "nano-banana-pro-vt",
        "nano-banana-pro-cl",
        "nano-banana-pro-vip",
        "nano-banana-pro-4k-vip",
        // Text / Chat（以下均在 Grsai /v1/chat/completions 实测返回 200）
        "gemini-3.1-pro",
        "gemini-2.5-pro",
        "gemini-3-flash",
        "gemini-3-pro",
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        // GPT 系列（2026-09-20 串行实测 /v1/chat/completions 全部返回 200；与 static/js/api-settings.js 的 grsai 预设保持一致）
        "gpt-6-astra",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
        "gpt-5.5",
    };

    private ModelsEndpoint? ResolveModelsEndpoint(string baseUrl, string protocol, string? apiKey, string? providerId, string? providerName)
    {
        string? resolvedKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey;

        // 表单未填 Key 时，尝试从已保存的 api_providers.json + API/.env 按 id/name 解析（编辑既有通道场景）
        if (resolvedKey is null && !string.IsNullOrEmpty(providerId) && File.Exists(apiProvidersPath))
        {
            try
            {
                var parsed = JsonNode.Parse(File.ReadAllText(apiProvidersPath, Encoding.UTF8));
                if (parsed is JsonArray arr)
                {
                    foreach (var item in arr)
                    {
                        if (item is not JsonObject p) continue;
                        var pId = p["id"]?.GetValue<string>() ?? "";
                        var pName = p["name"]?.GetValue<string>() ?? "";
                        if (!string.Equals(pId, providerId, StringComparison.OrdinalIgnoreCase) &&
                            !string.Equals(pName, providerName ?? "", StringComparison.OrdinalIgnoreCase))
                            continue;
                        resolvedKey = ReadEnvValue(GetEnvKeyForProvider(pId));
                        var fromJson = p["base_url"]?.GetValue<string>() ?? "";
                        if (string.IsNullOrWhiteSpace(baseUrl) && !string.IsNullOrWhiteSpace(fromJson))
                            baseUrl = fromJson;
                        break;
                    }
                }
            }
            catch (Exception ex) { SendLog($"[拉取模型] 解析通道配置失败: {ex.Message}"); }
        }

        if (string.IsNullOrWhiteSpace(baseUrl)) return null;
        var baseNorm = baseUrl.Trim().TrimEnd('/');
        var protocolLower = (protocol ?? "").ToLowerInvariant();
        string modelsBase;
        if (protocolLower == "volcengine")
            modelsBase = baseNorm.EndsWith("/api/v3") ? baseNorm : baseNorm + "/api/v3";
        else if (protocolLower == "gemini")
            modelsBase = baseNorm.EndsWith("/v1beta") ? baseNorm : baseNorm + "/v1beta";
        else
            modelsBase = baseNorm.EndsWith("/v1") ? baseNorm : baseNorm + "/v1";

        return new ModelsEndpoint { Url = modelsBase + "/models", ApiKey = resolvedKey ?? "" };
    }

    private async Task<object> HandleFetchModelsAsync(JsonElement payload)
    {
        var baseUrl = payload.TryGetProperty("baseUrl", out var bProp) ? (bProp.GetString() ?? "").Trim() : "";
        var protocol = payload.TryGetProperty("protocol", out var pProp) ? (pProp.GetString() ?? "").Trim() : "";
        var apiKey = payload.TryGetProperty("apiKey", out var kProp) ? (kProp.GetString() ?? "").Trim() : "";
        var providerId = payload.TryGetProperty("id", out var idProp) ? (idProp.GetString() ?? "").Trim() : "";
        var providerName = payload.TryGetProperty("name", out var nProp) ? (nProp.GetString() ?? "").Trim() : "";

        var endpoint = ResolveModelsEndpoint(baseUrl, protocol, apiKey, providerId, providerName);

        // Grsai 专有服务没有 /models 接口，直接返回内置官方清单（用解析后的 URL 一并判断，兼容 baseUrl 从配置回填的情况）
        if (IsGrsaiProvider(protocol, baseUrl) || (endpoint is not null && IsGrsaiProvider("", endpoint.Url)))
            return new { ok = true, models = GrsaiCuratedModels(), source = "curated", note = "Grsai 未提供 /models 接口，返回内置官方模型清单" };

        if (endpoint is null)
            return new { ok = false, error = "缺少接口地址（baseUrl）" };
        if (string.IsNullOrEmpty(endpoint.ApiKey))
            return new { ok = false, error = "缺少 API Key，请在接口表单中填写，或确认该通道已在 API 管理中配置" };

        using var req = new HttpRequestMessage(HttpMethod.Get, endpoint.Url);
        req.Headers.TryAddWithoutValidation("Authorization", "Bearer " + endpoint.ApiKey);
        req.Headers.TryAddWithoutValidation("Accept", "application/json");
        // 显式 UA：避免部分网关（如 Cloudflare 前置）对无 UA / Python-urllib 类客户端返回 1010 拦截
        req.Headers.TryAddWithoutValidation("User-Agent", "InfiniteCanvasLauncher/1.0");

        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(12));
            using var resp = await _pingHttpClient.SendAsync(req, cts.Token);
            var bodyText = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
                return new { ok = false, error = $"接口返回错误 ({(int)resp.StatusCode})，请检查地址与 Key" };

            // 解析多种 OpenAI 兼容 / Anthropic / Gemini 模型列表格式
            var ids = new List<string>();
            try
            {
                var node = JsonNode.Parse(bodyText);
                if (node is JsonObject root)
                {
                    if (root["data"] is JsonArray dataArr)
                    {
                        foreach (var d in dataArr)
                        {
                            var id = d?["id"]?.GetValue<string>();
                            if (!string.IsNullOrEmpty(id)) ids.Add(id);
                        }
                    }
                    // data 为空时回退到 Gemini 风格的 models[] 列表
                    if (ids.Count == 0 && root["models"] is JsonArray modelsArr)
                    {
                        foreach (var m in modelsArr)
                        {
                            var id = m?["id"]?.GetValue<string>();
                            if (string.IsNullOrEmpty(id))
                            {
                                var name = m?["name"]?.GetValue<string>() ?? "";
                                if (name.StartsWith("models/", StringComparison.OrdinalIgnoreCase))
                                    name = name.Substring("models/".Length);
                                id = string.IsNullOrEmpty(name) ? null : name;
                            }
                            if (!string.IsNullOrEmpty(id) && !ids.Contains(id)) ids.Add(id);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                return new { ok = false, error = "无法解析接口返回的模型列表: " + ex.Message };
            }

            if (ids.Count == 0)
                return new { ok = false, error = "接口未返回任何模型（data/models 为空），可能该接口不支持 /models 列表" };

            return new { ok = true, models = ids.ToArray() };
        }
        catch (OperationCanceledException)
        {
            return new { ok = false, error = "拉取超时（>12s）" };
        }
        catch (Exception ex)
        {
            return new { ok = false, error = ex.Message };
        }
    }

    private static void OpenInDefaultBrowser(string url)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true
            });
        }
        catch
        {
            try
            {
                Process.Start("explorer.exe", url);
            }
            catch {}
        }
    }

    private async Task<object> HandleStartServerAsync()
    {
        SendLog("[启动] 正在检查 Infinite Canvas 环境与依赖...");

        var existing = await ProbeAsync(appUrl, TimeSpan.FromSeconds(2), CancellationToken.None);
        if (existing)
        {
            SendLog("检测到已有后端服务 (127.0.0.1:3000)，正在使用系统默认浏览器打开...");
            OpenInDefaultBrowser(appUrl);
            return new { running = true, url = appUrl };
        }

        var python = FindPython(root) ?? throw new InvalidOperationException("未找到可用的 Python。请安装 Python 3.10+ 或放入便携 Python。");
        SendLog($"使用 Python: {python}");

        var depsOk = await EnsureDependenciesAsync(root, python, CancellationToken.None);
        if (!depsOk) throw new InvalidOperationException("依赖环境安装失败，请查看日志。");

        server = StartServer(root, python);
        ownsServer = true;
        server.OutputDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) SendLog($"[服务] {e.Data}"); };
        server.ErrorDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) SendLog($"[服务] {e.Data}"); };
        server.BeginOutputReadLine();
        server.BeginErrorReadLine();

        SendLog("等待 127.0.0.1:3000 服务就绪...");
        var ready = await WaitForServerAsync(appUrl, TimeSpan.FromSeconds(45), CancellationToken.None);
        if (!ready) throw new InvalidOperationException("服务启动超时 (45s)");

        SendLog("🚀 服务就绪，正在使用系统默认浏览器打开无限画布页面...");
        OpenInDefaultBrowser(appUrl);
        return new { running = true, url = appUrl };
    }

    private object HandleStopServer()
    {
        SendLog("[停止] 收到停止服务指令，正在关闭后台服务...");
        StopOwnedServer();
        SendLog("🛑 后端服务已成功停止。");
        return new { stopped = true };
    }

    private void HandleSavePreferences(JsonElement payload)
    {
        if (payload.TryGetProperty("launchAtStartup", out var autoProp))
        {
            launchAtStartup = autoProp.GetBoolean();
            SetStartupRegistry(launchAtStartup);
        }
        if (payload.TryGetProperty("keepRunningInBackground", out var bgProp))
        {
            keepRunningInBackground = bgProp.GetBoolean();
        }
        SavePreferences();
    }

    private void HandleCreateShortcut()
    {
        var desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        var shortcutPath = Path.Combine(desktop, "无限画布 · Infinite Canvas.lnk");
        var exePath = Application.ExecutablePath;

        Type? shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType != null)
        {
            dynamic shell = Activator.CreateInstance(shellType)!;
            dynamic shortcut = shell.CreateShortcut(shortcutPath);
            shortcut.TargetPath = exePath;
            shortcut.WorkingDirectory = root;
            shortcut.Description = "Infinite Canvas for Lochou Launcher";
            shortcut.IconLocation = exePath + ",0";
            shortcut.Save();
            SendLog($"[快捷方式] 已在桌面创建: {shortcutPath}");
        }
    }

    // ------------------------------------------------------------------
    // 更新（阶段 2）
    //
    // ⚠️ 这两个 URL 里的仓库名必须与 main.py 顶部的 GITHUB_* 常量保持一致。
    //    C# 侧读不到 main.py 的常量，只能各写一份；两处不一致就是 bug 信号。
    //    用 releases/latest/download/ 取资产：该路径**不消耗** GitHub API 配额
    //    （api.github.com 匿名只有 60 次/时，实测已 403）。
    // ------------------------------------------------------------------

    private const string UpdateRepoSlug = "HanaJhon/Infinite-Canvas";
    private const string UpdateManifestUrl =
        "https://github.com/" + UpdateRepoSlug + "/releases/latest/download/update.json";
    private const string UpdateAssetBaseUrl =
        "https://github.com/" + UpdateRepoSlug + "/releases/latest/download/";

    private static readonly HttpClient _updateHttpClient = new HttpClient
    {
        Timeout = TimeSpan.FromMinutes(15),
    };

    /// <summary>
    /// 读本地 VERSION 文件（与 main.py 的 current_app_version() 同源），
    /// 并折算成规范式（1.1.10 → 1.2.0）：胶囊上的 V 号与更新比对都用它。
    /// 规则见 VersionUtil.cs。
    /// </summary>
    private string LocalVersion()
    {
        try
        {
            var p = Path.Combine(root, "VERSION");
            if (File.Exists(p)) return VersionUtil.NormalizeVersion(File.ReadAllText(p));
        }
        catch { }
        return "";
    }

    private async Task<object> HandleCheckUpdateAsync()
    {
        var current = LocalVersion();
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, UpdateManifestUrl);
            req.Headers.TryAddWithoutValidation("User-Agent", "InfiniteCanvasLauncher/1.0");
            req.Headers.TryAddWithoutValidation("Accept", "application/json");
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(25));
            using var resp = await _updateHttpClient.SendAsync(req, cts.Token);
            if (!resp.IsSuccessStatusCode)
                return new { ok = false, current, error = $"取更新清单失败（HTTP {(int)resp.StatusCode}）。若刚发版，请确认 Release 已上传 update.json。" };

            var text = await resp.Content.ReadAsStringAsync(cts.Token);
            using var doc = JsonDocument.Parse(text);
            var r = doc.RootElement;

            var latest = r.TryGetProperty("version", out var vProp) ? (vProp.GetString() ?? "") : "";
            if (string.IsNullOrEmpty(latest))
                return new { ok = false, current, error = "更新清单里没有 version 字段" };

            var notes = new List<string>();
            if (r.TryGetProperty("notes", out var nProp) && nProp.ValueKind == JsonValueKind.Array)
                foreach (var it in nProp.EnumerateArray())
                    if (it.ValueKind == JsonValueKind.String) notes.Add(it.GetString() ?? "");

            var size = 0L;
            var sha = "";
            var assetName = "";
            var isDelta = false;
            if (r.TryGetProperty("packages", out var pkgs) && pkgs.ValueKind == JsonValueKind.Array)
            {
                string? deltaName = null, deltaSha = null; long deltaSize = 0;
                string? fullName = null, fullSha = null; long fullSize = 0;
                foreach (var p in pkgs.EnumerateArray())
                {
                    if (!p.TryGetProperty("kind", out var kProp)) continue;
                    var kind = kProp.GetString() ?? "";
                    if (string.Equals(kind, "delta", StringComparison.OrdinalIgnoreCase))
                    {
                        // 只接受「从我当前版本出发」的增量：落点才完整。
                        // 若当前版本与 from_version 不符（例如跳过了一版），必须用完整包。
                        var fromVer = p.TryGetProperty("from_version", out var fv) ? (fv.GetString() ?? "") : "";
                        if (VersionUtil.CompareVersion(fromVer, current) != 0) continue;
                        deltaName = p.TryGetProperty("name", out var nm) ? (nm.GetString() ?? "") : "";
                        deltaSize = p.TryGetProperty("size", out var sz) ? sz.GetInt64() : 0;
                        deltaSha = p.TryGetProperty("sha256", out var hProp) ? (hProp.GetString() ?? "") : "";
                    }
                    else if (string.Equals(kind, "full", StringComparison.OrdinalIgnoreCase))
                    {
                        fullName = p.TryGetProperty("name", out var nm) ? (nm.GetString() ?? "") : "";
                        fullSize = p.TryGetProperty("size", out var sz) ? sz.GetInt64() : 0;
                        fullSha = p.TryGetProperty("sha256", out var hProp) ? (hProp.GetString() ?? "") : "";
                    }
                }
                // 优先增量：体积通常只有改动过的几个文件（几 MB 而非 111 MB）
                if (!string.IsNullOrEmpty(deltaName))
                {
                    assetName = deltaName; size = deltaSize; sha = deltaSha ?? ""; isDelta = true;
                }
                else if (!string.IsNullOrEmpty(fullName))
                {
                    assetName = fullName; size = fullSize; sha = fullSha ?? "";
                }
            }

            if (string.IsNullOrEmpty(assetName))
                return new { ok = false, current, latest, notes, error = "更新清单里没有可用更新包" };

            return new
            {
                ok = true,
                current,
                latest,
                // 版本号跨「日期制遗留 ↔ 三段式」时不能比数值：2026.08.30 恒大于 1.1.1。
                // 所以两边体系不同时只认一个方向 —— 远端已是新方案、本地还是日期制，
                // 才算真有更新；反过来只是远端还没推新版号，不能报「有新版」。
                updateAvailable = VersionUtil.IsLegacyDate(current) != VersionUtil.IsLegacyDate(latest)
                    ? !VersionUtil.IsLegacyDate(latest)
                    : VersionUtil.CompareVersion(latest, current) > 0,
                notes,
                size,
                sha256 = sha,
                assetName,
                isDelta,
                url = UpdateAssetBaseUrl + Uri.EscapeDataString(assetName),
            };
        }
        catch (Exception ex)
        {
            return new { ok = false, current, error = ex.Message };
        }
    }

    private Task<object> HandleStartUpdateAsync(JsonElement payload)
    {
        if (payload.ValueKind != JsonValueKind.Object)
            return Task.FromResult<object>(new { ok = false, error = "缺少更新参数" });

        var url = payload.TryGetProperty("url", out var uProp) ? (uProp.GetString() ?? "") : "";
        var expectedSha = payload.TryGetProperty("sha256", out var sProp) ? (sProp.GetString() ?? "") : "";
        var expectedSize = payload.TryGetProperty("size", out var zProp) && zProp.TryGetInt64(out var z) ? z : 0L;
        var targetVersion = payload.TryGetProperty("version", out var vProp) ? (vProp.GetString() ?? "") : "";

        if (string.IsNullOrEmpty(url))
            return Task.FromResult<object>(new { ok = false, error = "缺少下载地址" });

        // 防并发：用户点完更新又立刻重开启动器再点一次时，两个执行器同时往同一个
        // 安装目录解包会把目录写坏。UI 上按钮在下载期间是禁用的，这里是第二道保险。
        if (Program.IsUpdateInProgress(root))
            return Task.FromResult<object>(new { ok = false, error = "已有一个更新正在进行中，请等它完成后重启启动器再试。" });

        // ⚠️ 前端 callNative 的超时只有 30s，而完整包 111 MB 的下载远超此值。
        //    所以这里立刻返回，真正的「下载 → 校验 → 派生执行器」放到后台任务，
        //    进度与错误一律走 UPDATE_PROGRESS 推送。
        _ = Task.Run(() => RunUpdateAsync(url, expectedSha, expectedSize, targetVersion));
        return Task.FromResult<object>(new { ok = true, started = true, version = targetVersion });
    }

    private async Task RunUpdateAsync(string url, string expectedSha, long expectedSize, string targetVersion)
    {
        var downloadDir = Path.Combine(root, "data", "update_download");
        Directory.CreateDirectory(downloadDir);
        var fileName = Path.GetFileName(new Uri(url).LocalPath);
        if (string.IsNullOrEmpty(fileName)) fileName = "update.zip";
        var zipPath = Path.Combine(downloadDir, fileName);
        var tmpPath = zipPath + ".part";

        try
        {
            SendLog($"开始下载更新包 {fileName} ...");
            SendToWebView("UPDATE_PROGRESS", new { phase = "download", percent = 0, received = 0L, total = expectedSize });

            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            req.Headers.TryAddWithoutValidation("User-Agent", "InfiniteCanvasLauncher/1.0");
            using var cts = new CancellationTokenSource(TimeSpan.FromMinutes(30));
            using var resp = await _updateHttpClient.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cts.Token);
            if (!resp.IsSuccessStatusCode)
            {
                Fail($"下载失败（HTTP {(int)resp.StatusCode}）");
                return;
            }

            var total = resp.Content.Headers.ContentLength ?? expectedSize;
            long received = 0;
            var lastPercent = -1;
            await using (var src = await resp.Content.ReadAsStreamAsync(cts.Token))
            await using (var dst = File.Create(tmpPath))
            {
                var buffer = new byte[256 * 1024];
                int n;
                while ((n = await src.ReadAsync(buffer, cts.Token)) > 0)
                {
                    await dst.WriteAsync(buffer.AsMemory(0, n), cts.Token);
                    received += n;
                    if (total > 0)
                    {
                        var percent = (int)(received * 100 / total);
                        if (percent != lastPercent)
                        {
                            lastPercent = percent;
                            SendToWebView("UPDATE_PROGRESS", new { phase = "download", percent, received, total });
                        }
                    }
                }
            }

            // 校验：体积 + sha256，两者都必须过才允许动盘上的文件
            SendToWebView("UPDATE_PROGRESS", new { phase = "verify", percent = 100, received, total });
            var actualSize = new FileInfo(tmpPath).Length;
            if (expectedSize > 0 && actualSize != expectedSize)
            {
                TryDeleteFile(tmpPath);
                Fail($"体积校验失败：期望 {expectedSize} 字节，实际 {actualSize} 字节");
                return;
            }
            if (!string.IsNullOrEmpty(expectedSha))
            {
                var actualSha = await Task.Run(() => Sha256File(tmpPath));
                if (!string.Equals(actualSha, expectedSha, StringComparison.OrdinalIgnoreCase))
                {
                    TryDeleteFile(tmpPath);
                    Fail($"校验失败：sha256 不一致（实际 {actualSha[..12]}…）");
                    return;
                }
            }

            if (File.Exists(zipPath)) TryDeleteFile(zipPath);
            File.Move(tmpPath, zipPath);
            SendLog("更新包校验通过。");

            // 派生更新执行器：把自己复制一份到 data/ 下再跑，这样它能覆盖安装目录里的正本 exe
            var selfPath = Environment.ProcessPath;
            if (string.IsNullOrEmpty(selfPath) || !File.Exists(selfPath))
            {
                Fail("定位不到启动器自身路径，无法派生更新进程");
                return;
            }

            var applierPath = Path.Combine(root, "data", $"_apply_update_{Environment.ProcessId}.exe");
            File.Copy(selfPath, applierPath, overwrite: true);

            var pids = PrepareForUpdate();
            var psi = new ProcessStartInfo
            {
                FileName = applierPath,
                Arguments = $"--apply-update \"{zipPath}\" \"{root}\" \"{string.Join(",", pids)}\" \"{selfPath}\"",
                WorkingDirectory = root,
                UseShellExecute = false,
            };
            Process.Start(psi);
            SendLog("更新进程已启动，启动器即将退出以释放文件占用。");
            SendToWebView("UPDATE_PROGRESS", new
            {
                phase = "done",
                percent = 100,
                version = targetVersion,
                downloadedBytes = actualSize,
            });

            // 留一点时间把消息送到界面，再退出
            ScheduleExit(1500);
        }
        catch (Exception ex)
        {
            TryDeleteFile(tmpPath);
            Fail(ex.Message);
        }
    }

    private void Fail(string message)
    {
        SendLog($"[更新失败] {message}");
        SendToWebView("UPDATE_PROGRESS", new { phase = "error", error = message });
    }

    /// <summary>停掉服务进程并返回需要等待退出的 PID 列表（含自己）。</summary>
    private List<int> PrepareForUpdate()
    {
        var pids = new List<int> { Environment.ProcessId };
        try
        {
            if (server is not null && !server.HasExited)
            {
                var pid = server.Id;
                server.Kill(true);
                try { server.WaitForExit(8000); } catch { }
                pids.Add(pid);
                SendLog($"已停止服务进程（PID {pid}）。");
            }
        }
        catch (Exception ex)
        {
            SendLog($"停止服务进程时出错：{ex.Message}");
        }
        ownsServer = false;
        return pids;
    }

    private void ScheduleExit(int delayMs)
    {
        try
        {
            form.BeginInvoke(() =>
            {
                var timer = new System.Windows.Forms.Timer { Interval = delayMs };
                timer.Tick += (_, _) =>
                {
                    timer.Stop();
                    timer.Dispose();
                    forceExit = true;
                    tray.Visible = false;
                    form.Close();
                };
                timer.Start();
            });
        }
        catch { }
    }

    private void SendToWebView(string type, object payload)
    {
        if (form.IsDisposed) return;
        try
        {
            var json = JsonSerializer.Serialize(new { type, payload });
            if (webView.CoreWebView2 != null)
                webView.BeginInvoke(() => webView.CoreWebView2.PostWebMessageAsJson(json));
        }
        catch { }
    }

    private static string Sha256File(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static void TryDeleteFile(string path)
    {
        try { if (File.Exists(path)) File.Delete(path); } catch { }
    }

    private void SendLog(string message)
    {
        if (form.IsDisposed) return;
        try
        {
            var json = JsonSerializer.Serialize(new
            {
                type = "LOG",
                payload = $"[{DateTime.Now:HH:mm:ss}] {message}"
            });
            if (webView.CoreWebView2 != null)
            {
                webView.BeginInvoke(() => webView.CoreWebView2.PostWebMessageAsJson(json));
            }
        }
        catch {}
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        if (forceExit) return;
        if (keepRunningInBackground)
        {
            e.Cancel = true;
            form.Hide();
            tray.Visible = true;
            tray.ShowBalloonTip(1500, LauncherHost.Title, "已最小化到系统托盘，服务持续在后台运行。", ToolTipIcon.Info);
        }
        else
        {
            forceExit = true;
            StopOwnedServer();
        }
    }

    private void FadeInWindow()
    {
        form.BeginInvoke(() =>
        {
            if (form.Opacity >= 1.0)
            {
                // 已经是全不透明（比如超时保底路径），也要确认分层样式已摘掉
                form.EnsurePerPixelAlpha();
                return;
            }

            var fadeTimer = new System.Windows.Forms.Timer { Interval = 16 }; // ~60fps
            fadeTimer.Tick += (s, _) =>
            {
                if (form.Opacity < 1.0)
                {
                    form.Opacity = Math.Min(1.0, form.Opacity + 0.08); // 约 200ms 内丝滑淡入
                }
                else
                {
                    fadeTimer.Stop();
                    fadeTimer.Dispose();
                    // ⚠️ 淡入用的是 WS_EX_LAYERED + LWA_ALPHA（整窗统一透明度），
                    // 它会盖掉 DWM 的逐像素 alpha —— 不摘掉的话圆角会一直退化成方块。
                    form.EnsurePerPixelAlpha();
                }
            };
            fadeTimer.Start();
        });
    }

    private void RestoreWindow()
    {
        form.Show();
        form.WindowState = FormWindowState.Normal;
        form.Activate();
        if (form.Opacity < 1.0)
        {
            form.Opacity = 1.0;
        }
        form.EnsurePerPixelAlpha();
    }

    private void ExitFromTray()
    {
        forceExit = true;
        tray.Visible = false;
        StopOwnedServer();
        form.Close();
    }

    private void StopOwnedServer()
    {
        if (!ownsServer || server is null) return;
        try { if (!server.HasExited) server.Kill(true); } catch {}
        ownsServer = false;
    }

    private void SetStartupRegistry(bool enable)
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run", true);
            if (key != null)
            {
                if (enable)
                    key.SetValue("InfiniteCanvasLauncher", $"\"{Application.ExecutablePath}\"");
                else
                    key.DeleteValue("InfiniteCanvasLauncher", false);
            }
        }
        catch {}
    }

    private void LoadPreferences()
    {
        try
        {
            if (File.Exists(preferencePath))
            {
                var doc = JsonNode.Parse(File.ReadAllText(preferencePath));
                if (doc is not null)
                {
                    keepRunningInBackground = doc["keepRunningInBackground"]?.GetValue<bool>() ?? true;
                    launchAtStartup = doc["launchAtStartup"]?.GetValue<bool>() ?? false;
                }
            }
        }
        catch {}
    }

    private void SavePreferences()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(preferencePath)!);
            var obj = new JsonObject
            {
                ["keepRunningInBackground"] = keepRunningInBackground,
                ["launchAtStartup"] = launchAtStartup
            };
            File.WriteAllText(preferencePath, obj.ToJsonString());
        }
        catch {}
    }

    private string GetEnvKeyForProvider(string providerId)
    {
        if (providerId == "comfly") return "COMFLY_API_KEY";
        if (providerId == "modelscope") return "MODELSCOPE_API_KEY";
        if (providerId == "runninghub") return "RUNNINGHUB_API_KEY";
        if (providerId == "volcengine") return "ARK_API_KEY";
        return $"API_PROVIDER_{Regex.Replace(providerId, @"[^A-Za-z0-9]", "_").ToUpper()}_KEY";
    }

    private string ReadEnvValue(string key)
    {
        if (!File.Exists(apiEnvPath) || string.IsNullOrWhiteSpace(key)) return "";
        try
        {
            foreach (var line in File.ReadAllLines(apiEnvPath))
            {
                var trimmed = line.Trim();
                if (trimmed.StartsWith("#") || !trimmed.Contains('=')) continue;
                var parts = trimmed.Split('=', 2);
                if (parts[0].Trim() == key) return parts[1].Trim();
            }
        }
        catch {}
        return "";
    }

    private void WriteEnvValue(string key, string value)
    {
        if (string.IsNullOrWhiteSpace(key)) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(apiEnvPath)!);
            var utf8NoBom = new UTF8Encoding(false);
            var lines = File.Exists(apiEnvPath) ? File.ReadAllLines(apiEnvPath, utf8NoBom).ToList() : new List<string>();
            bool found = false;
            for (int i = 0; i < lines.Count; i++)
            {
                var trimmed = lines[i].Trim();
                if (trimmed.StartsWith("#") || !trimmed.Contains('=')) continue;
                var parts = trimmed.Split('=', 2);
                if (parts[0].Trim() == key)
                {
                    lines[i] = $"{key}={value}";
                    found = true;
                    break;
                }
            }
            if (!found) lines.Add($"{key}={value}");
            File.WriteAllLines(apiEnvPath, lines, utf8NoBom);
        }
        catch {}
    }

    private void CleanOrphanedEnvKeys(HashSet<string> activeEnvKeys)
    {
        if (!File.Exists(apiEnvPath)) return;
        try
        {
            var utf8NoBom = new UTF8Encoding(false);
            var lines = File.ReadAllLines(apiEnvPath, utf8NoBom).ToList();
            bool changed = false;
            for (int i = 0; i < lines.Count; i++)
            {
                var trimmed = lines[i].Trim();
                if (trimmed.StartsWith("#") || !trimmed.Contains('=')) continue;
                var parts = trimmed.Split('=', 2);
                var k = parts[0].Trim();
                if (k.StartsWith("API_PROVIDER_", StringComparison.OrdinalIgnoreCase) && k.EndsWith("_KEY", StringComparison.OrdinalIgnoreCase))
                {
                    if (!activeEnvKeys.Contains(k))
                    {
                        lines[i] = $"{k}=";
                        changed = true;
                    }
                }
            }
            if (changed)
            {
                File.WriteAllLines(apiEnvPath, lines, utf8NoBom);
            }
        }
        catch {}
    }

    private static string? FindPython(string root)
    {
        var bundled = Path.Combine(root, "python", "python.exe");
        if (File.Exists(bundled) && CanRun(bundled, "--version")) return bundled;
        foreach (var candidate in new[] { "python", "py" }) if (CanRun(candidate, candidate == "py" ? "-3 --version" : "--version")) return candidate;
        return null;
    }

    private static bool CanRun(string file, string args)
    {
        try { using var p = StartProcess(file, args, Directory.GetCurrentDirectory(), false); p.WaitForExit(5000); return p.ExitCode == 0; } catch { return false; }
    }

    private async Task<bool> EnsureDependenciesAsync(string root, string python, CancellationToken token)
    {
        var requirements = new Dictionary<string, string> { ["fastapi"] = "fastapi", ["uvicorn"] = "uvicorn", ["requests"] = "requests", ["pydantic"] = "pydantic", ["multipart"] = "python-multipart", ["httpx"] = "httpx", ["PIL"] = "pillow" };
        var missing = new List<string>();
        foreach (var item in requirements) if (!await RunAsync(python, $"-c \"import {item.Key}\"", root, token, false)) missing.Add(item.Value);
        if (missing.Count == 0) { SendLog("依赖检查全部通过，跳过安装。"); return true; };
        SendLog($"缺少依赖包: {string.Join(", ", missing)}");
        var args = string.Join(" ", missing.Select(Quote));
        var packages = Path.Combine(root, "packages");
        if (Directory.Exists(packages))
        {
            SendLog("尝试从本地 packages 离线安装...");
            if (await RunAsync(python, $"-m pip install --no-index --find-links {Quote(packages)} {args}", root, token, true)) return true;
        }
        if (!await RunAsync(python, "-m pip --version", root, token, false))
        {
            var bootstrap = Path.Combine(root, "get-pip.py");
            if (!File.Exists(bootstrap) || !await RunAsync(python, $"{Quote(bootstrap)} --quiet", root, token, true)) return false;
        }
        return await RunAsync(python, $"-m pip install {args}", root, token, true);
    }

    private static Process StartServer(string root, string python) => StartProcess(python, "main.py", root, true);
    private static Process StartProcess(string file, string args, string cwd, bool redirect)
    {
        return Process.Start(new ProcessStartInfo(file, args) { WorkingDirectory = cwd, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = redirect, RedirectStandardError = redirect }) ?? throw new InvalidOperationException($"无法启动 {file}");
    }

    private async Task<bool> RunAsync(string file, string args, string cwd, CancellationToken token, bool output)
    {
        try
        {
            using var p = StartProcess(file, args, cwd, true);
            while (!p.HasExited)
            {
                if (output)
                {
                    var line = await p.StandardOutput.ReadLineAsync(token);
                    if (!string.IsNullOrWhiteSpace(line)) SendLog($"[安装] {line}");
                }
                else await Task.Delay(80, token);
            }
            return p.ExitCode == 0;
        }
        catch (Exception ex) { if (output) SendLog($"[安装错误] {ex.Message}"); return false; }
    }

    private static async Task<bool> WaitForServerAsync(string target, TimeSpan timeout, CancellationToken token)
    {
        var until = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < until && !token.IsCancellationRequested)
        {
            if (await ProbeAsync(target, TimeSpan.FromSeconds(2), token)) return true;
            await Task.Delay(500, token);
        }
        return false;
    }

    private static async Task<bool> ProbeAsync(string target, TimeSpan timeout, CancellationToken token)
    {
        try { using var client = new HttpClient { Timeout = timeout }; using var response = await client.GetAsync(target, token); return (int)response.StatusCode < 500; } catch { return false; }
    }

    private static string Quote(string value) => $"\"{value.Replace("\"", "\\\"")}\"";
    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        StopOwnedServer();
        tray.Visible = false;
        tray.Dispose();
        webView.Dispose();
        server?.Dispose();
        applicationIcon.Dispose();
    }
}

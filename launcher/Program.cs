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
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        using var mutex = new Mutex(true, "InfiniteCanvasLauncher.SingleInstance", out var isOwner);
        if (!isOwner)
        {
            MessageBox.Show("Infinite Canvas 已经在运行中。", LauncherHost.Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var root = ResolveProjectRoot();
        using var host = new LauncherHost(root, AppUrl);
        Application.Run(host.Form);
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

    [DllImport("gdi32.dll")]
    private static extern IntPtr CreateRoundRectRgn(int x1, int y1, int x2, int y2, int cx, int cy);

    [DllImport("user32.dll")]
    private static extern int SetWindowRgn(IntPtr hWnd, IntPtr hRgn, bool bRedraw);

    [DllImport("gdi32.dll")]
    private static extern bool DeleteObject(IntPtr hObject);

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

    private const int WM_GETMINMAXINFO = 0x24;
    private const int WM_SIZING = 0x0214;
    private const int WS_MINIMIZEBOX = 0x20000;
    private const int WS_MAXIMIZEBOX = 0x10000;
    private const int CS_DROPSHADOW = 0x20000;

    private const int WMSZ_LEFT = 1;
    private const int WMSZ_RIGHT = 2;
    private const int WMSZ_TOP = 3;
    private const int WMSZ_TOPLEFT = 4;
    private const int WMSZ_TOPRIGHT = 5;
    private const int WMSZ_BOTTOM = 6;
    private const int WMSZ_BOTTOMLEFT = 7;
    private const int WMSZ_BOTTOMRIGHT = 8;

    private const double TargetAspectRatio = 16.0 / 9.0;
    private const int CornerRadius = 24;

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
            cp.ClassStyle |= CS_DROPSHADOW;
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
        UpdateFormRegion();
    }

    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        UpdateFormRegion();
    }

    public void UpdateFormRegion()
    {
        if (WindowState == FormWindowState.Maximized)
        {
            SetWindowRgn(Handle, IntPtr.Zero, true);
        }
        else
        {
            IntPtr hRgn = CreateRoundRectRgn(0, 0, Width + 1, Height + 1, CornerRadius, CornerRadius);
            SetWindowRgn(Handle, hRgn, true);
            DeleteObject(hRgn);
        }
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
            BackColor = Color.FromArgb(9, 10, 15),
            Icon = applicationIcon,
            Opacity = 0.0 // 初始完全透明，等页面渲染就绪后平滑渐显，杜绝白屏/黑屏闪烁
        };

        webView = new WebView2
        {
            Dock = DockStyle.Fill,
            DefaultBackgroundColor = Color.FromArgb(9, 10, 15) // 设置 WebView2 底层画板默认背景为深色
        };
        form.Controls.Add(webView);
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
                html, body, #root {
                    border-radius: 18px !important;
                    overflow: hidden !important;
                    background-color: #090a0f !important;
                }
                *:focus, *:focus-visible, button:focus, button:focus-visible {
                    outline: none !important;
                    box-shadow: none !important;
                }
            `;
            document.head.appendChild(style);
        }
    }

    function setupWindowBridge() {
        injectGlobalStyles();

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

        var sw = Stopwatch.StartNew();
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(13));
            using var resp = await _pingHttpClient.SendAsync(req, cts.Token);
            // 必须读完响应体：模型「回复完成」这一刻才算计时结束（非流式，等完整回复）
            var _ = await resp.Content.ReadAsStringAsync();
            sw.Stop();
            if (!resp.IsSuccessStatusCode)
                return new { latency = 0, ok = false, error = $"模型返回错误 ({(int)resp.StatusCode})" };
            return new { latency = (long)Math.Round(sw.Elapsed.TotalMilliseconds), ok = true };
        }
        catch (OperationCanceledException)
        {
            sw.Stop();
            return new { latency = 0, ok = false, error = "测速超时（>13s）" };
        }
        catch (Exception ex)
        {
            sw.Stop();
            return new { latency = 0, ok = false, error = ex.Message };
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
            if (form.Opacity >= 1.0) return;

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

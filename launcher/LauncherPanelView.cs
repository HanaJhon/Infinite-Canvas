using System.Drawing.Drawing2D;
using System.Text.Json;

/// <summary>
/// 启动器主界面 —— WinForms 原生控件版（2026-10-26 起替代 WebView2）。
///
/// 🚨 为什么换掉 WebView2：老板本机 WebView2 运行时损坏（`Application\155.x\` 下缺 SideBySide
///    assembly），启动器直接报 `0x800736B1 并行配置不正确`，完全打不开。原生控件不依赖任何
///    浏览器运行时，永远不会再被 WebView2/Edge 的更新连累。
///
/// 功能对等（原来由 dist/launcher 的 HTML 承担）：
///   起服务 / 停服务 / 打开画布 / 检查更新 / 更新进度 / 日志。
///   原来 HTML 里那 7 个 WINDOW_* 消息（拖拽、缩放、最小化…）不再需要 —— 原生窗口自带标题栏。
///
/// 通信：
///   UI → 宿主：<see cref="ActionRequested"/>（type 与原来 WebView2 的消息 type 完全一致，
///              宿主那边 OnWebMessageReceived 的 switch 原样复用）。
///   宿主 → UI：<see cref="HandleMessage"/>（吃原来 PostJsonToWebView 发的同一份 JSON）。
/// </summary>
internal sealed class LauncherPanelView : Panel
{
    /// <summary>(type, payloadJson)。type 沿用原 WebView2 协议的取值。</summary>
    public event Action<string, string>? ActionRequested;

    private static readonly Color Bg = Color.FromArgb(9, 10, 15);
    private static readonly Color Card = Color.FromArgb(18, 20, 28);
    private static readonly Color Line = Color.FromArgb(42, 46, 58);
    private static readonly Color TextMain = Color.FromArgb(232, 236, 244);
    private static readonly Color TextDim = Color.FromArgb(138, 146, 164);
    private static readonly Color Accent = Color.FromArgb(94, 168, 255);
    private static readonly Color Danger = Color.FromArgb(232, 104, 104);

    private readonly Label _title;
    private readonly Label _version;
    private readonly Label _status;
    private readonly Label _url;
    private readonly ProgressBar _progress;
    private readonly TextBox _log;
    private readonly Button _btnStart;
    private readonly Button _btnStop;
    private readonly Button _btnOpen;
    private readonly Button _btnUpdate;
    private readonly Button _btnSettings;

    public LauncherPanelView()
    {
        Dock = DockStyle.Fill;
        BackColor = Bg;
        DoubleBuffered = true;
        Padding = new Padding(40, 32, 40, 32);

        _title = new Label
        {
            Text = "CANVAS · LOCHOU LAUNCHER",
            ForeColor = TextMain,
            Font = new Font("Microsoft YaHei UI", 15f, FontStyle.Bold),
            AutoSize = true,
            Location = new Point(40, 32),
        };

        _version = new Label
        {
            Text = "v—",
            ForeColor = TextDim,
            Font = new Font("Microsoft YaHei UI", 9.5f),
            AutoSize = true,
        };

        _status = new Label
        {
            Text = "正在初始化…",
            ForeColor = TextMain,
            Font = new Font("Microsoft YaHei UI", 12f, FontStyle.Bold),
            AutoSize = true,
        };

        _url = new Label
        {
            Text = "",
            ForeColor = TextDim,
            Font = new Font("Consolas", 10f),
            AutoSize = true,
        };

        _progress = new ProgressBar
        {
            Minimum = 0,
            Maximum = 100,
            Value = 0,
            Visible = false,
            Height = 8,
            Style = ProgressBarStyle.Continuous,
        };

        _log = new TextBox
        {
            Multiline = true,
            ReadOnly = true,
            ScrollBars = ScrollBars.Vertical,
            BackColor = Color.FromArgb(13, 15, 21),
            ForeColor = TextDim,
            BorderStyle = BorderStyle.FixedSingle,
            Font = new Font("Consolas", 9f),
            WordWrap = false,
        };

        _btnStart = MakeButton("启动服务", Accent, () => Raise("START_SERVER"));
        _btnStop = MakeButton("停止服务", Danger, () => Raise("STOP_SERVER"));
        _btnOpen = MakeButton("打开画布", null, () => Raise("OPEN_CANVAS"));
        _btnUpdate = MakeButton("检查更新", null, () => Raise("UPDATE_CHECK"));
        _btnSettings = MakeButton("打开配置目录", null, () => Raise("OPEN_CONFIG_DIR"));

        Controls.AddRange(new Control[]
        {
            _title, _version, _status, _url, _progress, _log,
            _btnStart, _btnStop, _btnOpen, _btnUpdate, _btnSettings,
        });

        // 打开画布 / 打开配置目录由宿主处理（不经过原 switch，直接做）
        _btnOpen.Click += (_, _) => ActionRequested?.Invoke("OPEN_CANVAS", "{}");
        _btnSettings.Click += (_, _) => ActionRequested?.Invoke("OPEN_CONFIG_DIR", "{}");
        _btnUpdate.Click += (_, _) => ActionRequested?.Invoke("UPDATE_CHECK", "{}");

        Resize += (_, _) => LayoutChildren();
        LayoutChildren();
    }

    private Button MakeButton(string text, Color? accent, Action onClick)
    {
        var b = new Button
        {
            Text = text,
            FlatStyle = FlatStyle.Flat,
            BackColor = accent.HasValue ? accent.Value : Card,
            ForeColor = accent.HasValue ? Color.White : TextMain,
            Font = new Font("Microsoft YaHei UI", 10.5f, FontStyle.Bold),
            Height = 44,
            Width = 132,
            Cursor = Cursors.Hand,
        };
        b.FlatAppearance.BorderColor = accent.HasValue ? accent.Value : Line;
        b.FlatAppearance.BorderSize = 1;
        b.Click += (_, _) => onClick();
        return b;
    }

    /// <summary>按当前尺寸摆放控件（窗口可缩放）。</summary>
    private void LayoutChildren()
    {
        int padL = Padding.Left, padR = Padding.Right;
        int w = Math.Max(200, Width - padL - padR);

        _title.Location = new Point(padL, Padding.Top);
        _version.Location = new Point(padL + _title.PreferredWidth + 12, Padding.Top + 10);

        int y = _title.Bottom + 28;
        _status.Location = new Point(padL, y);
        y = _status.Bottom + 6;
        _url.Location = new Point(padL, y);

        y = _url.Bottom + 20;
        _progress.Location = new Point(padL, y);
        _progress.Width = w;
        y += _progress.Height + 20;

        // 按钮行
        int bx = padL;
        foreach (var b in new[] { _btnStart, _btnStop, _btnOpen, _btnUpdate, _btnSettings })
        {
            b.Location = new Point(bx, y);
            bx += b.Width + 10;
        }
        y += _btnStart.Height + 24;

        _log.Location = new Point(padL, y);
        _log.Width = w;
        _log.Height = Math.Max(80, Height - y - Padding.Bottom);
    }

    private void Raise(string type, string payload = "{}")
        => ActionRequested?.Invoke(type, payload);

    /// <summary>版本号 / 端口等初始信息。</summary>
    public void SetInfo(string version, int port, string url)
    {
        if (IsDisposed) return;
        _version.Text = "v" + version;
        _url.Text = url;
        LayoutChildren();
    }

    /// <summary>服务状态：running = true 显示「运行中」。</summary>
    public void SetServerState(bool running, string url)
    {
        if (IsDisposed) return;
        _status.Text = running ? "服务运行中" : "服务已停止";
        _status.ForeColor = running ? Accent : TextDim;
        _url.Text = running ? url : "";
        _btnStart.Enabled = !running;
        _btnStop.Enabled = running;
        _btnOpen.Enabled = running;
        LayoutChildren();
    }

    /// <summary>处理宿主推来的消息（原来是 PostJsonToWebView 的 JSON）。</summary>
    public void HandleMessage(string json)
    {
        if (IsDisposed || string.IsNullOrWhiteSpace(json)) return;
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            var type = root.TryGetProperty("type", out var t) ? t.GetString() : "";

            switch (type)
            {
                case "LOG":
                    AppendLog(root.TryGetProperty("payload", out var p) ? (p.GetString() ?? "") : "");
                    break;

                case "UPDATE_PROGRESS":
                case "ROLLBACK_PROGRESS":
                    if (root.TryGetProperty("payload", out var up) && up.ValueKind == JsonValueKind.Object)
                    {
                        var pct = up.TryGetProperty("percent", out var pc) && pc.TryGetNumber(out var n) ? n : 0;
                        var msg = up.TryGetProperty("message", out var m) ? m.GetString() : "";
                        ShowProgress((int)Math.Clamp(pct, 0, 100), msg);
                    }
                    break;

                case "SERVER_STATE":
                    if (root.TryGetProperty("payload", out var st) && st.ValueKind == JsonValueKind.Object)
                    {
                        var running = st.TryGetProperty("running", out var r) && r.ValueKind == JsonValueKind.True;
                        var url = st.TryGetProperty("url", out var u) ? u.GetString() ?? "" : "";
                        SetServerState(running, url);
                    }
                    break;
            }
        }
        catch { /* 消息格式异常不影响界面 */ }
    }

    public void AppendLog(string line)
    {
        if (IsDisposed || string.IsNullOrEmpty(line)) return;
        if (_log.TextLength > 60000) _log.Text = _log.Text.Substring(_log.TextLength - 30000);
        _log.AppendText(line + Environment.NewLine);
    }

    public void ShowProgress(int percent, string? message)
    {
        if (IsDisposed) return;
        _progress.Visible = true;
        _progress.Value = Math.Clamp(percent, 0, 100);
        if (!string.IsNullOrEmpty(message)) AppendLog(message);
    }

    public void HideProgress()
    {
        if (IsDisposed) return;
        _progress.Visible = false;
        _progress.Value = 0;
    }
}

/// <summary>JsonElement 取数字的小工具（System.Text.Json 没有 TryGetNumber）。</summary>
internal static class JsonElementNumberExtensions
{
    public static bool TryGetNumber(this JsonElement el, out double value)
    {
        value = 0;
        if (el.ValueKind == JsonValueKind.Number && el.TryGetDouble(out value)) return true;
        if (el.ValueKind == JsonValueKind.String && double.TryParse(el.GetString(), out value)) return true;
        return false;
    }
}

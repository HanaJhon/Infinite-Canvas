using System.Diagnostics;
using System.Drawing;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

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

sealed class LauncherHost : IDisposable
{
    public const string Title = "Infinite Canvas";
    private readonly string root;
    private readonly string url;
    private readonly Form form;
    private readonly Icon applicationIcon;
    private readonly TextBox logBox;
    private readonly Label status;
    private readonly WebView2 webView;
    private readonly NotifyIcon tray;
    private readonly ToolStripMenuItem clearPreferenceItem;
    private readonly string preferencePath;
    private Process? server;
    private bool ownsServer;
    private bool forceExit;
    private bool disposed;
    private CloseAction? rememberedAction;

    private enum CloseAction { Exit, Tray }

    public Form Form => form;

    public LauncherHost(string projectRoot, string appUrl)
    {
        root = projectRoot;
        url = appUrl;
        preferencePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "InfiniteCanvasLauncher", "preferences.json");
        applicationIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? (Icon)SystemIcons.Application.Clone();
        form = new Form
        {
            Text = LauncherHost.Title,
            Width = 1440,
            Height = 920,
            MinimumSize = new Size(960, 640),
            StartPosition = FormStartPosition.CenterScreen,
            BackColor = Color.White,
            Icon = applicationIcon
        };
        status = new Label { Dock = DockStyle.Top, Height = 34, TextAlign = ContentAlignment.MiddleLeft, Padding = new Padding(12, 0, 0, 0), BackColor = Color.FromArgb(38, 52, 73), ForeColor = Color.White, Text = "正在检查运行环境..." };
        logBox = new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, BackColor = Color.FromArgb(248, 249, 251), BorderStyle = BorderStyle.None, Font = new Font("Consolas", 9), Padding = new Padding(12) };
        webView = new WebView2 { Dock = DockStyle.Fill, Visible = false };
        form.Controls.Add(webView);
        form.Controls.Add(logBox);
        form.Controls.Add(status);
        form.FormClosing += OnFormClosing;
        form.Shown += async (_, _) => await BootstrapAsync();

        tray = new NotifyIcon { Icon = applicationIcon, Text = LauncherHost.Title, Visible = false };
        var menu = new ContextMenuStrip();
        menu.Items.Add("打开窗口", null, (_, _) => RestoreWindow());
        menu.Items.Add("退出并关闭服务", null, (_, _) => ExitFromTray());
        clearPreferenceItem = new ToolStripMenuItem("清除关闭偏好", null, (_, _) => { rememberedAction = null; SavePreference(null); Log("已清除关闭偏好，下次关闭时将再次询问。"); });
        menu.Items.Add(clearPreferenceItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出托盘", null, (_, _) => ExitFromTray());
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += (_, _) => RestoreWindow();
    }

    private async Task BootstrapAsync()
    {
        try
        {
            if (!File.Exists(Path.Combine(root, "main.py"))) throw new InvalidOperationException("未找到 main.py。请将启动器放在项目根目录或项目 launcher 目录中。");
            rememberedAction = LoadPreference();
            var existing = await ProbeAsync(url, TimeSpan.FromSeconds(2), CancellationToken.None);
            if (existing)
            {
                Log("检测到已有服务，将复用该服务，不会在退出时关闭它。");
            }
            else
            {
                var python = FindPython(root) ?? throw new InvalidOperationException("未找到可用的 Python。请安装 Python 3.10 或更高版本，或将便携 Python 放入项目 python\\目录。");
                Log($"使用 Python：{python}");
                if (!await EnsureDependenciesAsync(root, python, CancellationToken.None)) return;
                server = StartServer(root, python);
                ownsServer = true;
                server.OutputDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) Log($"[服务] {e.Data}"); };
                server.ErrorDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) Log($"[服务错误] {e.Data}"); };
                server.BeginOutputReadLine();
                server.BeginErrorReadLine();
                Log("正在等待服务就绪...");
                if (!await WaitForServerAsync(url, TimeSpan.FromSeconds(45), CancellationToken.None)) throw new InvalidOperationException("服务未能在 45 秒内启动，请查看日志。");
            }
            status.Text = "正在打开 Infinite Canvas...";
            await OpenWebViewAsync();
            status.Text = "Infinite Canvas 已就绪";
        }
        catch (Exception ex)
        {
            Log($"[错误] {ex.Message}");
            status.Text = "启动失败";
            MessageBox.Show(ex.Message, LauncherHost.Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private async Task OpenWebViewAsync()
    {
        try
        {
            await webView.EnsureCoreWebView2Async();
            webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
            webView.CoreWebView2.Settings.IsStatusBarEnabled = false;
            webView.CoreWebView2.NavigationCompleted += (_, e) =>
            {
                if (!e.IsSuccess) Log($"[页面] 加载失败：{e.WebErrorStatus}");
            };
            webView.Source = new Uri(url);
            logBox.Visible = false;
            webView.Visible = true;
        }
        catch (WebView2RuntimeNotFoundException)
        {
            throw new InvalidOperationException("未检测到 Microsoft Edge WebView2 Runtime。请安装 WebView2 Runtime 后重新启动；当前不会自动改用外部浏览器。");
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException($"嵌入页面初始化失败：{ex.Message}");
        }
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        if (forceExit) return;
        if (rememberedAction == CloseAction.Tray)
        {
            e.Cancel = true;
            MinimizeToTray();
            return;
        }
        if (rememberedAction == CloseAction.Exit)
        {
            forceExit = true;
            StopOwnedServer();
            return;
        }
        using var dialog = new CloseChoiceForm();
        if (dialog.ShowDialog(form) != DialogResult.OK)
        {
            e.Cancel = true;
            return;
        }
        if (dialog.Remember)
        {
            rememberedAction = dialog.Action;
            SavePreference(rememberedAction);
        }
        if (dialog.Action == CloseAction.Tray)
        {
            e.Cancel = true;
            MinimizeToTray();
        }
        else
        {
            forceExit = true;
            StopOwnedServer();
        }
    }

    private void MinimizeToTray()
    {
        form.Hide();
        tray.Visible = true;
        tray.ShowBalloonTip(1500, LauncherHost.Title, "程序已最小化到系统托盘。", ToolTipIcon.Info);
    }

    private void RestoreWindow()
    {
        form.Show();
        form.WindowState = FormWindowState.Normal;
        form.Activate();
    }

    private void ExitFromTray()
    {
        forceExit = true;
        tray.Visible = false;
        StopOwnedServer();
        form.Close();
    }

    private CloseAction? LoadPreference()
    {
        try
        {
            if (!File.Exists(preferencePath)) return null;
            var value = JsonSerializer.Deserialize<Preference>(File.ReadAllText(preferencePath));
            return value?.Action switch { "exit" => CloseAction.Exit, "tray" => CloseAction.Tray, _ => null };
        }
        catch { return null; }
    }

    private void SavePreference(CloseAction? action)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(preferencePath)!);
            if (action is null) { if (File.Exists(preferencePath)) File.Delete(preferencePath); return; }
            File.WriteAllText(preferencePath, JsonSerializer.Serialize(new Preference { Action = action == CloseAction.Exit ? "exit" : "tray" }));
        }
        catch (Exception ex) { Log($"[提示] 无法保存关闭偏好：{ex.Message}"); }
    }

    private sealed class Preference { public string Action { get; set; } = ""; }

    private void StopOwnedServer()
    {
        if (!ownsServer || server is null) return;
        try { if (!server.HasExited) server.Kill(true); } catch (Exception ex) { Log($"[服务] 停止失败：{ex.Message}"); }
        ownsServer = false;
    }

    private void Log(string message)
    {
        if (form.IsDisposed) return;
        if (form.InvokeRequired) { form.BeginInvoke(() => Log(message)); return; }
        logBox.AppendText($"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}");
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
        if (missing.Count == 0) { Log("依赖检查通过，跳过安装。"); return true; }
        Log($"缺少依赖：{string.Join(", ", missing)}");
        var args = string.Join(" ", missing.Select(Quote));
        var packages = Path.Combine(root, "packages");
        if (Directory.Exists(packages))
        {
            Log("尝试从本地 packages 离线安装...");
            if (await RunAsync(python, $"-m pip install --no-index --find-links {Quote(packages)} {args}", root, token, true)) return true;
            Log("离线安装未满足全部依赖，改用在线安装...");
        }
        if (!await RunAsync(python, "-m pip --version", root, token, false))
        {
            var bootstrap = Path.Combine(root, "get-pip.py");
            if (!File.Exists(bootstrap) || !await RunAsync(python, $"{Quote(bootstrap)} --quiet", root, token, true)) { Log("[错误] pip 安装失败。"); return false; }
        }
        if (!await RunAsync(python, $"-m pip install {args}", root, token, true)) { Log("[错误] 在线依赖安装失败，请检查网络或手动运行 安装依赖.bat。"); return false; }
        return true;
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
                    if (!string.IsNullOrWhiteSpace(line)) Log($"[安装] {line}");
                }
                else await Task.Delay(80, token);
            }
            if (output)
            {
                var rest = await p.StandardOutput.ReadToEndAsync(token);
                if (!string.IsNullOrWhiteSpace(rest)) Log($"[安装] {rest.Trim()}");
                var errors = await p.StandardError.ReadToEndAsync(token);
                if (!string.IsNullOrWhiteSpace(errors)) Log($"[安装错误] {errors.Trim()}");
            }
            return p.ExitCode == 0;
        }
        catch (Exception ex) { if (output) Log($"[安装错误] {ex.Message}"); return false; }
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

    private sealed class CloseChoiceForm : Form
    {
        private readonly RadioButton exit = new() { Text = "退出并关闭服务", AutoSize = true, Location = new Point(24, 55), Checked = true };
        private readonly RadioButton tray = new() { Text = "最小化到系统托盘", AutoSize = true, Location = new Point(24, 90) };
        private readonly CheckBox remember = new() { Text = "记住我的选择", AutoSize = true, Location = new Point(24, 132) };
        public CloseAction Action => exit.Checked ? CloseAction.Exit : CloseAction.Tray;
        public bool Remember => remember.Checked;
        public CloseChoiceForm()
        {
            Text = "关闭 Infinite Canvas";
            ClientSize = new Size(340, 205);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterParent;
            MinimizeBox = false;
            MaximizeBox = false;
            ShowInTaskbar = false;

            var content = new Panel { Dock = DockStyle.Fill, Padding = new Padding(24, 20, 24, 0) };
            content.Controls.Add(new Label { Text = "关闭窗口时要如何处理？", AutoSize = true, Location = new Point(24, 20) });
            content.Controls.Add(exit);
            content.Controls.Add(tray);
            content.Controls.Add(remember);

            var actions = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                Height = 48,
                FlowDirection = FlowDirection.RightToLeft,
                WrapContents = false,
                Padding = new Padding(0, 8, 16, 8)
            };
            var ok = new Button { Text = "确定", DialogResult = DialogResult.OK, Width = 86, Height = 30 };
            var cancel = new Button { Text = "取消", DialogResult = DialogResult.Cancel, Width = 86, Height = 30, Margin = new Padding(0, 0, 8, 0) };
            actions.Controls.Add(ok);
            actions.Controls.Add(cancel);

            Controls.Add(content);
            Controls.Add(actions);
            AcceptButton = ok;
            CancelButton = cancel;
        }
    }
}

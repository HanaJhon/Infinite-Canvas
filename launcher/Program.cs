using System.Diagnostics;
using System.Drawing;
using System.Net.Http;
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

sealed class LauncherHost : IDisposable
{
    public const string Title = "CANVAS · LOCHOU LAUNCHER";
    private readonly string root;
    private readonly string appUrl;
    private readonly Form form;
    private readonly Icon applicationIcon;
    private readonly WebView2 webView;
    private readonly NotifyIcon tray;
    private readonly string preferencePath;
    private readonly string apiProvidersPath;
    private readonly string apiEnvPath;
    private Process? server;
    private bool ownsServer;
    private bool forceExit;
    private bool disposed;
    private bool keepRunningInBackground = true;
    private bool launchAtStartup = false;

    public Form Form => form;

    public LauncherHost(string projectRoot, string canvasUrl)
    {
        root = projectRoot;
        appUrl = canvasUrl;
        preferencePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "InfiniteCanvasLauncher", "preferences.json");
        apiProvidersPath = Path.Combine(root, "data", "api_providers.json");
        apiEnvPath = Path.Combine(root, "API", ".env");

        applicationIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? (Icon)SystemIcons.Application.Clone();
        form = new Form
        {
            Text = LauncherHost.Title,
            Width = 1440,
            Height = 920,
            MinimumSize = new Size(1024, 680),
            StartPosition = FormStartPosition.CenterScreen,
            BackColor = Color.FromArgb(9, 10, 15),
            Icon = applicationIcon
        };

        webView = new WebView2 { Dock = DockStyle.Fill };
        form.Controls.Add(webView);
        form.FormClosing += OnFormClosing;
        form.Shown += async (_, _) => await InitializeLauncherAsync();

        tray = new NotifyIcon { Icon = applicationIcon, Text = LauncherHost.Title, Visible = false };
        var menu = new ContextMenuStrip();
        menu.Items.Add("打开启动器/画布", null, (_, _) => RestoreWindow());
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

            // Resolve dist directory across various single-file extract and project directory structures
            var candidatePaths = new[]
            {
                Path.Combine(AppContext.BaseDirectory, "dist"),
                Path.Combine(AppContext.BaseDirectory, "launcher", "dist"),
                Path.Combine(root, "launcher", "dist"),
                Path.Combine(root, "dist"),
                Path.Combine(root, "dist", "dist")
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
        }
        catch (Exception ex)
        {
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

            object? result = null;
            bool success = true;
            string error = "";

            try
            {
                switch (type)
                {
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
                    case "SAVE_PREFERENCES":
                        HandleSavePreferences(payload);
                        result = new { saved = true };
                        break;
                    case "CREATE_SHORTCUT":
                        HandleCreateShortcut();
                        result = new { created = true };
                        break;
                    case "TEST_PING":
                        result = new { latency = new Random().Next(25, 45) };
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
            var response = JsonSerializer.Serialize(new
            {
                requestId,
                success,
                result,
                error
            });
            webView.CoreWebView2.PostWebMessageAsJson(response);
        }
        catch (Exception ex)
        {
            SendLog($"[Bridge Error] {ex.Message}");
        }
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

    private async Task<object> HandleStartServerAsync()
    {
        SendLog("[启动] 正在检查 Infinite Canvas 环境与依赖...");

        var existing = await ProbeAsync(appUrl, TimeSpan.FromSeconds(2), CancellationToken.None);
        if (existing)
        {
            SendLog("检测到已有后端服务 (127.0.0.1:3000)，直接连接...");
            // Navigate webview to Canvas
            webView.BeginInvoke(() => webView.Source = new Uri(appUrl));
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

        SendLog("🚀 服务就绪，正在无缝跳转至无限画布主界面...");
        webView.BeginInvoke(() => webView.Source = new Uri(appUrl));
        return new { running = true, url = appUrl };
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
        if (missing.Count == 0) { SendLog("依赖检查全部通过，跳过安装。"); return true; }
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

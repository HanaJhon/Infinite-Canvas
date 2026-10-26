using System.Collections.Concurrent;
using System.Net;
using System.Text;
using System.Text.Json;

/// <summary>
/// 启动器界面的本地 HTTP 宿主（2026-10-26）。
///
/// 🚨 为什么这么做：启动器原来用 WebView2 内嵌 dist/launcher 那套 HTML 界面，但老板本机
///    WebView2 运行时损坏（0x800736B1），而原生 WinForms 界面又还原不出原来的设计。
///    所以改成：**启动器自己起一个本地 HTTP 服务提供原界面，用系统默认浏览器打开**。
///    好处是界面 100% 不变，且完全不依赖 WebView2 / Edge。
///
/// 通信协议（与 WebView2 的 postMessage 一一对应）：
///   JS → C#：`POST /api/bridge`，body = 原来 postMessage 的那份 JSON（含 type / payload / requestId）
///            响应 = 原来 PostWebMessageAsJson 的那份 JSON（含 requestId / success / result / error）
///   C# → JS：`GET /api/poll?since=N` 长轮询拿增量事件（LOG / UPDATE_PROGRESS / ROLLBACK_PROGRESS），
///            返回 `{ cursor, events: [ ... ] }`。用轮询而不是 SSE —— HttpListener 上 SSE 要自己
///            管连接生命周期，轮询更简单也更不容易卡。
/// </summary>
internal sealed class LauncherHttpHost : IDisposable
{
    public const int Port = 5199;
    public static string BaseUrl => $"http://127.0.0.1:{Port}/";

    private readonly HttpListener _listener = new();
    private readonly string _webRoot;
    private readonly Func<string, Task<string>> _bridge;
    private readonly ConcurrentQueue<string> _events = new();
    private readonly CancellationTokenSource _cts = new();
    private long _cursor;
    private bool _disposed;

    /// <summary>给界面推一条事件（原来 SendToWebView / SendLog 的等价物）。</summary>
    public void Push(string json)
    {
        _events.Enqueue(json);
        // 队列太长说明浏览器那边根本没在轮询（比如标签被关了），丢掉旧的防止内存涨
        while (_events.Count > 500) _events.TryDequeue(out _);
    }

    public LauncherHttpHost(string webRoot, Func<string, Task<string>> bridge)
    {
        _webRoot = webRoot;
        _bridge = bridge;
        _listener.Prefixes.Add(BaseUrl);
    }

    public void Start()
    {
        _listener.Start();
        _ = Task.Run(AcceptLoopAsync);
    }

    private async Task AcceptLoopAsync()
    {
        while (!_cts.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try
            {
                ctx = await _listener.GetContextAsync();
            }
            catch
            {
                break; // 监听器被关掉
            }
            _ = Task.Run(() => HandleAsync(ctx));
        }
    }

    private async Task HandleAsync(HttpListenerContext ctx)
    {
        try
        {
            var req = ctx.Request;
            var path = (req.Url?.AbsolutePath ?? "/").TrimEnd('/');
            if (path.Length == 0) path = "/";

            if (req.HttpMethod == "POST" && path == "/api/bridge")
            {
                string body;
                using (var sr = new StreamReader(req.InputStream, Encoding.UTF8))
                    body = await sr.ReadToEndAsync();
                var resp = await _bridge(body);
                await WriteTextAsync(ctx, resp, "application/json; charset=utf-8");
                return;
            }

            if (req.HttpMethod == "GET" && path == "/api/poll")
            {
                var sinceStr = req.QueryString["since"];
                long since = long.TryParse(sinceStr, out var v) ? v : 0;
                // 最多等 20 秒，来新事件就立刻返回
                var deadline = DateTime.UtcNow.AddSeconds(20);
                var batch = new List<string>();
                while (DateTime.UtcNow < deadline)
                {
                    while (_events.TryDequeue(out var item))
                    {
                        batch.Add(item);
                        _cursor++;
                        if (batch.Count >= 50) break;
                    }
                    if (batch.Count > 0) break;
                    await Task.Delay(150);
                }
                var payload = JsonSerializer.Serialize(new { cursor = _cursor, events = batch });
                await WriteTextAsync(ctx, payload, "application/json; charset=utf-8");
                return;
            }

            // 静态文件
            var rel = path == "/" ? "index.html" : path.TrimStart('/');
            var full = Path.GetFullPath(Path.Combine(_webRoot, rel));
            if (!full.StartsWith(Path.GetFullPath(_webRoot), StringComparison.OrdinalIgnoreCase))
            {
                ctx.Response.StatusCode = 403;
                ctx.Response.Close();
                return;
            }
            if (!File.Exists(full))
            {
                ctx.Response.StatusCode = 404;
                ctx.Response.Close();
                return;
            }
            var bytes = await File.ReadAllBytesAsync(full);
            await WriteBytesAsync(ctx, bytes, MimeOf(full));
        }
        catch
        {
            try { ctx.Response.Abort(); } catch { }
        }
    }

    private static string MimeOf(string path) => Path.GetExtension(path).ToLowerInvariant() switch
    {
        ".html" => "text/html; charset=utf-8",
        ".js" => "text/javascript; charset=utf-8",
        ".css" => "text/css; charset=utf-8",
        ".json" => "application/json; charset=utf-8",
        ".svg" => "image/svg+xml",
        ".png" => "image/png",
        ".jpg" or ".jpeg" => "image/jpeg",
        ".ico" => "image/x-icon",
        ".woff" => "font/woff",
        ".woff2" => "font/woff2",
        ".ttf" => "font/ttf",
        _ => "application/octet-stream",
    };

    private static async Task WriteTextAsync(HttpListenerContext ctx, string text, string mime)
        => await WriteBytesAsync(ctx, Encoding.UTF8.GetBytes(text), mime);

    private static async Task WriteBytesAsync(HttpListenerContext ctx, byte[] bytes, string mime)
    {
        ctx.Response.StatusCode = 200;
        ctx.Response.ContentType = mime;
        ctx.Response.ContentLength64 = bytes.Length;
        // 本地界面，禁缓存，改完刷新立刻生效
        ctx.Response.Headers["Cache-Control"] = "no-store";
        await ctx.Response.OutputStream.WriteAsync(bytes);
        ctx.Response.Close();
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        try { _cts.Cancel(); } catch { }
        try { _listener.Stop(); } catch { }
        try { _listener.Close(); } catch { }
        _cts.Dispose();
    }
}

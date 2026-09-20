using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

/// <summary>
/// 更新执行器（applier）。
///
/// 为什么是「exe 自己再跑一遍」而不是生成 .cmd / .ps1：
/// 安装路径可能含中文（本机就是 D:\工作\无限画布\...）。Windows 批处理与
/// PowerShell 脚本在中文路径下极易因编码问题毁掉文件名，所以不生成脚本。
/// 做法是启动器把**自己复制一份**到 &lt;root&gt;/data/_apply_update_&lt;pid&gt;.exe，
/// 以 <c>--apply-update</c> 派生一个脱离的进程，然后启动器自己退出。
/// 副本可执行文件位于 data/ 下，因此它去覆盖安装目录里的正本 exe 不会被
/// 「文件正在使用」挡住（Windows 不允许覆盖正在运行的映像文件）。
/// 副本用完无法自删，由下次启动的启动器清理 data/_apply_update_*.exe。
/// </summary>
internal static class UpdateApplier
{
    private const string ManifestEntryName = "release-manifest.json";

    /// <summary>剪枝时的二次防线：这些顶层目录永远不许删。</summary>
    private static readonly string[] ForbiddenRoots =
        { "data", "assets", "output", "API", ".git", ".workbuddy-ai" };

    private static string LogPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "InfiniteCanvasLauncher", "update.log");

    private static readonly object LogLock = new();

    public static bool IsApplyMode(string[] args) =>
        args.Length > 0 && args[0].Equals("--apply-update", StringComparison.OrdinalIgnoreCase);

    /// <summary>入口。返回进程退出码。</summary>
    public static int Run(string[] args)
    {
        try
        {
            if (args.Length < 5)
            {
                Log("参数不足。用法：--apply-update <zip> <destDir> <waitPids> <launchExe>");
                return 2;
            }

            var zipPath = args[1];
            var destDir = Path.GetFullPath(args[2]);
            var waitPids = args[3]
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(s => int.TryParse(s, out var v) ? v : -1)
                .Where(v => v > 0)
                .ToArray();
            var launchExe = args[4];

            Log("================ 开始应用更新 ================");
            Log($"包：{zipPath}");
            Log($"目标：{destDir}");
            Log($"等待进程退出：{(waitPids.Length == 0 ? "（无）" : string.Join(", ", waitPids))}");

            if (!File.Exists(zipPath))
            {
                Log("[中止] 更新包不存在");
                return 3;
            }
            if (!Directory.Exists(destDir))
            {
                Log("[中止] 目标目录不存在");
                return 3;
            }

            // ① 等启动器与服务都退出，否则文件被占用，替换会半途失败
            if (!WaitForExit(waitPids, TimeSpan.FromSeconds(120)))
            {
                Log("[中止] 等待进程退出超时，未做任何改动");
                return 4;
            }

            // ② 读包内清单（唯一权威来源）
            var manifest = ReadManifest(zipPath, out var manifestError);
            if (manifest is null)
            {
                Log($"[中止] 读不到包内清单：{manifestError}");
                return 5;
            }
            Log($"清单：version={manifest.Version} kind={manifest.Kind} 文件数={manifest.Files.Count} " +
                $"可剪枝目录=[{string.Join(", ", manifest.PruneRoots)}]");

            if (!string.Equals(manifest.Kind, "full", StringComparison.OrdinalIgnoreCase))
            {
                Log("[中止] 只支持完整包（增量包需要额外合并逻辑，尚未实现）");
                return 5;
            }

            // ③ 备份「将要被覆盖的旧文件」—— 只备份内容真的变了的，避免每次几 GB
            var backupDir = BackupChangedFiles(destDir, manifest, out var backupCount);
            Log($"已备份 {backupCount} 个将被覆盖的文件 -> {backupDir ?? "（无需备份）"}");

            // ④ 解压覆盖
            var written = ExtractOverwrite(zipPath, destDir);
            Log($"已写入 {written} 个文件");

            // ⑤ 剪掉旧版残留（只在程序独占目录内）
            var pruned = PruneStaleFiles(destDir, manifest);
            Log($"已清理 {pruned} 个旧版残留文件");

            // ⑥ 收尾
            TryDelete(zipPath);
            TrimBackups(destDir, 10);

            Log("更新完成，正在重新启动启动器 ...");
            Relaunch(launchExe, destDir);
            Log("================ 更新流程结束 ================");
            return 0;
        }
        catch (Exception ex)
        {
            Log($"[异常] {ex}");
            return 1;
        }
    }

    // ------------------------------------------------------------------
    // 各步骤
    // ------------------------------------------------------------------

    private static bool WaitForExit(int[] pids, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        foreach (var pid in pids)
        {
            while (true)
            {
                Process? p = null;
                try { p = Process.GetProcessById(pid); }
                catch (ArgumentException) { break; }   // 进程已不存在
                catch { break; }

                p.Dispose();
                if (DateTime.UtcNow > deadline)
                {
                    Log($"  等待 PID {pid} 超时");
                    return false;
                }
                Thread.Sleep(300);
            }
            Log($"  PID {pid} 已退出");
        }
        // 让文件句柄再松一下
        Thread.Sleep(600);
        return true;
    }

    private static PackageManifest? ReadManifest(string zipPath, out string error)
    {
        error = "";
        try
        {
            using var zip = ZipFile.OpenRead(zipPath);
            var entry = zip.Entries.FirstOrDefault(e =>
                e.FullName.EndsWith("/" + ManifestEntryName, StringComparison.OrdinalIgnoreCase) ||
                e.FullName.Equals(ManifestEntryName, StringComparison.OrdinalIgnoreCase));
            if (entry is null)
            {
                error = $"包内没有 {ManifestEntryName}";
                return null;
            }
            using var stream = entry.Open();
            var doc = JsonSerializer.Deserialize<PackageManifest>(stream);
            if (doc is null)
            {
                error = "清单反序列化为空";
                return null;
            }
            return doc;
        }
        catch (Exception ex)
        {
            error = ex.Message;
            return null;
        }
    }

    /// <summary>把「内容将要变化」的现有文件复制到 data/update_backups/&lt;时间戳&gt;/。返回备份目录与文件数。</summary>
    private static string? BackupChangedFiles(string destDir, PackageManifest manifest, out int count)
    {
        count = 0;
        var backupRoot = Path.Combine(destDir, "data", "update_backups");
        string? backupDir = null;

        foreach (var (rel, expectedHash) in manifest.Files)
        {
            var target = SafeCombine(destDir, rel);
            if (target is null || !File.Exists(target)) continue;

            var actual = Sha256File(target);
            if (string.Equals(actual, expectedHash, StringComparison.OrdinalIgnoreCase)) continue;

            backupDir ??= Path.Combine(backupRoot, DateTime.Now.ToString("yyyyMMdd-HHmmss"));
            var dest = Path.Combine(backupDir, rel.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
            File.Copy(target, dest, overwrite: true);
            count++;
        }

        if (backupDir is null) return null;

        var meta = JsonSerializer.Serialize(new
        {
            kind = "launcher-apply",
            target_version = manifest.Version,
            applied_at = DateTime.Now.ToString("o"),
            replaced_files = count,
        }, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(Path.Combine(backupDir, "apply-info.json"), meta, new UTF8Encoding(false));
        return backupDir;
    }

    /// <summary>把 zip 内容覆盖到 destDir，剥掉包内顶层目录。返回写入文件数。</summary>
    private static int ExtractOverwrite(string zipPath, string destDir)
    {
        var written = 0;
        using var zip = ZipFile.OpenRead(zipPath);
        foreach (var entry in zip.Entries)
        {
            if (entry.FullName.EndsWith("/", StringComparison.Ordinal)) continue;

            var rel = StripTopSegment(entry.FullName);
            if (string.IsNullOrEmpty(rel)) continue;

            var target = SafeCombine(destDir, rel);
            if (target is null)
            {
                Log($"  [跳过] 包内路径越界：{entry.FullName}");
                continue;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            // 直接覆盖：更新包内只有程序文件，用户数据不在其中
            entry.ExtractToFile(target, overwrite: true);
            written++;
        }
        return written;
    }

    /// <summary>删掉 prune_roots 里「新版清单没有」的文件。返回删除数。</summary>
    private static int PruneStaleFiles(string destDir, PackageManifest manifest)
    {
        var pruned = 0;
        foreach (var rootName in manifest.PruneRoots)
        {
            var name = rootName.Trim().Trim('/', '\\');
            if (string.IsNullOrEmpty(name)) continue;
            if (ForbiddenRoots.Contains(name, StringComparer.OrdinalIgnoreCase))
            {
                Log($"  [安全] 剪枝目录 {name} 在禁用名单里，跳过");
                continue;
            }

            var rootDir = Path.Combine(destDir, name);
            if (!Directory.Exists(rootDir)) continue;

            foreach (var file in Directory.EnumerateFiles(rootDir, "*", SearchOption.AllDirectories))
            {
                var rel = Path.GetRelativePath(destDir, file).Replace('\\', '/');
                if (manifest.Files.ContainsKey(rel)) continue;
                if (TryDelete(file)) pruned++;
            }
        }
        return pruned;
    }

    private static void TrimBackups(string destDir, int keep)
    {
        try
        {
            var backupRoot = Path.Combine(destDir, "data", "update_backups");
            if (!Directory.Exists(backupRoot)) return;
            var dirs = new DirectoryInfo(backupRoot).GetDirectories()
                .OrderByDescending(d => d.Name).ToList();
            foreach (var d in dirs.Skip(keep))
            {
                try { d.Delete(recursive: true); } catch { /* 留着无害 */ }
            }
        }
        catch { /* 备份清理失败不影响更新结果 */ }
    }

    private static void Relaunch(string launchExe, string destDir)
    {
        try
        {
            if (!File.Exists(launchExe))
            {
                Log($"  [警告] 找不到启动器：{launchExe}，请手动打开");
                return;
            }
            var psi = new ProcessStartInfo
            {
                FileName = launchExe,
                WorkingDirectory = destDir,
                UseShellExecute = true,
            };
            Process.Start(psi);
            Log($"  已拉起 {launchExe}");
        }
        catch (Exception ex)
        {
            Log($"  [警告] 拉起启动器失败：{ex.Message}");
        }
    }

    // ------------------------------------------------------------------
    // 工具
    // ------------------------------------------------------------------

    /// <summary>拼路径并校验没越出 baseDir（防 zip 里的 ../ 穿越）。越界返回 null。</summary>
    private static string? SafeCombine(string baseDir, string rel)
    {
        var full = Path.GetFullPath(Path.Combine(baseDir, rel.Replace('/', Path.DirectorySeparatorChar)));
        var root = Path.GetFullPath(baseDir)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        return full.StartsWith(root, StringComparison.OrdinalIgnoreCase) ? full : null;
    }

    private static string StripTopSegment(string entryName)
    {
        var idx = entryName.IndexOf('/');
        return idx < 0 ? entryName : entryName[(idx + 1)..];
    }

    private static string Sha256File(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static bool TryDelete(string path)
    {
        try { File.Delete(path); return true; }
        catch { return false; }
    }

    private static void Log(string message)
    {
        var line = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}";
        lock (LogLock)
        {
            try
            {
                var dir = Path.GetDirectoryName(LogPath);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                File.AppendAllText(LogPath, line + Environment.NewLine, new UTF8Encoding(false));
            }
            catch { /* 日志写不进去也不能让更新失败 */ }
        }
    }

    private sealed class PackageManifest
    {
        [System.Text.Json.Serialization.JsonPropertyName("version")]
        public string Version { get; set; } = "";

        [System.Text.Json.Serialization.JsonPropertyName("kind")]
        public string Kind { get; set; } = "";

        [System.Text.Json.Serialization.JsonPropertyName("prune_roots")]
        public List<string> PruneRoots { get; set; } = new();

        [System.Text.Json.Serialization.JsonPropertyName("files")]
        public Dictionary<string, string> Files { get; set; } = new();
    }
}

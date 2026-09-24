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
///
/// <para><b>恢复点（restore point）与 format 2 清单</b></para>
/// 本执行器与网页端 <c>main.py</c> 共用同一个恢复点目录
/// <c>&lt;root&gt;/data/update_backups/&lt;时间戳&gt;/</c>，因此两边**必须用同一种清单格式**，
/// 否则会出现「网页端回退启动器做的更新时静默漏掉一半文件」。清单固定为
/// <c>manifest.json</c>（<c>format: 2</c>），字段与 main.py 的
/// <c>create_update_backup</c> 对齐：
/// <list type="bullet">
///   <item><c>root_files</c>：每个受影响的非 static 文件 → <c>{existed}</c>。
///         <c>existed=false</c> 表示「更新前不存在」（= 本次新增），回退时要删掉它。</item>
///   <item><c>static_snapshot</c>：<c>{exists, complete, file_count}</c>。
///         <b><c>complete=true</c> 才允许回退时整目录 rmtree+copytree</b>；
///         否则只能逐文件复制 —— 早期版本（本文件旧实现 / legacy 备份）只备份
///         「变更过的」static 文件，若被整目录替换会把 static 里其余文件全删掉。</item>
///   <item><c>affected_files</c>：受影响文件清单，供 UI 展示。</item>
/// </list>
/// </summary>
internal static class UpdateApplier
{
    private const string ManifestEntryName = "release-manifest.json";

    /// <summary>恢复点清单文件名。必须与 main.py 的 <c>UPDATE_BACKUP_MANIFEST</c> 一致。</summary>
    private const string BackupManifestName = "manifest.json";

    /// <summary>恢复点根目录下**不是**用户文件的元数据文件，回退时绝不能还原到安装目录。</summary>
    private static readonly string[] BackupMetadataFiles =
        { BackupManifestName, "apply-info.json" };

    /// <summary>剪枝时的二次防线：这些顶层目录永远不许删。</summary>
    private static readonly string[] ForbiddenRoots =
        { "data", "assets", "output", "API", ".git", ".workbuddy-ai" };

    /// <summary>保留的恢复点数量上限（与 main.py 的 UPDATE_BACKUP_RETENTION 一致）。</summary>
    private const int BackupRetention = 10;

    private static string LogPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "InfiniteCanvasLauncher", "update.log");

    private static readonly object LogLock = new();

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public static bool IsApplyMode(string[] args) =>
        args.Length > 0 && args[0].Equals("--apply-update", StringComparison.OrdinalIgnoreCase);

    public static bool IsRollbackMode(string[] args) =>
        args.Length > 0 && args[0].Equals("--rollback", StringComparison.OrdinalIgnoreCase);

    // ==================================================================
    // ① 应用更新
    // ==================================================================

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
            var waitPids = ParsePids(args[3]);
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

            // 增量包与完整包的差别：
            //  - 增量包 (delta) 只包含「相对上一版的变更文件」，清单里的 files 仍是全集。
            //    所以【不能剪枝】（剪枝会按全集去删其余文件，把整个安装清空）；
            //    只覆盖包内那几个文件，并按 manifest.deleted 删除被移除的文件。
            //  - 完整包 (full) 覆盖全部文件，再剪掉 prune_roots 内的旧残留。
            var isDelta = string.Equals(manifest.Kind, "delta", StringComparison.OrdinalIgnoreCase);
            if (!isDelta && !string.Equals(manifest.Kind, "full", StringComparison.OrdinalIgnoreCase))
            {
                Log($"[中止] 不支持的包类型：{manifest.Kind}（只支持 full / delta）");
                return 5;
            }
            Log(isDelta
                ? "检测到增量包（delta）：仅覆盖变更文件，不执行剪枝。"
                : "检测到完整包（full）：备份 → 覆盖 → 剪枝。");

            // ③ 先算出「将要被删除的文件」，再建恢复点 —— 顺序不能反：
            //    恢复点必须包含这些文件，否则回退时补不回来。
            var zipRels = GetZipEntryRels(zipPath);
            var deleteList = isDelta
                ? manifest.Deleted.Where(r => !string.IsNullOrWhiteSpace(r)).ToList()
                : CollectStaleFiles(destDir, manifest);
            Log(deleteList.Count > 0
                ? $"本次将删除 {deleteList.Count} 个文件（已纳入恢复点）"
                : "本次没有要删除的文件");

            // ③.5 预检：确认要覆盖的文件现在都写得进去。
            //      被占用就【一个字节都别写】直接中止 —— 写到一半崩掉留下的
            //      「后端新、前端旧」半成品，比干脆不更新更难排查（2026-09-24 踩过两次）。
            var locked = FindLockedTargets(zipPath, destDir);
            if (locked.Count > 0)
            {
                Log($"[中止] 有 {locked.Count} 个文件被占用，无法覆盖。未做任何改动。");
                foreach (var rel in locked.Take(20)) Log($"    {rel}");
                if (locked.Count > 20) Log($"    ...（还有 {locked.Count - 20} 个）");
                Log("       请先退出启动器，并在任务管理器里结束安装目录下的 python.exe（遗留的服务进程），然后重试。");
                return 6;
            }

            // ④ 建恢复点（format 2，与网页端 main.py 完全一致）
            var restorePoint = CreateUpdateRestorePoint(destDir, manifest, isDelta ? zipRels : null, deleteList);
            Log(restorePoint is null
                ? "无需备份（没有文件会被覆盖或删除）"
                : $"已创建恢复点 {Path.GetFileName(restorePoint)}");

            // ⑤ 解压覆盖（只写包内条目；增量包因此天然只更新变更文件）
            var written = ExtractOverwrite(zipPath, destDir, out var failed);
            Log($"已写入 {written} 个文件");

            if (failed.Count > 0)
            {
                // 预检过了却仍写失败：占用是中途才出现的。此时目录已经是半新半旧，
                // 必须从刚建的恢复点整体还原，绝不把半成品安装留给用户。
                Log($"[失败] 有 {failed.Count} 个文件中途被占用，写入失败：");
                foreach (var rel in failed.Take(20)) Log($"    {rel}");
                if (failed.Count > 20) Log($"    ...（还有 {failed.Count - 20} 个）");
                if (restorePoint is not null)
                {
                    Log("正在从恢复点整体还原，避免留下半成品安装 ...");
                    var back = RestoreFromRestorePoint(destDir, restorePoint);
                    Log($"已还原 {back} 个文件（安装目录回到更新前状态）。");
                }
                else
                {
                    Log("[警告] 本次没有可用恢复点，安装目录可能不完整 —— 请用完整包重新安装。");
                }
                Log("[中止] 更新未完成。请关掉启动器与所有服务进程后重试。");
                return 7;
            }

            // ⑥ 删除：增量包按 manifest.deleted；完整包删 prune_roots 内的旧残留
            var deleted = DeleteFiles(destDir, deleteList);
            Log(isDelta
                ? $"已删除 {deleted} 个被移除的文件（增量包）"
                : $"已清理 {deleted} 个旧版残留文件（完整包）");

            // ⑦ 收尾
            TryDelete(zipPath);
            TrimBackups(destDir, BackupRetention);

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

    // ==================================================================
    // ② 回退到某个恢复点
    // ==================================================================

    /// <summary>回退入口。用法：<c>--rollback &lt;恢复点名&gt; &lt;destDir&gt; &lt;waitPids&gt; &lt;launchExe&gt;</c></summary>
    public static int RunRollback(string[] args)
    {
        try
        {
            if (args.Length < 5)
            {
                Log("参数不足。用法：--rollback <backupName> <destDir> <waitPids> <launchExe>");
                return 2;
            }

            var backupName = args[1];
            var destDir = Path.GetFullPath(args[2]);
            var waitPids = ParsePids(args[3]);
            var launchExe = args[4];

            Log("================ 开始版本回退 ================");
            Log($"恢复点：{backupName}");
            Log($"目标：{destDir}");

            if (!Directory.Exists(destDir))
            {
                Log("[中止] 目标目录不存在");
                return 3;
            }

            var backupDir = ResolveBackupDir(destDir, backupName);
            if (backupDir is null || !Directory.Exists(backupDir))
            {
                Log($"[中止] 恢复点不存在或路径不安全：{backupName}");
                return 3;
            }

            if (!WaitForExit(waitPids, TimeSpan.FromSeconds(120)))
            {
                Log("[中止] 等待进程退出超时，未做任何改动");
                return 4;
            }

            var manifest = ReadBackupManifest(backupDir);
            Log(manifest is null
                ? "该恢复点没有 manifest.json（legacy 格式）→ 仅逐文件还原，绝不整目录替换 static。"
                : $"清单：kind={manifest.kind} from={manifest.from_version} target={manifest.target_version} " +
                  $"受影响文件={manifest.affected_files?.Count ?? 0} static完整快照={manifest.static_snapshot?.complete == true}");

            // 先把「当前状态」存成一个安全恢复点 —— 回退本身也是危险操作，
            // 万一退回去的那版更差，用户还能再退回来（与 main.py 的 rollback_safety 一致）。
            var safetyRels = new List<string>();
            var safetyAdded = new List<string>();
            CollectRollbackImpact(backupDir, destDir, manifest, safetyRels, safetyAdded);
            var safetyDir = SnapshotRestorePoint(
                destDir,
                fileRels: safetyRels,
                addedRels: safetyAdded,
                snapshotStatic: Directory.Exists(Path.Combine(destDir, "static")),
                kind: "rollback_safety",
                fromVersion: ReadVersionFile(destDir),
                targetVersion: manifest?.from_version ?? "",
                source: "local-rollback",
                parentBackup: Path.GetFileName(backupDir),
                noteText: $"回退前安全快照（即将还原 {Path.GetFileName(backupDir)}）");
            Log(safetyDir is null
                ? "（未能建立回退前安全快照，继续）"
                : $"已建立回退前安全快照：{Path.GetFileName(safetyDir)}");

            // ---- 还原 ----
            var restored = new List<string>();
            var skipped = new List<string>();
            var removed = new List<string>();

            RestoreStatic(destDir, backupDir, manifest, restored, skipped);

            foreach (var file in Directory.EnumerateFiles(backupDir, "*", SearchOption.AllDirectories))
            {
                var rel = Path.GetRelativePath(backupDir, file).Replace('\\', '/');
                if (rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;   // 上面已处理
                if (IsBackupMetadata(rel)) continue;                                          // 清单本身不能还原到安装目录
                if (IsForbiddenPath(rel)) { skipped.Add(rel); Log($"  [安全] 跳过禁用目录下的文件：{rel}"); continue; }

                var target = SafeCombine(destDir, rel);
                if (target is null) { skipped.Add(rel); Log($"  [跳过] 路径越界：{rel}"); continue; }

                try
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                    CopyFileAtomic(file, target);
                    restored.Add(rel);
                }
                catch (Exception ex)
                {
                    skipped.Add(rel);
                    Log($"  [跳过] 还原失败 {rel}：{ex.Message}");
                }
            }

            // 删掉「更新时新增的」文件 —— 它们在恢复点里被标成 existed=false。
            // legacy 恢复点没有 root_files，这一步自然跳过（只能做部分还原）。
            if (manifest?.root_files is not null)
            {
                foreach (var (rel, state) in manifest.root_files)
                {
                    if (state?.existed != false) continue;
                    if (rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;
                    if (IsBackupMetadata(rel) || IsForbiddenPath(rel)) continue;
                    var target = SafeCombine(destDir, rel);
                    if (target is null || !File.Exists(target)) continue;
                    if (TryDelete(target)) { removed.Add(rel); Log($"  已删除更新新增的文件 {rel}"); }
                }
            }

            TrimBackups(destDir, BackupRetention);

            Log($"回退完成：还原 {restored.Count} 个，删除 {removed.Count} 个，跳过 {skipped.Count} 个。");
            Log($"现在版本：{ReadVersionFile(destDir)}");
            Log("正在重新启动启动器 ...");
            Relaunch(launchExe, destDir);
            Log("================ 回退流程结束 ================");
            return 0;
        }
        catch (Exception ex)
        {
            Log($"[异常] {ex}");
            return 1;
        }
    }

    /// <summary>
    /// 从恢复点还原安装目录（不建「回退前安全快照」、不重启启动器）。
    /// 专用于更新中途失败时把目录还原回去，避免留下半新半旧的半成品安装。
    /// 还原逻辑与 <see cref="RunRollback"/> 保持一致，返回还原的文件数。
    /// </summary>
    private static int RestoreFromRestorePoint(string destDir, string backupDir)
    {
        var manifest = ReadBackupManifest(backupDir);
        var restored = new List<string>();
        var skipped = new List<string>();

        RestoreStatic(destDir, backupDir, manifest, restored, skipped);

        foreach (var file in Directory.EnumerateFiles(backupDir, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(backupDir, file).Replace('\\', '/');
            if (rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;   // 上面已处理
            if (IsBackupMetadata(rel)) continue;                                          // 清单本身不还原
            if (IsForbiddenPath(rel)) { skipped.Add(rel); continue; }

            var target = SafeCombine(destDir, rel);
            if (target is null) { skipped.Add(rel); continue; }

            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                CopyFileAtomic(file, target);
                restored.Add(rel);
            }
            catch (Exception ex)
            {
                skipped.Add(rel);
                Log($"  [跳过] 还原失败 {rel}：{ex.Message}");
            }
        }

        // 删掉「本次更新新增的」文件（恢复点里标成 existed=false 的那些）
        if (manifest?.root_files is not null)
        {
            foreach (var (rel, state) in manifest.root_files)
            {
                if (state?.existed != false) continue;
                if (rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;
                if (IsBackupMetadata(rel) || IsForbiddenPath(rel)) continue;
                var target = SafeCombine(destDir, rel);
                if (target is null || !File.Exists(target)) continue;
                TryDelete(target);
            }
        }

        return restored.Count;
    }

    /// <summary>列出可用于回退的恢复点（供启动器 UI）。按时间倒序。</summary>
    public static List<RestorePointInfo> ListRestorePoints(string destDir)
    {
        var result = new List<RestorePointInfo>();
        try
        {
            var root = Path.Combine(destDir, "data", "update_backups");
            if (!Directory.Exists(root)) return result;

            foreach (var dir in new DirectoryInfo(root).GetDirectories())
            {
                var manifest = ReadBackupManifest(dir.FullName);
                if (manifest is not null && !string.Equals(manifest.state, "ready", StringComparison.OrdinalIgnoreCase))
                    continue;   // 没写完的恢复点不展示（与 main.py 的 state 检查一致）

                // legacy（只有 apply-info.json）→ 从它补出目标版本 / 应用时间 / 受影响文件数，
                // 否则 UI 会退化成「（版本未知）」+ 把 static 与元数据都算进去的虚高文件数。
                var legacy = manifest is null ? ReadLegacyApplyInfo(dir.FullName) : null;
                var legacyCreated = ParseIsoSeconds(legacy?.AppliedAt ?? "");

                result.Add(new RestorePointInfo
                {
                    Name = dir.Name,
                    Kind = manifest?.kind ?? legacy?.Kind ?? "legacy",
                    Format = manifest?.format ?? 1,
                    CreatedAt = manifest?.created_at > 0
                        ? manifest!.created_at
                        : (legacyCreated > 0
                            ? legacyCreated
                            : new DateTimeOffset(dir.LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0),
                    FromVersion = manifest?.from_version ?? "",
                    TargetVersion = manifest?.target_version ?? legacy?.TargetVersion ?? "",
                    AffectedCount = manifest?.affected_files?.Count
                        ?? (legacy?.ReplacedFiles > 0 ? legacy.ReplacedFiles : CountFiles(dir.FullName)),
                    StaticComplete = manifest?.static_snapshot?.complete == true,
                    // legacy 恢复点只能做「部分还原」：没有 root_files，删不掉更新新增的文件
                    Partial = manifest is null,
                });
            }
        }
        catch (Exception ex)
        {
            Log($"[列举恢复点失败] {ex.Message}");
        }
        return result.OrderByDescending(p => p.CreatedAt).ToList();
    }

    // ------------------------------------------------------------------
    // 恢复点创建
    // ------------------------------------------------------------------

    /// <summary>应用更新前建恢复点：备份「将被覆盖的文件 + 将被删除的文件 + 完整 static 快照」。
    /// 没有任何文件会变时返回 null（不产生空恢复点）。</summary>
    private static string? CreateUpdateRestorePoint(
        string destDir, PackageManifest manifest, HashSet<string>? restrictRels, List<string> deleteList)
    {
        var overwritten = new List<string>();
        var added = new List<string>();

        foreach (var (rel, expectedHash) in manifest.Files)
        {
            if (restrictRels is not null && !restrictRels.Contains(rel)) continue;
            if (rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;  // static 走整目录快照
            var target = SafeCombine(destDir, rel);
            if (target is null) continue;

            if (!File.Exists(target)) { added.Add(rel); continue; }                       // 更新会新增它
            if (string.Equals(Sha256File(target), expectedHash, StringComparison.OrdinalIgnoreCase)) continue;
            overwritten.Add(rel);                                                          // 内容会变
        }

        // 将被删除的非 static 文件（回退要能把它们补回来）
        var deletedRoot = deleteList
            .Where(r => !string.IsNullOrEmpty(r) && !r.StartsWith("static/", StringComparison.OrdinalIgnoreCase))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        // static 会不会变？变了才做整目录快照（9MB，代价可忽略，但没必要白拷）
        var staticWillChange = deleteList.Any(r => r.StartsWith("static/", StringComparison.OrdinalIgnoreCase))
            || manifest.Files.Keys.Any(rel =>
                rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)
                && (restrictRels is null || restrictRels.Contains(rel))
                && StaticFileWillChange(destDir, rel, manifest.Files[rel]));

        if (overwritten.Count == 0 && added.Count == 0 && deletedRoot.Count == 0 && !staticWillChange)
            return null;

        return SnapshotRestorePoint(
            destDir,
            fileRels: overwritten.Concat(deletedRoot),
            addedRels: added,
            snapshotStatic: staticWillChange,
            kind: "launcher-apply",
            fromVersion: ReadVersionFile(destDir),
            targetVersion: manifest.Version,
            source: "launcher-update",
            parentBackup: "",
            noteText: $"由启动器更新到 {manifest.Version}（{manifest.Kind} 包）");
    }

    private static bool StaticFileWillChange(string destDir, string rel, string expectedHash)
    {
        var target = SafeCombine(destDir, rel);
        if (target is null || !File.Exists(target)) return true;
        return !string.Equals(Sha256File(target), expectedHash, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>把指定的现存文件 + （可选）完整 static 目录快照成一个 format 2 恢复点。
    /// <paramref name="addedRels"/> 是「当前不存在、但回退后会出现」的文件，在清单里记 <c>existed=false</c>。
    /// 没有任何内容可备份时返回 null。</summary>
    private static string? SnapshotRestorePoint(
        string destDir,
        IEnumerable<string> fileRels,
        IEnumerable<string> addedRels,
        bool snapshotStatic,
        string kind,
        string fromVersion,
        string targetVersion,
        string source,
        string parentBackup,
        string noteText)
    {
        var rootFiles = new Dictionary<string, FileState>(StringComparer.OrdinalIgnoreCase);
        var toCopy = new List<string>();
        foreach (var rel in fileRels)
        {
            var name = NormalizeRel(rel);
            if (name is null || IsBackupMetadata(name) || IsForbiddenPath(name)) continue;
            // static 不进 root_files（与 main.py 的 clean_root_files 一致）：它们由
            // static_snapshot 整目录覆盖，写进 root_files 只会让 existed 语义含糊。
            if (name.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;
            var target = SafeCombine(destDir, name);
            if (target is null || !File.Exists(target)) continue;
            rootFiles[name] = new FileState { existed = true };
            toCopy.Add(name);
        }
        foreach (var rel in addedRels)
        {
            var name = NormalizeRel(rel);
            if (name is null || IsBackupMetadata(name) || IsForbiddenPath(name)) continue;
            if (name.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;
            rootFiles[name] = new FileState { existed = false };
        }

        var staticDir = Path.Combine(destDir, "static");
        var hasStatic = Directory.Exists(staticDir);
        if (toCopy.Count == 0 && rootFiles.Count == 0 && !(snapshotStatic && hasStatic)) return null;

        var backupRoot = Path.Combine(destDir, "data", "update_backups");
        Directory.CreateDirectory(backupRoot);
        // 回退前安全快照带 "rollback-" 前缀 —— 与 main.py 的 next_update_backup_dir("rollback-")
        // 保持一致，UI 才能一眼认出「这是回退时自动存的」。
        var backupDir = UniqueBackupDir(backupRoot, kind == "rollback_safety" ? "rollback-" : "");
        Directory.CreateDirectory(backupDir);

        try
        {
            foreach (var rel in toCopy.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                var src = SafeCombine(destDir, rel)!;
                var dst = Path.Combine(backupDir, rel.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
                File.Copy(src, dst, overwrite: true);
            }

            var staticSnapshot = new StaticSnapshot { exists = hasStatic, complete = false, file_count = 0 };
            if (snapshotStatic && hasStatic)
            {
                var dstStatic = Path.Combine(backupDir, "static");
                CopyDirectory(staticDir, dstStatic);
                staticSnapshot = new StaticSnapshot
                {
                    exists = true,
                    complete = true,                                    // ← 只有这里才允许回退时整目录替换
                    file_count = Directory.EnumerateFiles(dstStatic, "*", SearchOption.AllDirectories).Count(),
                };
            }

            var affected = rootFiles.Keys
                .Concat(staticSnapshot.complete
                    ? Directory.EnumerateFiles(Path.Combine(backupDir, "static"), "*", SearchOption.AllDirectories)
                        .Select(f => "static/" + Path.GetRelativePath(Path.Combine(backupDir, "static"), f).Replace('\\', '/'))
                    : Enumerable.Empty<string>())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(s => s, StringComparer.OrdinalIgnoreCase)
                .ToList();

            var manifest = new RestorePointManifest
            {
                format = 2,
                state = "ready",
                kind = kind,
                created_at = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
                from_version = fromVersion,
                target_version = targetVersion,
                source = source,
                parent_backup = parentBackup,
                update_notes = Notes(targetVersion, noteText),
                root_files = rootFiles,
                static_snapshot = staticSnapshot,
                affected_files = affected,
            };

            File.WriteAllText(
                Path.Combine(backupDir, BackupManifestName),
                JsonSerializer.Serialize(manifest, JsonOpts),
                new UTF8Encoding(false));

            return backupDir;
        }
        catch
        {
            // 恢复点建失败不能留下半个目录（否则会被 UI 当成可用恢复点）
            try { Directory.Delete(backupDir, recursive: true); } catch { }
            throw;
        }
    }

    /// <summary>算出「回退会把哪些文件改动」，用于回退前的安全快照。</summary>
    private static void CollectRollbackImpact(
        string backupDir, string destDir, RestorePointManifest? manifest,
        List<string> fileRels, List<string> addedRels)
    {
        // ① 恢复点里的文件：现存 → 会被覆盖（要存内容）；不存在 → 回退会新建（记 existed=false）
        foreach (var file in Directory.EnumerateFiles(backupDir, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(backupDir, file).Replace('\\', '/');
            if (IsBackupMetadata(rel) || IsForbiddenPath(rel)) continue;
            if (rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;   // 由 snapshotStatic 整体覆盖
            var target = SafeCombine(destDir, rel);
            if (target is null) continue;
            if (File.Exists(target)) fileRels.Add(rel); else addedRels.Add(rel);
        }

        // ② 回退会「删掉」的文件（= 更新时新增的，existed=false）：现在它们存在，要存下来
        if (manifest?.root_files is not null)
        {
            foreach (var (rel, state) in manifest.root_files)
            {
                if (state?.existed != false) continue;
                if (rel.StartsWith("static/", StringComparison.OrdinalIgnoreCase)) continue;
                if (IsBackupMetadata(rel) || IsForbiddenPath(rel)) continue;
                fileRels.Add(rel);
            }
        }
    }

    /// <summary>还原 static 目录。</summary>
    private static void RestoreStatic(
        string destDir, string backupDir, RestorePointManifest? manifest,
        List<string> restored, List<string> skipped)
    {
        var backupStatic = Path.Combine(backupDir, "static");
        if (!Directory.Exists(backupStatic)) return;
        var liveStatic = Path.Combine(destDir, "static");

        // 🚨 只有清单明确声明「完整快照」时才允许整目录替换。
        //    早期实现与 legacy 恢复点只备份「变更过的」static 文件（实测 14~18/74），
        //    整目录替换会把 static 里其余文件全部抹掉 —— 那会直接毁掉整个前端。
        if (manifest?.static_snapshot?.complete == true)
        {
            try
            {
                if (Directory.Exists(liveStatic)) Directory.Delete(liveStatic, recursive: true);
                CopyDirectory(backupStatic, liveStatic);
                restored.Add("static/（整目录快照）");
                Log("  已整目录还原 static/（清单声明为完整快照）");
            }
            catch (Exception ex)
            {
                skipped.Add("static/");
                Log($"  [警告] static 整目录还原失败：{ex.Message}");
            }
            return;
        }

        var count = 0;
        foreach (var file in Directory.EnumerateFiles(backupStatic, "*", SearchOption.AllDirectories))
        {
            var rel = "static/" + Path.GetRelativePath(backupStatic, file).Replace('\\', '/');
            var target = SafeCombine(destDir, rel);
            if (target is null) { skipped.Add(rel); continue; }
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                CopyFileAtomic(file, target);
                restored.Add(rel);
                count++;
            }
            catch (Exception ex)
            {
                skipped.Add(rel);
                Log($"  [跳过] 还原 static 失败 {rel}：{ex.Message}");
            }
        }
        Log($"  已逐文件还原 static/ 共 {count} 个（非完整快照，绝不删除备份外的文件）");
    }

    // ------------------------------------------------------------------
    // 各步骤
    // ------------------------------------------------------------------

    private static int[] ParsePids(string raw) =>
        (raw ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(s => int.TryParse(s, out var v) ? v : -1)
            .Where(v => v > 0)
            .ToArray();

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

    /// <summary>解压前预检「文件是否可写」的轮数 / 间隔。</summary>
    private const int LockCheckAttempts = 6;
    private const int LockCheckDelayMs = 800;

    /// <summary>单个文件解压失败后的退避重试次数 / 间隔。</summary>
    private const int ExtractAttempts = 5;
    private const int ExtractRetryDelayMs = 500;

    /// <summary>包内所有目标文件的相对路径（剥掉顶层目录、跳过目录项与越界项）。</summary>
    private static List<string> EnumerateTargetRels(string zipPath, string destDir)
    {
        var rels = new List<string>();
        using var zip = ZipFile.OpenRead(zipPath);
        foreach (var entry in zip.Entries)
        {
            if (entry.FullName.EndsWith("/", StringComparison.Ordinal)) continue;
            var rel = StripTopSegment(entry.FullName);
            if (string.IsNullOrEmpty(rel)) continue;
            if (SafeCombine(destDir, rel) is null) continue;   // 路径越界
            rels.Add(rel);
        }
        return rels;
    }

    /// <summary>
    /// 预检：解压前确认包内要覆盖的文件现在都写得进去（没被别的进程占用）。
    /// 被占用就【一个字节都别写】直接中止 —— 否则写到一半崩掉会留下
    /// 「后端新、前端旧」的半成品安装，比干脆不更新更难排查（2026-09-24 踩过两次）。
    /// 占用常常是瞬时的（进程正在退出、杀软正在扫描），所以先退避重试几轮。
    /// </summary>
    private static List<string> FindLockedTargets(string zipPath, string destDir)
    {
        var rels = EnumerateTargetRels(zipPath, destDir);
        var locked = new List<string>();
        for (var attempt = 1; attempt <= LockCheckAttempts; attempt++)
        {
            locked = new List<string>();
            foreach (var rel in rels)
            {
                var target = SafeCombine(destDir, rel);
                if (target is null || !File.Exists(target)) continue;   // 新文件不会被占用
                try
                {
                    using var fs = new FileStream(target, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
                }
                catch (IOException) { locked.Add(rel); }
                catch (UnauthorizedAccessException) { locked.Add(rel); }
            }
            if (locked.Count == 0) return locked;
            if (attempt < LockCheckAttempts)
            {
                Log($"  有 {locked.Count} 个文件暂时被占用，{LockCheckDelayMs}ms 后重试（第 {attempt}/{LockCheckAttempts} 轮）...");
                Thread.Sleep(LockCheckDelayMs);
            }
        }
        return locked;
    }

    /// <summary>
    /// 把 zip 内容覆盖到 destDir，剥掉包内顶层目录。返回写入文件数；
    /// 被占用而写不进去的记进 <paramref name="failed"/>。
    /// </summary>
    private static int ExtractOverwrite(string zipPath, string destDir, out List<string> failed)
    {
        failed = new List<string>();
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

            // 直接覆盖：更新包内只有程序文件，用户数据不在其中。
            // 逐个文件退避重试 —— 一次失败就整体中止，会把安装目录留在半新半旧的状态。
            var ok = false;
            for (var attempt = 1; attempt <= ExtractAttempts; attempt++)
            {
                try
                {
                    entry.ExtractToFile(target, overwrite: true);
                    ok = true;
                    break;
                }
                catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
                {
                    if (attempt >= ExtractAttempts) break;
                    Thread.Sleep(ExtractRetryDelayMs);
                }
            }
            if (ok)
            {
                written++;
            }
            else
            {
                failed.Add(rel);
                Log($"  [失败] 无法写入（文件被占用）：{rel}");
            }
        }
        return written;
    }

    /// <summary>算出完整包里 prune_roots 内「新版清单没有」的旧残留（先算不删，好纳入恢复点）。</summary>
    private static List<string> CollectStaleFiles(string destDir, PackageManifest manifest)
    {
        var stale = new List<string>();
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
                stale.Add(rel);
            }
        }
        return stale;
    }

    /// <summary>删除给定相对路径的文件（受 ForbiddenRoots 与越界保护）。返回删除数。</summary>
    private static int DeleteFiles(string destDir, List<string> rels)
    {
        var n = 0;
        foreach (var rel in rels)
        {
            var name = NormalizeRel(rel);
            if (name is null) continue;
            if (IsForbiddenPath(name))
            {
                Log($"  [安全] 拒绝删除禁用目录下的文件：{rel}");
                continue;
            }
            var target = SafeCombine(destDir, name);
            if (target is null || !File.Exists(target)) continue;
            if (TryDelete(target)) { n++; Log($"  已删除 {name}"); }
        }
        return n;
    }

    private static void TrimBackups(string destDir, int keep)
    {
        try
        {
            var backupRoot = Path.Combine(destDir, "data", "update_backups");
            if (!Directory.Exists(backupRoot)) return;
            // ⚠️ 不能按目录名排序：回退安全快照带 "rollback-" 前缀，字母 'r' > '2'，
            //    会让它永远排在最前，结果被裁掉的反而是真正更新的更新恢复点。
            //    按清单里的 created_at（缺失则退回目录 mtime）排序，才与 main.py 一致。
            var dirs = new DirectoryInfo(backupRoot).GetDirectories()
                .OrderByDescending(BackupTimestamp).ToList();
            foreach (var d in dirs.Skip(keep))
            {
                try { d.Delete(recursive: true); } catch { /* 留着无害 */ }
            }
        }
        catch { /* 备份清理失败不影响更新结果 */ }
    }

    private static double BackupTimestamp(DirectoryInfo dir)
    {
        var manifest = ReadBackupManifest(dir.FullName);
        if (manifest is not null && manifest.created_at > 0) return manifest.created_at;
        try { return new DateTimeOffset(dir.LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0; }
        catch { return 0; }
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

    /// <summary>把恢复点名解析成绝对目录，并校验它就在 <c>&lt;destDir&gt;/data/update_backups/</c> 下。</summary>
    private static string? ResolveBackupDir(string destDir, string backupName)
    {
        var name = (backupName ?? "").Trim().Trim('/', '\\');
        if (string.IsNullOrEmpty(name)) return null;
        if (name.Contains('/') || name.Contains('\\') || name.Contains("..")) return null;

        var root = Path.GetFullPath(Path.Combine(destDir, "data", "update_backups"))
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var full = Path.GetFullPath(Path.Combine(root, name));
        if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) return null;
        return full;
    }

    private static string UniqueBackupDir(string backupRoot, string prefix = "")
    {
        var baseName = prefix + DateTime.Now.ToString("yyyyMMdd-HHmmss");
        var candidate = Path.Combine(backupRoot, baseName);
        var suffix = 2;
        while (Directory.Exists(candidate) || File.Exists(candidate))
        {
            candidate = Path.Combine(backupRoot, $"{baseName}-{suffix}");
            suffix++;
        }
        return candidate;
    }

    private static string? NormalizeRel(string? rel)
    {
        var name = (rel ?? "").Replace('\\', '/').Trim().Trim('/');
        if (string.IsNullOrEmpty(name)) return null;
        if (name.Split('/').Any(p => p is "" or "." or "..")) return null;
        return name;
    }

    private static bool IsBackupMetadata(string rel) =>
        BackupMetadataFiles.Contains(rel, StringComparer.OrdinalIgnoreCase);

    private static bool IsForbiddenPath(string rel)
    {
        var top = rel.Split('/', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? "";
        return ForbiddenRoots.Contains(top, StringComparer.OrdinalIgnoreCase);
    }

    private static int CountFiles(string dir)
    {
        try { return Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories).Count(); }
        catch { return 0; }
    }

    private static string ReadVersionFile(string destDir)
    {
        try
        {
            var path = Path.Combine(destDir, "VERSION");
            if (!File.Exists(path)) return "";
            var first = File.ReadAllLines(path).FirstOrDefault(l => !string.IsNullOrWhiteSpace(l));
            return (first ?? "").Trim();
        }
        catch { return ""; }
    }

    private static Dictionary<string, object> Notes(string version, string text) => new()
    {
        ["version"] = version ?? "",
        ["updated_at"] = "",
        ["items"] = new List<object>
        {
            new Dictionary<string, object> { ["type"] = "update", ["text"] = text ?? "" },
        },
    };

    /// <summary>先写临时文件再 <c>os.replace</c> 式替换，避免半截文件覆盖掉好的文件。</summary>
    private static void CopyFileAtomic(string src, string target)
    {
        var tmp = target + ".rollback_tmp";
        File.Copy(src, tmp, overwrite: true);
        if (File.Exists(target)) File.Delete(target);
        File.Move(tmp, target);
    }

    private static void CopyDirectory(string src, string dst)
    {
        Directory.CreateDirectory(dst);
        foreach (var dir in Directory.EnumerateDirectories(src, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(Path.Combine(dst, Path.GetRelativePath(src, dir)));
        }
        foreach (var file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            var target = Path.Combine(dst, Path.GetRelativePath(src, file));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

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

    /// <summary>列出 zip 内所有文件条目（剥掉顶层目录后的相对路径）。用于增量包只备份/只覆盖这些文件。</summary>
    private static HashSet<string> GetZipEntryRels(string zipPath)
    {
        var set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using var zip = ZipFile.OpenRead(zipPath);
        foreach (var e in zip.Entries)
        {
            if (e.FullName.EndsWith("/", StringComparison.Ordinal)) continue;
            var rel = StripTopSegment(e.FullName);
            if (!string.IsNullOrEmpty(rel)) set.Add(rel);
        }
        return set;
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

    // ------------------------------------------------------------------
    // DTO
    // ------------------------------------------------------------------

    /// <summary>供启动器 UI 展示的恢复点信息。</summary>
    internal sealed class RestorePointInfo
    {
        public string Name { get; set; } = "";
        public string Kind { get; set; } = "";
        public int Format { get; set; }
        public double CreatedAt { get; set; }
        public string FromVersion { get; set; } = "";
        public string TargetVersion { get; set; } = "";
        public int AffectedCount { get; set; }
        public bool StaticComplete { get; set; }
        /// <summary>true = legacy 恢复点，只能做部分还原（删不掉更新新增的文件）。</summary>
        public bool Partial { get; set; }
    }

    /// <summary>format 2 恢复点清单（与 main.py 的 create_update_backup 对齐）。</summary>
    private sealed class RestorePointManifest
    {
        public int format { get; set; } = 2;
        public string state { get; set; } = "ready";
        public string kind { get; set; } = "";
        public double created_at { get; set; }
        public string from_version { get; set; } = "";
        public string target_version { get; set; } = "";
        public string source { get; set; } = "";
        public string parent_backup { get; set; } = "";
        public Dictionary<string, object> update_notes { get; set; } = new();
        public Dictionary<string, FileState> root_files { get; set; } = new();
        public StaticSnapshot static_snapshot { get; set; } = new();
        public List<string> affected_files { get; set; } = new();
    }

    private sealed class FileState
    {
        public bool existed { get; set; }
    }

    private sealed class StaticSnapshot
    {
        public bool exists { get; set; }
        /// <summary>true 才允许回退时整目录 rmtree+copytree。legacy 恢复点为 false。</summary>
        public bool complete { get; set; }
        public int file_count { get; set; }
    }

    private static RestorePointManifest? ReadBackupManifest(string backupDir)
    {
        try
        {
            var path = Path.Combine(backupDir, BackupManifestName);
            if (!File.Exists(path)) return null;
            return JsonSerializer.Deserialize<RestorePointManifest>(File.ReadAllText(path));
        }
        catch { return null; }
    }

    /// <summary>legacy 恢复点的清单（老启动器写的 apply-info.json）。
    /// 它只有 target_version / applied_at / replaced_files —— **没有 from_version**，
    /// 且**只备份被覆盖的文件**（没有完整 static 快照）→ 只能「部分还原」。
    /// ⚠️ 不读它的话，UI 上这些恢复点会显示成「（版本未知）」且文件数虚高（把 static 和元数据都算进去）。</summary>
    private sealed class LegacyApplyInfo
    {
        [System.Text.Json.Serialization.JsonPropertyName("kind")]
        public string Kind { get; set; } = "";

        [System.Text.Json.Serialization.JsonPropertyName("target_version")]
        public string TargetVersion { get; set; } = "";

        [System.Text.Json.Serialization.JsonPropertyName("applied_at")]
        public string AppliedAt { get; set; } = "";

        [System.Text.Json.Serialization.JsonPropertyName("replaced_files")]
        public int ReplacedFiles { get; set; }
    }

    private static LegacyApplyInfo? ReadLegacyApplyInfo(string backupDir)
    {
        try
        {
            var path = Path.Combine(backupDir, "apply-info.json");
            if (!File.Exists(path)) return null;
            return JsonSerializer.Deserialize<LegacyApplyInfo>(File.ReadAllText(path));
        }
        catch { return null; }
    }

    /// <summary>ISO8601 → unix 秒；解析不出来返回 0。</summary>
    private static double ParseIsoSeconds(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return 0;
        return DateTimeOffset.TryParse(text, System.Globalization.CultureInfo.InvariantCulture,
            System.Globalization.DateTimeStyles.RoundtripKind, out var dt)
            ? dt.ToUnixTimeMilliseconds() / 1000.0
            : 0;
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

        /// <summary>增量包里被移除的文件（相对路径）。执行器会把这些从安装目录删掉。仅 delta 使用。</summary>
        [System.Text.Json.Serialization.JsonPropertyName("deleted")]
        public List<string> Deleted { get; set; } = new();
    }
}

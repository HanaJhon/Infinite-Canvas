using System.Text.RegularExpressions;

/// <summary>
/// 版本号规则：三段式 + 满十进位（与 tools/versioning.py 一一对应）。
///
/// 规则：从 1.1.1 起算，每发一版末段 +1；末段满 10 → 中段 +1、末段归 0；
/// 中段满 10 → 首段 +1 并丢掉归零的末段；首段满 10 不再进位。
/// 即「每多进一级就少一段」：
///     1.1.1 → 1.1.2 … 1.1.9 → 1.2.0 … 1.9.9 → 2.0 … 9.9 → 10 → 11
///
/// ⚠️ Python 侧有一份等价实现（tools/versioning.py）。两边共用
///    tools/version_vectors.json 的自测向量表，任何一边改规则都必须同时过测，
///    否则会出现「启动器显示 1.1.10、update.json 写 1.2.0」这类不一致。
/// </summary>
internal static class VersionUtil
{
    // 日期制遗留（老安装的 VERSION，如 2026.09.20）：原样保留，不参与进位换算。
    // 否则 2026.09.20 会被算成 2027.1，胶囊上显示成 V2027.1。
    private static readonly Regex LegacyDateRe =
        new(@"^\d{4}\.\d{1,2}\.\d{1,2}$", RegexOptions.Compiled);

    private static readonly Regex NumberRe = new(@"\d+", RegexOptions.Compiled);

    public static bool IsLegacyDate(string? value) =>
        LegacyDateRe.IsMatch((value ?? "").Trim());

    public static List<int> ParseVersion(string? value)
    {
        var parts = new List<int>();
        foreach (Match m in NumberRe.Matches(value ?? ""))
        {
            if (int.TryParse(m.Value, out var v)) parts.Add(v);
        }
        return parts;
    }

    /// <summary>把任意写法的版本号折算成「进位后」的规范式（幂等）。</summary>
    public static string NormalizeVersion(string? value)
    {
        var raw = (value ?? "").Trim();
        if (raw.Length == 0) return "";
        if (IsLegacyDate(raw)) return raw;

        var parts = ParseVersion(raw);
        if (parts.Count == 0) return "";

        while (true)
        {
            var over = -1;
            for (var i = 0; i < parts.Count; i++)
                if (parts[i] >= 10) over = i;          // 取最靠右的溢出位
            if (over < 0) break;

            if (over == 0)
            {
                // 首段溢出：没有更高位可进，不再进位（9.9 → 10），并丢掉多出来的段
                parts.RemoveRange(1, parts.Count - 1);
                break;
            }

            var carry = parts[over] / 10;
            parts[over] %= 10;
            parts[over - 1] += carry;
            if (over < parts.Count - 1)
                parts.RemoveRange(over + 1, parts.Count - over - 1);   // 丢掉右边已归零的段
        }

        return string.Join(".", parts);
    }

    /// <summary>按规范化后的点分数字比版本。a &gt; b 返回 1，相等 0，小于 -1。</summary>
    public static int CompareVersion(string? a, string? b)
    {
        var pa = ParseVersion(NormalizeVersion(a));
        var pb = ParseVersion(NormalizeVersion(b));
        for (var i = 0; i < Math.Max(pa.Count, pb.Count); i++)
        {
            var x = i < pa.Count ? pa[i] : 0;
            var y = i < pb.Count ? pb[i] : 0;
            if (x != y) return x > y ? 1 : -1;
        }
        return 0;
    }
}

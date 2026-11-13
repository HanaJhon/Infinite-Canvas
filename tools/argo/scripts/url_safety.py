#!/usr/bin/env python3
"""url_safety.py — URL 请求安全校验（SSRF 防护）

对 fetch / crawl 等会发起网络请求的入口做统一拦截：
  1. scheme 白名单（仅 http/https，拒绝 file:// / ftp:// 等）
  2. 主机名黑名单（localhost、裸单标签主机、.local/.internal/.lan 等）
  3. DNS 解析后 IP 段检查（私有 / 环回 / 链路本地 / 保留 / CGNAT 等）
  4. 重定向目标同样逐跳校验（配合 http_client 的安全跟随）

SSRF 判定语义：按「域名在本机 DNS 下的可路由语义」自适应，而非机械按
IP 段一刀切。若域名解析出的全部地址均为 fake-ip 占位段（代理工具
Clash/Surge TUN 的 fake-ip 模式，如 198.18.0.0/15、fdfe:dcba:9876::/64），
说明该域名由代理接管、流量经 TUN 直达公网目标，到不了内网 —— 不构成
SSRF 风险，放行；解析含任一真实私有 IP 则仍拦截。

默认阻止私有地址；显式设置 ARGO_ALLOW_PRIVATE_URLS=1 可放行
（本地调试 / 自建内网服务场景）。
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
import urllib.parse
from urllib.parse import urlparse


# 私有 / 特殊用途 IPv4 段
_PRIVATE_NETWORKS_V4 = [
    "0.0.0.0/8",        # 本网络
    "10.0.0.0/8",       # 私有
    "100.64.0.0/10",    # CGNAT
    "127.0.0.0/8",      # 环回
    "169.254.0.0/16",   # 链路本地
    "172.16.0.0/12",    # 私有
    "192.168.0.0/16",   # 私有
    "192.0.0.0/24",     # IETF 协议分配
    "192.0.2.0/24",     # TEST-NET-1
    "198.18.0.0/15",    # 基准测试
    "198.51.100.0/24",  # TEST-NET-2
    "203.0.113.0/24",   # TEST-NET-3
    "224.0.0.0/4",      # 组播
    "240.0.0.0/4",      # 保留
]

# 私有 / 特殊用途 IPv6 段
_PRIVATE_NETWORKS_V6 = [
    "::1/128",          # 环回
    "::/128",           # 未指定
    "fc00::/7",         # 唯一本地地址 ULA
    "fe80::/10",        # 链路本地
    "ff00::/8",         # 组播
    "2001:db8::/32",    # 文档
    "64:ff9b::/96",     # NAT64 前缀
]

_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n) for n in _PRIVATE_NETWORKS_V4 + _PRIVATE_NETWORKS_V6
]

# fake-ip 代理占位段：Clash/Surge 等 TUN 工具的 fake-ip 模式把域名解析到
# 这些段，流量由 TUN 设备接管转发至真实公网目标。占位段不可直达内网，
# 因此命中占位段不算 SSRF 风险（见 host_is_private）。
_FAKE_IP_NETWORKS = [
    ipaddress.ip_network("198.18.0.0/15"),      # Clash/Surge fake-ip 默认 v4 段
    ipaddress.ip_network("fdfe:dcba:9876::/64"),  # Clash fake-ip 默认 v6 段
]

# 裸主机名（无点）与内网域名后缀：默认视为不可路由目标
_PRIVATE_HOST_SUFFIXES = (
    ".local", ".internal", ".lan", ".home.arpa", ".corp", ".intranet",
)
_LOCALHOST_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


def allow_private() -> bool:
    """是否显式放行私有地址（ARGO_ALLOW_PRIVATE_URLS=1）。

    收编到 env_flag（2026-09-29）：授权位必须 expand=False + strict=True
    （见 env_flag docstring——别名展开落在授权位上等于授权扩张，「非关即开」
    会让任何拼错的值放行 SSRF）。此前裸读三值表：不读 env 文件、只认
    1/true/yes，且整个逃过静态门禁的授权位检查（门禁只匹配 env_flag 调用
    形状；同批已升级为按 ARGO_ALLOW_ 名字匹配，裸读即报红）。
    """
    from engine_env import env_flag
    return env_flag("ARGO_ALLOW_PRIVATE_URLS", default=False,
                    expand=False, strict=True)


def is_private_ip(ip_str: str) -> bool:
    """判断 IP 是否属于私有 / 特殊用途段。

    IPv4-mapped IPv6（::ffff:a.b.c.d）实际连接落在 IPv4 网段，
    必须转回 IPv4 再查表，否则 http://[::ffff:127.0.0.1]/ 可绕过
    私有段检查（SSRF）。
    """
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in net for net in _PRIVATE_NETWORKS)


def is_fake_ip_address(ip_str: str) -> bool:
    """判断 IP 是否属于 fake-ip 代理占位段。

    fake-ip 模式（Clash/Surge TUN）下代理工具把域名解析到占位段，
    流量由 TUN 设备接管转发到真实公网目标。占位段本身不可直达内网，
    因此不构成 SSRF 风险。仅当域名解析出的全部地址均为占位段时，
    才判定为「代理接管域名」并放行（见 host_is_private）。
    """
    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in net for net in _FAKE_IP_NETWORKS)


def host_is_private_name(host: str) -> bool:
    """主机名级判断：localhost / 裸主机名 / 内网域名后缀。"""
    h = (host or "").strip().rstrip(".").lower()
    if not h:
        return True
    if h in _LOCALHOST_NAMES:
        return True
    if "." not in h:
        return True  # 裸主机名（如 intranet、router）默认视为内网
    return h.endswith(_PRIVATE_HOST_SUFFIXES)


# 数字 IP 字面量字符集：十进制 / 十六进制（0x）/ 前导零八进制 / 点分组合
_NUMERIC_HOST_RE = re.compile(r"^[0-9a-fA-FxX.]+$")


def _normalize_numeric_host(host: str) -> str | None:
    """数字 IP 字面量规范化：八进制 / 十六进制 / 单段整数 → 标准点分 IPv4。

    各系统解析器对 0177.0.0.1（八进制）、0x7f.0.0.1（十六进制）、
    2130706433（单段整数）的行为不一致，校验层不能依赖连接层的「自觉」：
    统一 int() 规范化后再查私有表，堵住绕过（SSRF）。
    非数字字面量返回 None。
    """
    if not host or not _NUMERIC_HOST_RE.match(host) or ":" in host:
        return None  # IPv6 字面量交给 ipaddress / getaddrinfo 处理

    def _to_int(seg: str) -> int | None:
        try:
            if seg.lower().startswith("0x"):
                return int(seg, 16)
            if len(seg) > 1 and seg.startswith("0"):
                return int(seg, 8)
            return int(seg, 10)
        except ValueError:
            return None

    if "." in host:
        segs = host.split(".")
        if len(segs) != 4:
            return None
        parts: list[int] = []
        for s in segs:
            v = _to_int(s)
            if v is None or v > 255:
                return None
            parts.append(v)
        return ".".join(str(p) for p in parts)
    v = _to_int(host)
    if v is None or v > 0xFFFFFFFF:
        return None
    return ".".join(str((v >> s) & 0xFF) for s in (24, 16, 8, 0))


def host_is_private(host: str) -> bool:
    """综合判断主机是否私有：先主机名，再数字字面量，最后 DNS 解析。

    fake-ip 占位段例外：若解析出的地址全部是占位段（域名被代理接管，
    流量走 TUN 直达公网），则不视为私网；只要含任一真实私有 IP 即拦截。
    """
    if host_is_private_name(host):
        return True
    norm = _normalize_numeric_host(host)
    if norm is not None:
        # 数字字面量：直接按规范化结果查表，不依赖 getaddrinfo。
        # 标准点分形式（norm == host）此前会落到 getaddrinfo——既多一次系统
        # 调用，又让「被 mock/劫持的解析器」能影响 SSRF 判定。
        return is_private_ip(norm)
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        # 解析失败无法确认公网性：保守按私有处理（宁可误伤不可漏防）
        return True
    seen = set()
    for info in infos:
        ip = info[4][0]
        if ip in seen:
            continue
        seen.add(ip)
        if is_fake_ip_address(ip):
            # 代理接管域名（fake-ip 占位），不视为内网
            continue
        if is_private_ip(ip):
            return True
    return False


def check_url(url: str) -> tuple[bool, str]:
    """校验 URL 是否可安全请求。返回 (ok, reason)。"""
    if not url or not isinstance(url, str):
        return False, "空 URL"
    try:
        parsed = urlparse(url)
    except ValueError as e:
        return False, f"URL 解析失败: {e}"
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"仅允许 http/https，收到 {scheme or '空'} scheme"
    host = parsed.hostname or ""
    if not host:
        return False, "URL 缺少主机名"
    if allow_private():
        return True, ""
    if host_is_private_name(host):
        return False, f"主机名指向本机/内网: {host}"
    if host_is_private(host):
        return False, f"目标 IP 属于私有/保留段: {host}"
    return True, ""


def is_safe_fetch_url(url: str) -> bool:
    """便捷布尔封装：仅 http/https 且目标非私有地址。"""
    ok, _ = check_url(url)
    return ok


def max_redirects() -> int:
    """最大重定向跳数（默认 5，合法 1-20，越界回落默认）。"""
    try:
        from engine_env import get_env
        val = int(str(get_env(["ARGO_MAX_REDIRECTS"])).strip())
    except (TypeError, ValueError):
        return 5
    return val if 0 < val <= 20 else 5


def check_redirect_target(url: str, start: float) -> dict | None:
    """校验重定向目标是否可安全请求；被拦截返回统一错误 dict，放行返回 None。

    与 resolve_redirect_chain 的逐跳校验对齐——此前 _do_get/_do_post 的
    内联重定向循环只校验首跳，重定向到内网即可绕过 SSRF。
    """
    ok, reason = check_url(url)
    if ok:
        return None
    return {
        "status": 0, "headers": {}, "text": "",
        "url": url,
        "elapsed_ms": int((time.time() - start) * 1000),
        "error": f"重定向目标被 SSRF 防护拦截: {reason}",
    }


def resolve_redirect_chain(url: str, headers: dict, timeout: float,
                           limit: int | None = None) -> str | None:
    """逐跳安全跟随重定向：每跳目标都过 SSRF 校验（curl 通道用）。

    返回最终 URL；任一跳被拦截或超过跳数返回 None。
    """
    if limit is None:
        limit = max_redirects()
    current = url
    for _ in range(limit):
        ok, _reason = check_url(current)
        if not ok:
            return None
        parsed = urlparse(current)
        if parsed.scheme not in ("http", "https"):
            return None
        try:
            from net_proxy import open_connection, request_selector, resolve_proxy
            proxy_url = resolve_proxy(current)
            conn, via_proxy = open_connection(parsed, timeout, proxy_url)
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            conn.request("HEAD", request_selector(parsed, path, via_proxy),
                         headers=headers)
            resp = conn.getresponse()
            status = resp.status
            location = resp.getheader("Location")
            conn.close()
        except Exception:
            return None
        if status not in (301, 302, 303, 307, 308) or not location:
            return current
        current = urllib.parse.urljoin(current, location)
    return None


# ── 解析即锁定（DNS rebinding / TOCTOU 防护）─────────────────────────────────
#
# check_url() 在请求前解析一次 DNS，http.client 在 connect() 时再解析一次——
# 两次之间域名可改指内网（DNS rebinding）。下面两个连接类在 connect() 里
# 解析一次、过滤私网、把结果钉给本次 TCP 连接，窗口关闭；SNI/Host 仍用原域名。


def _is_ip_literal(host: str) -> bool:
    """主机名是否为 IP 字面量（v4 / v6，含 [v6] 与 IPv4-mapped）。"""
    h = (host or "").strip().strip("[]")
    if not h:
        return False
    if ":" in h:            # IPv6（含 ::ffff:a.b.c.d）
        return True
    parts = h.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


def resolve_public_addresses(host: str) -> list[str]:
    """解析主机名 → 公网地址名单（过滤私网/保留段；fake-ip 占位段放行）。

    返回空列表表示「无可连的公网地址」——调用方应拒绝连接（fail-closed）。
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for info in infos:
        ip = info[4][0]
        if ip in seen:
            continue
        seen.add(ip)
        if is_fake_ip_address(ip):      # 代理接管域名（占位段），不可直达内网
            out.append(ip)
            continue
        if is_private_ip(ip):
            continue
        out.append(ip)
    return out


def pin_host(host: str) -> str | None:
    """返回要钉扎的公网 IP；IP 字面量或显式放行私网时返回 None。

    无可连的公网地址则抛错（fail-closed）。供 safe_conn 的连接类使用。
    """
    if allow_private() or _is_ip_literal(host):
        return None
    addrs = resolve_public_addresses(host)
    if not addrs:
        raise OSError(f"SSRF 防护：{host} 无可连的公网地址")
    return addrs[0]

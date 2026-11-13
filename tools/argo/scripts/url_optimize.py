#!/usr/bin/env python3
"""url_optimize.py — URL 优化：Reddit 重写、追踪参数清理。纯函数。"""

from __future__ import annotations

import urllib.parse


def normalize_url(url: str) -> str:
    """基础 URL 规范化。"""
    url = url.strip()
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # 去掉默认端口
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    # 路径规范化（处理 ./ 和 ../）
    import posixpath
    raw_path = parsed.path or "/"
    path = posixpath.normpath(raw_path)
    # posixpath.normpath 会把空路径变成 "."，需要修正
    if path == ".":
        path = "/"
    # 保留尾部斜杠：原始路径以 / 结尾时，规范化后也要保留
    if raw_path.endswith("/") and not path.endswith("/"):
        path += "/"
    # 去掉 fragment：fragment 不参与服务端资源定位，且同一页面的锚点变体会
    # 在缓存/去重里裂成多条（docstring 一直这么写，旧实现却把 fragment 原样
    # 带了回来）。
    return urllib.parse.urlunsplit(
        (scheme, netloc, path, parsed.query, ""))


def optimize_url(url: str) -> str:
    """URL 优化：Reddit 重写、追踪参数清理。"""
    url = normalize_url(url)
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host in ("reddit.com", "www.reddit.com", "new.reddit.com"):
        url = url.replace("://www.reddit.com", "://old.reddit.com")
        url = url.replace("://reddit.com", "://old.reddit.com")
        url = url.replace("://new.reddit.com", "://old.reddit.com")
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                       "utm_content", "fbclid", "gclid", "ref", "ref_src"}
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    filtered = {k: v for k, v in qs.items() if k.lower() not in tracking_params}
    if len(filtered) < len(qs):
        new_qs = urllib.parse.urlencode(filtered, doseq=True)
        url = urllib.parse.urlunparse(parsed._replace(query=new_qs))
    return url

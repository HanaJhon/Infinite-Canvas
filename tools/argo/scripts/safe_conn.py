#!/usr/bin/env python3
"""safe_conn.py — 解析即锁定的 HTTP/HTTPS 连接类（DNS rebinding / TOCTOU 防护）

独立成模块的理由：``http.client`` 会连带拉起 ``ssl``（实测 ≈14 ms）。
``url_safety`` 被 ``robots_guard`` 等在**模块级**导入（见 robots_guard 的
「轻导入」注释），若把 ``http.client`` 放在 ``url_safety`` 里，
``test_robots_guard.test_module_import_stays_light`` 会红。连接类只在真正
建连时经 ``net_proxy.open_connection`` 导入，不进轻导入路径。

原理：``check_url()`` 在请求前解析一次 DNS，``http.client`` 在 ``connect()``
时再解析一次——两次之间域名可改指内网（DNS rebinding）。本类在 ``connect()``
里解析一次、过滤私网、把结果钉给本次 TCP 连接，窗口关闭；SNI/Host 仍用原域名。
"""

from __future__ import annotations

import http.client

from url_safety import pin_host


class SafeHTTPConnection(http.client.HTTPConnection):
    """解析即锁定的 HTTP 连接：TCP 只连校验过的公网 IP，Host 头仍用原域名。"""

    def connect(self):
        pinned = pin_host(self.host)
        if pinned is None:
            return super().connect()
        host = self.host
        self.host = pinned
        try:
            super().connect()
        finally:
            self.host = host


class SafeHTTPSConnection(http.client.HTTPSConnection):
    """解析即锁定的 HTTPS 连接：TCP 钉公网 IP，SNI/证书校验仍用原域名。"""

    def connect(self):
        pinned = pin_host(self.host)
        if pinned is None:
            return super().connect()
        host = self.host
        self.host = pinned
        try:
            http.client.HTTPConnection.connect(self)      # 仅 TCP
        finally:
            self.host = host
        server_hostname = self._tunnel_host or host
        self.sock = self._context.wrap_socket(
            self.sock, server_hostname=server_hostname)

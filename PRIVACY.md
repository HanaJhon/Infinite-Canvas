# 无限画布 · 图片采集 隐私政策 / Privacy Policy

适用于 Edge / Chrome 扩展「无限画布 · 图片采集」（Infinite Canvas Capture，版本 1.0.x）。
Applies to the "Infinite Canvas Capture" browser extension (Edge / Chrome, version 1.0.x).

最近更新 / Last updated：2026-11-03

---

## 中文

### 1. 我们收集什么

本扩展**不向开发者、也不向任何第三方**发送数据。

当用户主动采集图片时，图片本身、素材库与分类名称、以及登录令牌，只会发送到**用户自己在扩展设置里填写的「无限画布」服务地址**（例如 `http://127.0.0.1:3000`）。该地址由用户提供，开发者无法访问。

### 2. 数据存放在哪里

- 服务地址、登录令牌、深浅色主题偏好：保存在用户浏览器的本机存储（`chrome.storage.local`）。
- 采集的图片与素材元数据：保存在用户自己的「无限画布」服务（本机或局域网）。

### 3. 我们不做什么

- 不收集浏览历史，不做统计分析，不注入广告。
- 不读取与采集无关的页面内容。
- 不向任何第三方出售、共享或转让用户数据。
- 不使用远程代码；扩展的所有代码都在安装包内。

### 4. 权限说明

扩展仅在用户主动操作（右键菜单采集、拖拽投放、点击「扫描当前页图片」）时访问当前页面，用于取得图片地址。

### 5. 联系方式

- 问题与反馈：<https://github.com/HanaJhon/Infinite-Canvas/issues>
- 项目主页：<https://github.com/HanaJhon/Infinite-Canvas>

---

## English

### 1. What we collect

This extension sends **nothing** to the developer and **nothing** to any third party.

When the user captures images, the images, the library and category names, and the session token are sent **only to the Infinite Canvas server URL that the user entered in the extension options** (for example `http://127.0.0.1:3000`). That address is chosen by the user; the developer has no access to it.

### 2. Where data is stored

- Server URL, session token and theme preference: local browser storage on the user's machine (`chrome.storage.local`).
- Captured images and media metadata: the user's own Infinite Canvas server (local machine or LAN).

### 3. What we do not do

- No browsing history collection, no analytics, no ads injected.
- No reading of page content unrelated to capturing.
- No selling, sharing or transferring user data to third parties.
- No remote code; all code ships inside the package.

### 4. Permissions

The extension touches the current page only after an explicit user action (context menu capture, drop zone, or "scan images on this page"), solely to obtain image URLs.

### 5. Contact

- Issues: <https://github.com/HanaJhon/Infinite-Canvas/issues>
- Project: <https://github.com/HanaJhon/Infinite-Canvas>

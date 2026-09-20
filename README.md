# Infinite-Canvas · AI Agent · Lochou 版
AI 无限画布：聊天驱动画图 / 图片编辑 / 视频生成 / 灵感库，支持 OpenAI 协议、即梦等。
> 基于 [hero8152/Infinite-Canvas](https://github.com/hero8152/Infinite-Canvas) 二次开发，独立维护，不跟随上游（上游已于 2026-08 停更）。

## 近期更新 & 使用须知

当前版本 **1.1.1**。完整更新记录见 [Releases](https://github.com/HanaJhon/Infinite-Canvas/releases) 与软件内「更新说明」。

- **版本号改为三段式**：从 `1.1.1` 起算，末段满 10 自动进位（`1.1.9` → `1.2.0`、`1.9.9` → `2.0`）。启动器版本胶囊与画布内的版本徽章都按新规则显示，不再使用日期式版本号。
- **启动器新增软件更新入口**：首页版本胶囊可点击查看更新（或「设置 → 软件更新」），检测到新版本时胶囊右上角显示红点；启动器启动后会自动检查更新。胶囊上的版本号改为读取本地 `VERSION` 文件，不再写死。
- **修复 Grsai 通道的内置模型清单**：补回 `gpt-6-astra` / `gpt-5.6-terra` / `gpt-5.6-sol` / `gpt-5.5` 四个 GPT 对话模型（此前因把上游抖动误判为「模型不存在」而剔除，导致启动器拉取不到任何 GPT 对话模型）。
- **自动更新源修正**：检查更新改为比对本仓库 `HanaJhon/Infinite-Canvas`，修复原先指向第三方 fork 导致「改了版本号、软件内却检测不到新版本」的问题。
- **移除上游遗留的迁移推广内容**，更新面板不再出现第三方引流信息。
- **发布包改为干净打包**：剔除 `.git`、画布数据、历史记录、API 密钥等私有内容，安装包体积由约 798 MB 降至约 111 MB。
- ⚠️ **若手上还是日期式版本号（如 `2026.09.20`）的旧包，软件内可能提示不到这次更新，请手动下载覆盖一次**，之后即可正常自动更新。用户数据都在 `data/`、`assets/` 目录下、不在发布包内，覆盖安装不会动它们。
- ⚠️ 关闭弹窗时若选择「记住习惯」，以后将不会再弹出，请谨慎选择！
- ⚠️ 使用后请谨慎分享，存在泄露 API 密钥风险！
- 感谢 hero8152 的开源。

## 快速开始
```bash
pip install -r requirements.txt   # macOS 可直接运行 mac-安装依赖.command，Windows 运行 安装依赖.bat
python3 main.py
# 浏览器打开 http://127.0.0.1:3000/
```
Windows 用户也可直接双击根目录的 **`Lochou启动器.exe`**：图形界面，自动检查环境与依赖、一键启动 / 停止本地服务，并可管理 API 通道与软件更新。

## 功能
- 多协议生图 / 生视频：OpenAI、Gemini、火山方舟、即梦 CLI
- 智能画布 Agent：LLM 意图路由、流式回复、360 全景预览、视频帧抽取、循环节点
- **3D 预览节点**：three.js 实时舞台，上游接「快速生图」出图、下游可把当前画面截图回灌生图，支持拖拽 / 缩放与失败态提示
- **Windows 一键启动器**：环境与依赖检测、启停服务、API 通道配置（含模型拉取与测速）、创建快捷方式、软件一键更新
- 灵感库：[awesome-gpt-image-2](https://github.com/freestylefly/awesome-gpt-image-2) 541 个提示词案例 + 本地生成图，自动跟随上游更新
- tools：Chrome 批量采集素材插件、PS 直连画布插件

## 自动更新
版本号是三段式，从 `1.1.1` 起算，末段满 10 自动进位（`1.1.9` → `1.2.0`、`1.9.9` → `2.0`、`9.9` → `10`）。
升版本请用 `python tools/bump_version.py`，**不要手改 `VERSION`**（手写 `1.1.10` 这类非规范式会让更新检测陷入死循环）。
升完 commit → push，软件内版本徽章与启动器会自动检测新版本；启动器首页版本胶囊即更新入口，点开即可一键更新。
⚠️ 更新只覆盖程序文件，`data/` 与 `assets/` 里的画布、通道与密钥都会保留（更新前会自动备份到 `data/update_backups/`）；目前**没有界面上一键回滚**，需要回退请手动用备份目录里的副本覆盖。

## API 配置
在软件「API 设置」界面填写 Key / URL，勿写入代码或提交到仓库。
## 版权
禁止商业用途；二次开发须保持开源并注明来源作者。
## 链接
- 原项目（已停更）：[hero8152/Infinite-Canvas](https://github.com/hero8152/Infinite-Canvas)
- 教程视频：[YouTube](https://youtu.be/r_y_9ALr7fg)
- Chrome 采集插件：[Chrome 商店](https://chromewebstore.google.com/detail/infinite-canvas-%E5%9B%BE%E5%83%8F%E8%A7%86%E9%A2%91%E6%96%87%E5%AD%97%E6%8A%93%E5%8F%96%E5%B7%A5/ajfhnbklbmpfaaookhfakohabnpmlcic)
- 推荐 API 站（生图 / 视频 / LLM）：[apib.ai](https://apib.ai/register?aff=1uyAbb) · [fhl.mom](https://www.fhl.mom/register?aff=86L574B4T2N9)
---
<img width="2079" height="665" alt="image" src="https://github.com/user-attachments/assets/8469923b-f7a2-403c-9c37-e6e789211f28" />
<img width="1865" height="1503" alt="image" src="https://github.com/user-attachments/assets/f4030201-67c6-4845-b08b-b6fdf304afaa" />

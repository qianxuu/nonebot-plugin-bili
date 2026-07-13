# nonebot-plugin-bili

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![NoneBot2](https://img.shields.io/badge/NoneBot-2-red.svg)](https://nonebot.dev/)
[![OneBot](https://img.shields.io/badge/OneBot-V11-black.svg)](https://onebot.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![CI](https://github.com/qianxuu/nonebot-plugin-bili/actions/workflows/ci.yml/badge.svg)](https://github.com/qianxuu/nonebot-plugin-bili/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nonebot-plugin-bili.svg)](https://pypi.org/project/nonebot-plugin-bili/)

NoneBot2 插件：自动识别 B 站视频链接并尝试下载发送，支持直播开播 / 下播 / 标题变更提醒。

> **免责声明**：仅供学习与自用。请遵守哔哩哔哩服务条款与当地法律法规，勿用于未授权传播他人内容。本插件与哔哩哔哩无官方关联；依赖 Web 接口与 WBI 签名策略，**可能随时失效，不保证长期可用**。作者不对滥用、账号风控、版权纠纷或服务中断承担责任。使用本插件即表示你理解并自行承担相关风险。

## 功能

- 识别群聊 / 私聊中的 BV 号、`b23.tv` 短链与部分分享卡片
- 发送标题、封面与视频链接；可下载后发送视频
- 视频过大 / 充电专属 / 风控无流等场景给出提示并跳过下载
- 群冷却、群黑名单、本地缓存与过期清理
- 可选 NapCat 缓存目录映射，跳过 WS 流式上传
- 超级管理员私聊订阅直播，轮询状态并推送开播 / 下播 / 改标题

## 环境要求

- Python 3.12+
- [NoneBot2](https://nonebot.dev/)
- [OneBot V11 适配器](https://onebot.adapters.nonebot.dev/)
- [nonebot-plugin-apscheduler](https://github.com/nonebot/plugin-apscheduler)（直播轮询，插件会 `require`）
- 发送视频推荐 [NapCat](https://github.com/NapNeko/NapCatQQ)
- 机器人宿主需自行安装 driver（常见为 `nonebot2[fastapi]`）

## 安装

### 使用 nb-cli

```bash
nb plugin install nonebot-plugin-bili
```

### 使用 pip / uv

```bash
pip install nonebot-plugin-bili
# 或
uv add nonebot-plugin-bili
```

### 从 Git 安装

```bash
uv add git+https://github.com/qianxuu/nonebot-plugin-bili
# 或指定本地路径
uv add /path/to/nonebot-plugin-bili
```

加载：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_bili"]
```

或：

```python
nonebot.load_plugin('nonebot_plugin_bili')
```

### 本地开发

```bash
git clone https://github.com/qianxuu/nonebot-plugin-bili.git
cd nonebot-plugin-bili
uv sync --group dev
```

## 支持的视频输入

- `BV1xxxxxxxxx`
- `https://www.bilibili.com/video/BV1...`
- `https://b23.tv/xxxxxxx`
- 部分含 BV / 短链的分享卡片

## 直播命令

仅 **超级管理员私聊**：

| 命令 | 说明 |
|---|---|
| `订阅直播 <uid> <群号>` | 订阅主播开播提醒到指定群 |
| `取消订阅直播 <uid> <群号>` | 取消订阅 |
| `直播订阅列表` | 查看全部订阅 |

数据保存在机器人工作目录 `data/bili/bili.db`。

## 配置

复制 [`.env.example`](./.env.example) 到机器人项目的 `.env`，字段名对应 `BILI_*`（大小写不敏感）。

| 配置项 | 必需 | 默认 | 说明 |
|---|---|---|---|
| `BILI_NAPCAT_CACHE_DIR` | 否 | 空 | NapCat 容器内缓存目录 |
| `BILI_GROUP_BLACKLIST` | 否 | `[]` | 群黑名单，JSON 数组 |
| `BILI_MAX_VIDEO_SIZE_MIB` | 否 | `50` | 跳过下载的视频大小上限（MiB） |
| `BILI_GROUP_CD_SECONDS` | 否 | `60` | 同群同 BV 冷却秒数，`0` 表示不冷却 |
| `BILI_CACHE_RETENTION_HOURS` | 否 | `24` | 本地缓存保留小时数 |
| `BILI_LIVE_POLL_INTERVAL` | 否 | `15` | 直播状态轮询间隔（秒） |

### 完整示例

```env
BILI_NAPCAT_CACHE_DIR=/app/.config/QQ/NapCat/temp
BILI_GROUP_BLACKLIST=["123456789", "987654321"]
BILI_MAX_VIDEO_SIZE_MIB=50
BILI_GROUP_CD_SECONDS=60
BILI_CACHE_RETENTION_HOURS=24
BILI_LIVE_POLL_INTERVAL=15
```

配置 `BILI_NAPCAT_CACHE_DIR` 时，请确保机器人进程的 `cache/bili` 与 NapCat 该目录为同一挂载或可互相访问。

## 行为说明

- 同一 `bvid` 在同一群默认冷却 60 秒；配置为 `0` 表示不冷却
- 视频超过默认 50 MiB、充电专属、无有效流地址、风控 `v_voucher` 时跳过下载并提示
- 本地视频缓存：`cache/bili/{bvid}.mp4`（相对机器人工作目录）
- 下载前按保留时长清理过期缓存
- 直播状态默认每 15 秒轮询；开播后通过 WebSocket 采集观看 / 同接
- 解析 / 发送失败等情况写日志；部分场景会向用户提示前往 B 站观看

## 目录结构

```text
nonebot-plugin-bili/
├── src/nonebot_plugin_bili/
│   ├── __init__.py   # 元数据、启停钩子
│   ├── video.py      # 视频链接识别与发送
│   ├── live.py       # 直播订阅与轮询推送
│   ├── live_ws.py    # 直播间 WebSocket 采集
│   ├── api.py        # 视频 / 直播接口
│   ├── client.py     # HTTP 客户端与 WBI 会话
│   ├── wbi.py        # WBI 签名
│   ├── config.py     # 配置模型
│   ├── database.py   # 订阅与会话 SQLite
│   ├── download.py   # 分片下载与缓存
│   ├── upload.py     # NapCat 流式上传
│   └── utils.py
├── tests/
├── .env.example
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
└── README.md
```

## 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| WBI / `v_voucher` | 签名或风控 | 查看日志，稍后重试 |
| 视频不下载 | 过大 / 专属 / 流地址失败 | 看消息提示与日志 |
| 发送慢或失败 | 未配置 NapCat 映射 | 配置 `BILI_NAPCAT_CACHE_DIR` 与挂载 |
| 群内不响应 | 黑名单或冷却中 | 检查相关配置 |
| 直播不推送 | 未订阅 / 非超管 / 调度器未加载 | 检查命令权限与 apscheduler |

## 已知限制

- 依赖 B 站 Web 接口与 WBI 签名，策略变更或风控时可能失效，**不承诺长期可用**
- 部分视频（大会员 / 充电 / 地区限制等）无法下载，仅发送信息与提示
- 发送视频依赖具体 OneBot 实现能力（如 NapCat 缓存映射或 `upload_file_stream`）
- 直播订阅仅限超级管理员私聊操作
- 大视频受 `BILI_MAX_VIDEO_SIZE_MIB` 与宿主上传能力共同限制

## 开发

```bash
uv sync --group dev
uv run pytest
uv run ty check src/nonebot_plugin_bili tests
uv run ruff check .
uv run ruff format .
uv build
uv run twine check dist/*
```

## 安全提示

- 勿在仓库、Issue、截图中泄露 Cookie、机器人 token 或其他凭证
- 生产环境建议限制群范围（黑名单 / 冷却），避免被刷链导致带宽与风控压力
- `cache/bili` 与 `data/bili` 可能包含媒体与订阅数据，请勿公开分享

## License

[MIT](./LICENSE)

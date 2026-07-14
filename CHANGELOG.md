# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

## [0.2.0] - 2026-07-15

### 新增

- 配置项 `BILI_SEND`：JSON 数组可选发送封面（`cover`：标题+封面图+链接）与视频（`video`）

### 文档

- 强化接口可用性、安全提示与已知限制
- 补充目录结构、完整配置示例与开发校验命令
- 补充 `BILI_SEND` 配置说明与示例

### 构建 / CI

- 升级 `actions/checkout@v7`、`astral-sh/setup-uv@v7`
- 开发依赖增加 `twine`，CI 增加 build 后校验
- sdist 纳入变更日志、配置示例与测试源码

### 修复 / 改进

- 冷却 `seconds <= 0` 视为关闭冷却
- 缓存清理对缺失目录与删除失败更稳健

## [0.1.0] - 2026-07-13

### 新增

- B 站视频链接 / BV 号 / `b23.tv` 短链 / 分享卡片识别
- 视频信息发送与可选下载发送（NapCat 缓存映射或流式上传）
- 直播订阅、开播 / 下播 / 标题变更推送
- 群冷却、群黑名单、缓存清理与可配置大小限制

### 说明

- 首个面向独立开源分发的版本
- 依赖 B 站公开 Web 接口与 WBI 签名，接口可能变更，不保证长期可用

[Unreleased]: https://github.com/qianxuu/nonebot-plugin-bili/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/qianxuu/nonebot-plugin-bili/releases/tag/v0.2.0
[0.1.0]: https://github.com/qianxuu/nonebot-plugin-bili/releases/tag/v0.1.0

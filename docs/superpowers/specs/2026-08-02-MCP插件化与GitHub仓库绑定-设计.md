# MediaCrawler MCP 插件化与 GitHub 仓库绑定 — 设计文档

- 日期：2026-08-02
- 状态：已实现（feature/claude-code-plugin 分支）
- 作者：wanzicong + Claude

## 1. 背景与目标

MediaCrawler 仓库已内置一个 MCP 服务（`mcp_server/`，13 个工具：7 个平台爬取 +
list_platforms + read_crawl_data + 4 个媒体转写工具）。目标：

1. 把这个 MCP 工具打包成 **Claude Code 插件**，并配套若干使用技能（skills）。
2. 把项目绑定到用户自己的 GitHub 仓库（`wanzicong/MediaCrawler`，公开），
   与上游 `NanmiCoder/MediaCrawler` 用独立分支隔离，避免逻辑交集。

## 2. 现状梳理

- 本地 main 相对上游有 9 个定制提交（MCP 服务、抖音个人点赞收藏、媒体转写等）。
- 接手时仓库处于 merge 中途（上游 5 个提交，6 个文件冲突）——已解决并完成合并：
  - README*.md：采用上游赞助商链接更新；
  - pyproject/requirements/uv.lock：采用上游 xhshow>=0.2.0 升级，保留本地 mcp 依赖；
  - playwright_sign.py：上游移除 GET a3_hash monkey-patch（xhshow 0.2.0 原生修复）；
  - time_util.py：上游 RFC2822 时区修复。
- 合并后验证：226 passed，6 个失败均为本机无 Redis 的环境性失败（test_redis_cache、
  test_proxy_ip_pool），与改动无关；xhs 签名与 MCP 服务模块导入冒烟通过。

## 3. 架构设计

### 3.1 插件形态：根级插件

```
MediaCrawler/                       ← fork 仓库根（wanzicong/MediaCrawler）
├── .claude-plugin/
│   ├── plugin.json                 ← 插件清单（引用 ./.mcp.json）
│   └── marketplace.json            ← 市场清单（仓库可直接被 marketplace add）
├── .mcp.json                       ← stdio 启动 mcp_server
├── skills/
│   ├── crawl-platform/SKILL.md     ← 技能①平台爬取
│   ├── read-crawl-data/SKILL.md    ← 技能②数据回读
│   ├── media-transcribe/SKILL.md   ← 技能③视频转写
│   └── mcp-server-ops/SKILL.md     ← 技能④服务运维
├── commands/mediacrawler-help.md   ← /mediacrawler-help 命令
├── docs/插件使用指南.md             ← 安装与前置条件
└── mcp_server/ 等现有代码（零改动）
```

关键决策：

- **根级插件**（而非 plugin/ 子目录）：clone 即用，路径最少。
- **`.mcp.json` 用 `${CLAUDE_PLUGIN_ROOT}` 占位**：不写死本机绝对路径，保证可移植；
  启动命令为 `uv run --directory <插件根> python -m mcp_server`，经 stdio 协议实测可用。
- **marketplace.json 与 plugin.json 同置 `.claude-plugin/`**：参照官方 superpowers 插件布局，
  省去单独的 marketplace 仓库。

### 3.2 数据流

不变：Claude（skill 指导）→ MCP stdio → mcp_server → 爬虫子进程 →
`data/mcp_runs/<crawl_run_id>/` → read_crawl_data 回读。插件只加入口与说明，不改运行链路。

### 3.3 Git 策略（分支隔离）

- `feature/claude-code-plugin`：我们的插件开发分支（本次工作提交于此）。
- `main`：本地主分支（含上游合并），不与插件提交混杂。
- remote 规划：`origin` → `wanzicong/MediaCrawler`（用户仓库）；
  `upstream` → `NanmiCoder/MediaCrawler`（便于日后同步上游修复）。

## 4. 组件清单

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| .claude-plugin/plugin.json | 新增 | name=mediacrawler, version=1.0.0, mcpServers→./.mcp.json |
| .claude-plugin/marketplace.json | 新增 | 单插件市场清单，source=./ |
| .mcp.json | 新增 | stdio：uv run --directory ${CLAUDE_PLUGIN_ROOT} python -m mcp_server |
| skills/crawl-platform/SKILL.md | 新增 | 平台/模式对照、参数表、登录流程、错误处置 |
| skills/read-crawl-data/SKILL.md | 新增 | crawl_run_id 回读、格式限制、常见错误 |
| skills/media-transcribe/SKILL.md | 新增 | 资产查询→转写→状态→读字幕四工具流水线 |
| skills/mcp-server-ops/SKILL.md | 新增 | stdio/http、启停脚本、环境变量、安全须知 |
| commands/mediacrawler-help.md | 新增 | 帮助命令 |
| docs/插件使用指南.md | 新增 | 安装方式、uv 前置条件、许可证提醒 |

所有文档均为中文 UTF-8；SKILL.md 含合法 YAML frontmatter（name + description）。

## 5. 错误处理与边界

- MCP 启动失败排查路径写入 mcp-server-ops 技能（手动 stdio 启动、看 stderr 日志、查端口）。
- 登录失败、平台风控、DATA_READ_ERROR、抖音个人模式强制 crawl_run_id 等均在技能中写明处置。
- 安全：HTTP 模式无应用层鉴权的风险、公网需上游反向代理，已写入技能与指南。

## 6. 测试与验证

- JSON 语法校验：plugin.json / marketplace.json / .mcp.json 通过。
- SKILL.md frontmatter 与 UTF-8 编码校验通过。
- MCP stdio 协议实测：initialize + tools/list 返回全部 13 个工具。
- 回归：`pytest tests/ test/` → 224 passed, 9 skipped（Redis 依赖 8 例环境性排除）。
- Git 验证（推送后）：`gh repo view` 与 `git ls-remote` 确认提交一致。

## 7. 风险等级：低-中

- 插件文件全部新增，零侵入现有代码。
- merge 冲突解决为中风险点，已完成并测试验证。
- remote 变更可逆（上游地址保留为 upstream）。

## 8. 后续步骤（本次会话内完成）

1. 创建 GitHub 仓库 `wanzicong/MediaCrawler`（public）。
2. origin 改指用户仓库，NanmiCoder 挂为 upstream。
3. 推送 main 与 feature/claude-code-plugin 分支。

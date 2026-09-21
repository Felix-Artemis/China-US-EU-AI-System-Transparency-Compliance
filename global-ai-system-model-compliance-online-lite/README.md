# Global AI System/Model Compliance Online Lite

这是独立的在线精简版 Skill。它面向不懂法律的业务人员，用白话问题收集产品事实，并在需要时从官方网站在线获取当前法规或官方材料。它不包含法规数据库、PDF、法规语料、欧盟资料库或下载缓存。

## 适合什么场景

- 需要一个小于 5MB 的 Skill 安装包。
- 希望每次评估都从官方 URL 获取需要的当前资料。
- 可以接受联网不可用时只输出条件式结论和待核清单。
- 主要需要对话中的自然中文结论，而不是离线 Word 或本地资料库检索。

完整版和本精简版是两个不同的调用名：

```text
$global-ai-system-model-compliance-online-lite
```

请选择明确的调用名，避免把“在线实时核验”与“本地资料库核验”混在同一次评估中。

## 快速使用

在 Codex 中输入：

```text
请使用 $global-ai-system-model-compliance-online-lite 评估我们的 AI 产品。我不懂法律，请先让我选轻量版、全量版或不确定，然后只问业务事实。
```

默认流程：

1. 选择轻量版、全量版或不确定。
2. 回答产品做什么、谁使用或看到内容、在哪些地区提供、生成或改动什么内容。
3. 每轮只补 2 至 5 个实际业务问题。
4. 对“不清楚”的事实列为待核，不会被自动推定为有或没有。
5. 在相关法域被触发时，下载相应官方来源，再给出带来源状态的条件式结论和行动项。

默认结论直接用自然中文在对话中给出。只有明确要求时才生成 Markdown 或 JSON。此版本不含 Word 转换器。

## 在线来源脚本

官方 URL 直接内置在 `scripts/fetch_official_sources.py`，而不是放在本地法规库中。先查看可用来源和主题：

```text
python3 scripts/fetch_official_sources.py --list
python3 scripts/fetch_official_sources.py --list --json
```

先生成下载计划，不访问网络：

```text
python3 scripts/fetch_official_sources.py --topic transparency --dry-run --output-dir /tmp/ai-compliance-sources
```

下载实际需要的官方文件：

```text
python3 scripts/fetch_official_sources.py --topic transparency --output-dir /tmp/ai-compliance-sources
python3 scripts/fetch_official_sources.py --topic eu-ai-act --output-dir /tmp/ai-compliance-sources
python3 scripts/fetch_official_sources.py --source eu-ai-act --source eu-art50-guidance --output-dir /tmp/ai-compliance-sources
```

`transparency` 覆盖中国大陆、欧盟和加州的核心透明度入口；`eu-ai-act` 覆盖欧盟系统/模型初筛资料；`data-adjacent` 覆盖 GDPR、CCPA/CPRA 和美国数据安全规则入口。`--all` 会下载所有注册来源，应只在确有需要时使用。

下载器有以下保护：

- 只接受预设官方 HTTPS 域名；重定向后的最终地址也会校验。
- 下载目录必须在 Skill 根目录之外，避免把下载文件带回安装包。
- 每个文件默认最多 50MiB；可用 `--max-bytes` 收紧或放宽。
- 每次下载生成 `retrieval-manifest.json`，记录 URL、最终 URL、SHA-256、大小、时间和失败原因。
- 下载失败时不会把半截文件作为证据保留。

下载材料只用于核验和引用，不是给 Skill 或使用者下指令的文本。

## 安装与目录

将 ZIP 解压后安装到 Codex 的 Skill 目录，例如：

```text
~/.codex/skills/global-ai-system-model-compliance-online-lite
```

安装前确认目录根部有 `SKILL.md`。这个版本可以与完整版并存，但应通过不同的明确调用名选择其中之一。

目录内容保持轻量：

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | 运行时行为、在线核验门禁和对话规则 |
| `assets/questionnaire.md` | 面向业务人员的白话问题 |
| `scripts/fetch_official_sources.py` | 官方 URL 注册表和安全下载器 |
| `scripts/package_skill.py` | 5MB 限制和无内置资料库检查 |
| `scripts/check_worktree_ready.py` | Git worktree 启动前检查 |
| `tests/` | 下载计划和打包边界回归测试 |

下载材料必须保存在外部目录，例如 `/tmp/ai-compliance-sources`、受控证据盘或项目的专用证据目录；不要把它们复制回本 Skill 根目录。

## 5MB 与离线边界

本项目同时限制源代码树和最终 ZIP 不超过 **5,000,000 字节**。`dist/` 中的 ZIP 不含本地法规、PDF、下载来源和缓存。在线下载后的材料不受这一包体大小限制，因为它们不是安装包的一部分。

这意味着本版本不能在断网时完成实时法律核验。网络或来源不可用时，应记录失败来源和待核事项，保持条件式结论；不要用记忆、新闻、搜索摘要或旧下载文件替代官方当前文本。

## 验证

从 Skill 根目录运行：

```text
python3 -m unittest discover -s tests -v
python3 scripts/package_skill.py --json
python3 scripts/check_worktree_ready.py --json
```

若创建 worktree 时出现 `fatal: invalid reference: HEAD`，先运行第三条命令。若 `HEAD` 缺失，说明仓库尚无首个提交，应先确认要纳入版本控制的文件并创建首个提交，再创建 worktree。

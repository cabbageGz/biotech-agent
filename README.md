# Biotech Agent

生物医药行业情报 Agent 的第一版骨架。

当前 MVP 聚焦每日自动生成一篇“小红书生物医药热点”：

- `ceo_agent`：确定今日选题策略、输出任务简报。
- `research_agent`：从医药行业 RSS 源获取新闻并做热点提炼。
- `content_agent`：生成小红书风格标题、正文、标签和发布要点。
- `workflows/xiaohongshu_flow.py`：串联 CEO -> Research -> Content，并保存运行记录。
- `api/` + `frontend/`：本地控制台，可获取新闻、总结内容、查看发布文案。

## 当前数据源

已接入：

- PubMed：通过 NCBI E-utilities 抓取近期论文摘要信息。
- ClinicalTrials.gov：通过官方 API v2 抓取临床试验记录。
- FDA / openFDA：通过 openFDA drugs@FDA 接口抓取近期药品监管记录。
- BioPharma Dive、Fierce Biotech、Fierce Pharma、Nature Biotechnology、GEN News 等 RSS。

已纳入规划但需要授权或合规爬虫：

- 丁香园 / Insight
- 药明康德官方新闻、投资者关系与交易所公告
- 医药魔方 API
- 企业财报：SEC EDGAR、HKEX、上交所、深交所、公司 IR 页面

数据源总目录见 `tools/sources.json`，RSS 源见 `tools/rss/sources.json`。

## 快速开始

```bash
PYTHONPATH=. python3 -m api.cli serve
```

打开：

```text
http://127.0.0.1:8787
```

也可以命令行直接生成一次：

```bash
PYTHONPATH=. python3 -m api.cli run-once
```

持续每日运行：

```bash
PYTHONPATH=. python3 -m api.cli schedule --time 08:30
```

## 可选 LLM 配置

没有 API key 时，系统会使用规则摘要与模板文案，方便先跑通流程。配置 DeepSeek 后，摘要和文案会更自然：

```bash
DEEPSEEK_API_KEY=你的_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 运行记录

每次生成会写入：

```text
database/runs/<run_id>/
├── ceo_brief.md
├── research_report.md
├── xiaohongshu_post.md
└── run.json
```

## 用户与部署数据

用户、密码哈希、登录会话和使用统计保存在 SQLite：

```text
database/app.db
```

默认管理员：

```text
username: admin
password: 712834
```

后续部署到服务器时，建议把 `database/` 作为持久化目录挂载或一起备份：

- `database/app.db`：用户、权限、统计。
- `database/runs/`：每次生成的文案、研究摘要和图片文件。

代码更新时不要覆盖这两个生产数据目录。

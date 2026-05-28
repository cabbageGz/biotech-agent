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
- 医药魔方 ByDrug：抓取公开首页 SSR 数据中的最新新闻和公开报告，保留原文详情页链接用于证据追溯。
- 药明康德：抓取官网公开的公司新闻和媒体文章。
- BioPharma Dive、Fierce Biotech、Fierce Pharma、Nature Biotechnology、GEN News 等 RSS。

已纳入规划但需要授权或合规爬虫：

- 丁香园 / Insight
- 药明康德投资者关系、交易所公告与财报页面
- 医药魔方深度数据库 / API：需要授权账号、API 凭证或数据合同。
- 企业财报：SEC EDGAR、HKEX、上交所、深交所、公司 IR 页面

数据源总目录见 `tools/sources.json`，RSS 源见 `tools/rss/sources.json`。

## 快速开始

本地开发可以复制一份环境变量模板：

```bash
cp .env.example .env
```

`.env` 只放在本机或服务器上，已经被 `.gitignore` 和 `.dockerignore` 排除，不要提交、不要放进镜像。

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

## 可选图片生成配置

封面图和内容卡片使用阿里云百炼 / DashScope 的通义万相接口。API Key 通过环境变量配置：

```bash
DASHSCOPE_API_KEY=你的_万相_key
WANXIANG_MODEL=wan2.7-image
WANXIANG_IMAGE_SIZE=1024*1024
```

其中 `DASHSCOPE_API_KEY` 是必填；`WANXIANG_MODEL` 和 `WANXIANG_IMAGE_SIZE` 可不填，系统默认分别使用 `wan2.7-image` 和 `1024*1024`。如果服务已经启动，修改环境变量后需要重启后端服务。

如果希望生成图片自动上传到阿里云 OSS，并让网页直接通过 URL 加载图片，继续配置：

```bash
ALIYUN_OSS_ACCESS_KEY_ID=你的_oss_access_key_id
ALIYUN_OSS_ACCESS_KEY_SECRET=你的_oss_access_key_secret
ALIYUN_OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_BUCKET=gzz-agent
ALIYUN_OSS_PUBLIC_BASE_URL=https://gzz-agent.oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_SIGNED_URL_EXPIRES=900
```

`ALIYUN_OSS_BUCKET` 默认是 `gzz-agent`。配置 OSS 后，万相生成的图片会上传到 `biotech-agent/<run_id>/` 路径下，运行记录只保存 OSS object key；发布预览由后端临时签发访问 URL，默认 900 秒过期。导出发布包时，后端再用临时签名 URL 下载图片写入压缩包，不把图片长期落盘到服务器。

如果使用阿里云 OSS Access Point endpoint，例如 `gzz-agent-1326456261273942.oss-cn-beijing.oss-accesspoint.aliyuncs.com`，还需要配置签名用的 access point alias：

```bash
ALIYUN_OSS_ENDPOINT=gzz-agent-1326456261273942.oss-cn-beijing.oss-accesspoint.aliyuncs.com
ALIYUN_OSS_PUBLIC_BASE_URL=https://gzz-agent-1326456261273942.oss-cn-beijing.oss-accesspoint.aliyuncs.com
ALIYUN_OSS_ACCESS_POINT_ALIAS=你的_access_point_alias
```

Access Point 的公网 URL 仍然受 Bucket/Access Point 读权限控制。当前项目默认按私有 Bucket 处理，由后端签发临时访问 URL，不需要公开读。

## 密钥与打包安全

真实密钥只应该出现在服务器环境变量、部署平台 Secret Manager，或服务器本地 `.env` 中。不要把 `.env`、`database/`、导出的发布包、图片缓存打进部署包。

项目里已经做了几层保护：

- `.gitignore`：排除 `.env`、数据库、运行记录、导出包和图片缓存。
- `.dockerignore`：Docker 构建时排除 `.env`、`database/`、`.git/` 等敏感或运行期目录。
- `.env.example`：只保留占位符，方便部署时照着配置。
- `scripts/security_check.py`：打包前扫描明显硬编码密钥。
- `deploy/package.sh`：生成部署压缩包时自动排除敏感文件。

推荐用下面的命令打包上传：

```bash
./deploy/package.sh
```

生成的压缩包在 `deploy/` 目录下，不包含 `.env` 和 `database/`。服务器上单独创建 `.env`，或在 Docker / 云平台中配置环境变量。

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
password: 123456
```

后续部署到服务器时，建议把 `database/` 作为持久化目录挂载或一起备份：

- `database/app.db`：用户、权限、统计。
- `database/runs/`：每次生成的文案、研究摘要和图片文件。

代码更新时不要覆盖这两个生产数据目录。

# 官方政策执行解读智能体

面向政府网站、法规数据库与官方公告中的**政策、制度、通知与申报指南**，在**本地权威语料库**中检索、核对原文后，产出**可直接使用的执行说明**，并给出**条文级、可回溯的引用依据**。

- 技术栈：Python 3.12–3.14 + [`wit` 梧桐智能体开发框架](https://wt.ioa.pub/flux/docs/)（WIT）+ `acps-sdk`
- 接入方式：**WIT/凤翎路径**，注册为 ACPs **Partner**（AIP Direct，mTLS）
- 模型：DeepSeek（OpenAI 兼容协议）
- 检索：纯本地词法检索（SQLite FTS5 + jieba 分词 + BM25），**不依赖任何外部检索服务**

## 交付物（七字段执行说明）

`ExecutionBrief` 的固定结构（见 `src/policy_agent/schema.py`）：

| 字段 | 含义 |
| --- | --- |
| `applicable_subjects` | 政策适用对象 |
| `plain_explanation` | 通俗解释 |
| `action_items` | 需完成的事项 |
| `timeline` | 时间节点 |
| `required_materials` | 材料要求 |
| `risk_notes` | 风险提示 |
| `citations` | 可回溯条文依据（含标题、发文字号、章节、条号、原文、来源） |

同时渲染为 Markdown 报告（`src/policy_agent/render.py`）。

## 核心约束：以官方原文为核心，绝不编造

- 本地语料库是**唯一事实来源**；检索不到时如实回复“未在本地语料库中找到可作为依据的官方原文”，不编造、不进入落地点。
- 所有引用必须经 `policy.brief_assemble` **逐条核验**：
  - `citation_id` 必须真实存在于语料库；
  - `quote` 必须能在该条文原文中找到（归一化后包含）；
  - 无法核验的引用会被**剔除并记入 `warnings`**；若无任何有效引用，`grounded=false`。
- 引用元数据（发文字号、日期、章节、条号、来源）全部由语料库补齐，模型无法自造。

## 快速开始（本地）

```powershell
# 1) 安装（必须“先 SDK，后 wit”，requirements.txt 已固定顺序）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 2) 版本预检（版本、导入来源、wheel 校验和）
policy-agent preflight

# 3) 配置
Copy-Item .env.example .env   # 填入 OPENAI_API_KEY（DeepSeek）

# 4) 导入权威原文（支持 md/txt/html/pdf/docx，可传目录）
policy-agent import .\data\docs

# 5) 检索
policy-agent search "小微企业 创业补贴 申报时间 材料"

# 6) 生成执行说明（调用模型，输出 Markdown；--json 同时导出结构化结果）
policy-agent brief "小微企业如何申报创业补贴？" --out brief.md --json brief.json
```

> 说明：`wit-framework` **不在 PyPI**，两个 wheel 已随仓库放在 `vendor/wheels/`。

## 接入梧桐平台（ACPs Partner）

```powershell
$env:POLICY_PUBLIC_ENDPOINT = "https://<你的公网地址>/acps/aip/v1"   # 平台可达的 HTTPS
$env:POLICY_CERT_DNS        = "<你的公网主机名>"
$env:ACPS_USERNAME          = "<平台账号>"
$env:ACPS_PASSWORD          = "<平台密码>"

policy-agent validate   # 本地校验编译与能力投影
policy-agent acs        # 查看/导出 ACS 草稿
policy-agent register   # 推进注册；首次通常停在 waiting_for_review
policy-agent serve      # 审核通过后启动 Direct Partner listener（mTLS + AMP）
```

接入流程（由 wit 托管）：登录 → 提交 ACS → 平台审核 → 取得 **AIC** → 签发 **mTLS 证书** → 启动 listener。
首次 `register` 返回 `waiting_for_review` 属正常，等平台管理员审核通过后重跑即可。

> **`public_endpoint` 必须平台可达，且证书 SAN 覆盖其主机名。**
> `POLICY_BIND_HOST/PORT` 只是本地 bind；公网地址通过 DNS/反向代理/NAT 映射过去。

## Docker

```powershell
Copy-Item .env.example .env   # 填好 OPENAI_API_KEY / ACPS_* / POLICY_PUBLIC_ENDPOINT
docker compose build

# 本地导入语料
docker compose run --rm policy-agent import /app/data/docs
# 检索
docker compose run --rm policy-agent search "创业补贴 申报"
# 生成执行说明
docker compose run --rm policy-agent brief "小微企业如何申报创业补贴？"
# 上线服务
docker compose up -d policy-agent
```

挂载说明：`./data`（语料库）、`./.wit`（注册身份/证书/状态）、`./certs`（只读）。证书与 `.wit/` **不要提交到 git**。

## 测试

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

覆盖：条文切分、各格式导入（md/txt/html/docx）、FTS5+分词检索排序、引文核验（真/假）、
`ExecutionBrief` 落地点、Markdown 七段渲染、`compile()` 无诊断、ACS 草稿技能与 mTLS 端点、
以及**离线假 Provider 驱动的完整能力链路**（含“无出处则如实返回”）。

## 目录结构

```text
src/policy_agent/
├── schema.py         # ExecutionBrief / ArticleCitation 等领域类型
├── capabilities.py   # policy.* 四个公开能力 + 唯一落地点 assemble_brief
├── agent.py          # WitAgent 装配（模型/指令/能力/协议）
├── provider.py       # DeepSeek Provider（+ 离线占位 Provider）
├── render.py         # ExecutionBrief -> Markdown
├── serving.py        # AcpsConfig / 注册 / serve_direct_partner
├── cli.py            # policy-agent 命令行
└── corpus/           # 导入(md/txt/html/pdf/docx) / 条文切分 / SQLite+FTS5 检索
```

## 已知边界（v1）

- 仅 Partner（AIP Direct `rpc`+`stream`）；不做 AIP Group、不自建 Leader/Web。
- 纯词法检索（无向量）；同义改写召回有限，建议导入充足原文并善用关键词。
- `policy.brief_assemble` 的结构化结果随工具结果返回，并可由 CLI `--json` 导出；
  AIP Product 的正文是 Markdown 报告。
- 线上注册审批由平台管理员完成，属外部手工步骤。

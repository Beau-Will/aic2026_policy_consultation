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

## 快速开始

支持 **Linux / macOS / Windows**。Docker 方式三平台一致，推荐优先使用；若要在宿主机直接跑 Python，见方式 B。

### 方式 A：Docker（推荐，Linux / macOS / Windows 通用）

```bash
# 1) 准备目录与配置
mkdir -p data/docs
cp .env.example .env      # Windows PowerShell: Copy-Item .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（DeepSeek）

# 2) 构建镜像
docker compose build

# 3) 导入语料（把法规原文放到宿主机 data/docs/，可分子目录）
docker compose run --rm policy-agent import /app/docs

# 4) 检索 + 生成执行说明
docker compose run --rm policy-agent search "小微企业 创业补贴 申报时间"
docker compose run --rm policy-agent brief "小微企业如何申报创业补贴？"

# 5) 上线服务（ACPs 注册到位后，mTLS + AMP）
docker compose up -d policy-agent
docker compose logs -f policy-agent
```

> **Linux 不会遇到卷权限问题**：可写状态（语料索引 + 注册身份/证书）放在命名卷 `policy-state`，
> 原文目录只读挂载，容器不会写你的宿主机文件，也**不需要 chown**。

<details>
<summary>想让 data/ 与 .wit/ 直接出现在宿主机目录？（Linux 需注意属主）</summary>

把 `docker-compose.yml` 的 `volumes` 换成 bind mount：

```yaml
    volumes:
      - ./data:/app/state
      - ./data/docs:/app/docs:ro
```

**Linux 下必须先让宿主机目录对容器内 uid `10001` 可写**，否则会报数据库无法写入：

```bash
mkdir -p data/docs .wit
sudo chown -R 10001:10001 data .wit
```

macOS / Windows(Docker Desktop) 的 bind mount 会自动做 uid 映射，通常无需处理。
</details>

### 方式 B：本机 venv

**Linux / macOS**

```bash
bash scripts/setup.sh       # 建目录 + 生成 .env + 装依赖 + 发行预检，一步到位
```

或手动：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
policy-agent preflight
```

日常使用：

```bash
source .venv/bin/activate
policy-agent import ./data/docs
policy-agent search "小微企业 创业补贴 申报时间 材料"
policy-agent brief "小微企业如何申报创业补贴？" --out brief.md --json brief.json
```

**Windows（PowerShell）**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

或手动：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

日常使用：

```powershell
policy-agent import .\data\docs
policy-agent search "小微企业 创业补贴 申报时间 材料"
policy-agent brief "小微企业如何申报创业补贴？" --out brief.md --json brief.json
```

> 说明：`wit-framework` **不在 PyPI**，两个 wheel 已随仓库放在 `vendor/wheels/`。
> 安装顺序必须**先 `acps-sdk 2.2.0`、再 `wit-framework 2.1.0`**，`requirements.txt` 已固定该顺序。

## 语料放哪里、怎么组织

### 放这里

**默认目录：`data/docs/`**（相对仓库根目录）

```bash
# Linux / macOS
mkdir -p data/docs
cp /path/to/你的政策库/*.pdf data/docs/     # 示例；扫描是递归的，可分子目录
policy-agent import ./data/docs             # 传目录 = 导入所有支持的文件
```

```powershell
# Windows PowerShell 等价写法
New-Item -ItemType Directory -Force -Path .\data\docs | Out-Null
Copy-Item "D:\我的政策库\*" -Destination .\data\docs\ -Recurse
.\.venv\Scripts\policy-agent.exe import .\data\docs
```

> 未激活虚拟环境时：Linux / macOS 用 `./.venv/bin/policy-agent`，Windows 用 `.\.venv\Scripts\policy-agent.exe`。

`data/` 已在 `.gitignore` 中，**原文不会进 git 仓库**（体积大、且未必可公开分发），只保存在你本地。
Docker 方式下该目录以**只读**方式挂进容器（`/app/docs`），容器不会改写你的文件。

### 支持的文件类型

`.md` / `.markdown` / `.txt` / `.html` / `.htm` / `.pdf` / `.docx`

> 扫描是**递归**的：子目录里的文件都会被导入，放心按层级建目录。
> 以 `_` 或 `.` 开头的文件会被跳过（方便在语料目录里放说明/索引文件）。
> 不支持的格式（`.doc` / `.wps` / `.rtf` / `.odt` 等）会在导入时给出提示，请先另存为 `.docx` 或导出 PDF。

### 建议的目录结构

不强制，但按“层级 / 年份 / 类型”分开，后续好维护、也好替换更新：

```text
data/docs/
├── 国家级/
│   ├── 法律/          中华人民共和国中小企业促进法.pdf
│   ├── 行政法规/      优化营商环境条例.docx
│   └── 部门规章/      财政部关于印发…的通知.pdf
├── 省级/
│   └── XX省/           XX省创业补贴实施办法.md
└── 市级/
    └── XX市/           X人社发〔2024〕7号 创业补贴申报通知.html
```

### 文件名建议（重要）

导入时 `doc_id` 由**文件名 + 文件路径**生成，所以：

- ✅ **同一路径重新导入会覆盖旧版本**——政策更新时，用新文件覆盖同名文件再导一次即可（命令行显示 `[更新]`）。
- ✅ **不同目录下的同名文件不会互相覆盖**（如 `2024/通知.pdf` 与 `2025/通知.pdf` 是两条）。
- 💡 建议用**能分辨内容**的文件名（如带上发文字号：`X人社发〔2024〕7号-创业补贴申报通知.pdf`），检索结果与引用标题会更易读。
- 💡 需要完全自定义编号时，单文件导入可加 `--doc-id`：

```bash
policy-agent import ./data/docs/某文件.pdf --doc-id 中小企业促进法-2024
```

### 元数据（可选，但建议）

发文字号、发文机关、发布日期会**自动识别**（含“国务院令第N号”），施行日期只在原文写明“自…起施行”时才填。
识别不准时可在导入时显式指定（单文件）：

```bash
# Linux / macOS
policy-agent import ./data/docs/某通知.pdf \
  --title "XX市创业补贴申报通知" \
  --issuer "XX市人力资源和社会保障局" \
  --doc-number "X人社发〔2024〕7号" \
  --publish-date 2024-03-05 \
  --source-url "https://example.gov.cn/xxx"
```

```powershell
# Windows PowerShell（用反引号续行）
.\.venv\Scripts\policy-agent.exe import .\data\docs\某通知.pdf `
  --title "XX市创业补贴申报通知" `
  --issuer "XX市人力资源和社会保障局" `
  --doc-number "X人社发〔2024〕7号" `
  --publish-date 2024-03-05 `
  --source-url "https://example.gov.cn/xxx"
```

> 这些元数据会原样出现在最终报告的「条文依据」里，是**可回溯**的关键，正式语料建议补齐。

### 导入后自检

```bash
policy-agent stats                       # 文档数 / 条文数
policy-agent search "创业补贴 申报 材料"   # 能否检索到目标条文
```

检索不到就换关键词，或确认原文里确实有这些字——**检索不到就不会产出结论**（这是“不编造”的设计）。

### Docker 方式下的语料

原文放到宿主机 `data/docs/` 即可，容器内路径是 `/app/docs`：

```bash
docker compose run --rm policy-agent import /app/docs
docker compose run --rm policy-agent search "创业补贴 申报"
```

## 接入梧桐平台（ACPs Partner）

### 先搞懂两个“地址”变量

- **`POLICY_PUBLIC_ENDPOINT` = 你智能体在互联网上的“门牌号”**：平台用它来找到并调用你。
  格式固定为 `https://<主机名或IP>/acps/aip/v1`，且必须**平台可达**。
- **`POLICY_CERT_DNS` = 上面那个门牌号的主机名**，会写进你的 mTLS 证书。
  **通常留空即可**（程序自动从 endpoint 推导；IP 会自动写成 IP SAN）。

对照一下：`POLICY_BIND_HOST/PORT` 是**你本机监听**的地址（一般 `0.0.0.0`/`8443`，不用改），
而 `POLICY_PUBLIC_ENDPOINT` 是**给平台看的对外地址**——两者可以不同（靠 DNS/端口映射/隧道对应起来）。

### 三种填法（按你的情况选一个）

| 你的情况 | 怎么填 | 例子 |
| --- | --- | --- |
| 有云服务器公网 IP / 域名 | 直接把域名或 IP 写进去 | `POLICY_PUBLIC_ENDPOINT=https://agent.example.com/acps/aip/v1` |
| 只有自己的电脑（无公网 IP） | 用**内网穿透(隧道)**，填隧道给的公网主机名 | `https://<隧道主机名>:<端口>/acps/aip/v1` |
| 赛方 / 单位给了机器 | **先问主办方**要主机名/端口，再照上面填 | `https://<赛方给的主机名>/acps/aip/v1` |

> ⚠️ 用隧道时必须是 **TCP 透传（L4）**，不能用会终止 TLS 的 HTTP 反向代理——
> mTLS 的双向认证要由你自己的 listener 端到端完成（如 `ngrok tcp 8443`、frp `type=tcp`）。
>
> 暂时没地址也没关系：`import` / `search` / `brief` / `validate` / `acs` 都不需要它，
> 可以先本地把一切跑通，拿到地址后再 `register`。

详细说明见 [docs/registration.md](docs/registration.md)。

### 执行

在 `.env` 里填好下列值（三平台一致）：

```ini
POLICY_PUBLIC_ENDPOINT=https://agent.example.com/acps/aip/v1
POLICY_CERT_DNS=
ACPS_USERNAME=<平台账号>
ACPS_PASSWORD=<平台密码>
```

也可以临时用环境变量覆盖：

```bash
# Linux / macOS
export POLICY_PUBLIC_ENDPOINT="https://agent.example.com/acps/aip/v1"
```

```powershell
# Windows PowerShell
$env:POLICY_PUBLIC_ENDPOINT = "https://agent.example.com/acps/aip/v1"
```

然后依次执行：

```bash
policy-agent validate   # 本地校验编译与能力投影（不需要 endpoint）
policy-agent acs        # 查看/导出 ACS 草稿
policy-agent register   # 推进注册；首次通常停在 waiting_for_review
policy-agent serve      # 审核通过后启动 Direct Partner listener（mTLS + AMP）
```

接入流程（由 wit 托管）：登录 → 提交 ACS → 平台审核 → 取得 **AIC** → 签发 **mTLS 证书** → 启动 listener。
首次 `register` 返回 `waiting_for_review` 属正常，等平台管理员审核通过后重跑即可。

## Docker 卷、网络与 Linux 说明

| 项 | 设计 | 原因 |
| --- | --- | --- |
| 语料原文 | `./data/docs` **只读**挂载到 `/app/docs` | 容器不写宿主机文件，Linux 无需 chown |
| 运行态（索引 + 身份/证书） | 命名卷 `policy-state` 挂到 `/app/state` | 卷由镜像创建时继承 uid 10001，Linux 下可写 |
| 容器内 uid | `10001`（非 root） | 最小权限 |
| `host.docker.internal` | 通过 `extra_hosts: host-gateway` 注入 | Linux 上默认不解析该名称 |

容器需要**出网**访问：DeepSeek（`api.deepseek.com`）与梧桐平台（`wt.ioa.pub`，含 AMP 上报端口）。

常用运维命令：

```bash
docker compose build                 # 重建镜像
docker compose run --rm policy-agent <子命令>   # 一次性执行 CLI
docker compose up -d policy-agent    # 后台启动服务
docker compose logs -f policy-agent  # 跟踪日志
docker compose down                  # 停止

# 查看/重置运行态卷（重置会清空语料索引与注册身份）
docker volume inspect wt_policy-state
docker compose down -v && docker compose up -d
```

> 若要把运行态也放到宿主机可见目录，见「快速开始 · 方式 A」里的 bind mount 说明（Linux 需 `chown 10001`）。
> 证书与 `.wit/` **不要提交到 git**。

## 测试

```bash
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

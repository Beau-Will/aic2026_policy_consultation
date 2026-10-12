# 接入梧桐平台（ACPs Partner）运行手册

> 面向参加 2026AIC 算法大赛、走 **WIT/凤翎路径** 的开发者。
> 本项目的注册、证书与 listener 全部由 `wit` 托管，本手册只讲“怎么做”。
> 命令以 **Linux / macOS** 为主，关键处给出 Windows PowerShell 等价写法；Docker 方式三平台一致。

## 0. 先厘清概念

| 入口 | 是什么 | 你需要做什么 |
| --- | --- | --- |
| `https://wt.ioa.pub/flux/login` | 凤翎（Flux）Web 控制台登录页（Keycloak SSO） | 只用来登录 / 管理技能包，**不是安装页**，无需也无法在此“搭建” |
| `https://wt.ioa.pub/registry/` | ACPs 智能体注册平台 | 查看提交与审核状态 |
| 本文档 | 把自己的 Python 智能体注册为可被调用的 Partner | 按下文执行 |

## 1. 准备环境

**Linux / macOS**

```bash
bash scripts/setup.sh          # 建目录 + 生成 .env + 装依赖 + 发行预检，一步到位
source .venv/bin/activate
```

或手动：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt   # 先 acps-sdk 2.2.0，再 wit-framework 2.1.0
policy-agent preflight                       # 版本 / 导入来源 / wheel 校验和
```

**Windows (PowerShell)**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\policy-agent.exe preflight
```

## 2. 准备语料（决定结论是否有依据）

```bash
policy-agent import ./data/docs      # md/txt/html/pdf/docx，可传目录（递归扫描）
policy-agent stats
policy-agent search "关键词 关键词"    # 确认能检索到目标条文
```

```powershell
.\.venv\Scripts\policy-agent.exe import .\data\docs
```

## 3. 配置 `.env`（本节是重点）

```bash
cp .env.example .env      # Windows PowerShell: Copy-Item .env.example .env
```

然后填这几项：

| 变量 | 是否必填 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 必填 | DeepSeek API Key（`brief` / `serve` 会真正调用模型） |
| `ACPS_USERNAME` / `ACPS_PASSWORD` | 必填 | 梧桐平台账号 |
| `ACPS_PROFILE` | 必填 | `wt` = **2026AIC 大赛平台**（`wt.ioa.pub`，默认）；`ioa` = wit 内置的 `www.ioa.pub`（**账号不通用**，填错报 `401 USER_NOT_FOUND`） |
| `POLICY_PUBLIC_ENDPOINT` | 必填 | **平台用来找到并调用你的地址**（见下） |
| `POLICY_CERT_DNS` | 一般留空 | 通常会自动推导；只有特殊需要用别的名字时才填 |
| `POLICY_BIND_HOST` / `POLICY_BIND_PORT` | 不用改 | 你**本机**监听的地址/端口（`0.0.0.0` / `8443`） |

### 3.1 一句话理解这两个变量

- **`POLICY_PUBLIC_ENDPOINT` = 你智能体在互联网上的“门牌号”**。平台就是拿这个地址来调用你的。
- **`POLICY_CERT_DNS` = 这个门牌号的主机名**，会被写进你的 mTLS 证书，用来向平台证明“这个地址真的是你”。

> 关键点：**先有地址，才有证书**。所以你要先想清楚“平台能从哪个地址访问到我”，再谈填值。

**为什么要证书？** 平台和你的智能体之间是**双向 TLS（mTLS）**：平台验证你的证书，
你也验证平台的证书。证书由平台 CA 依据你填的 `POLICY_CERT_DNS` 签发，
所以**证书里的名字必须和公开地址的主机名一致**，否则平台连上你也会因证书不匹配而失败。

### 3.2 `POLICY_PUBLIC_ENDPOINT` 的固定格式

```
https://<主机名或IP>/acps/aip/v1
```

三条硬性要求：

1. 必须 `https://` 开头（严格互操作模式强制）；
2. 结尾必须 `/acps/aip/v1`；
3. **主机名/IP 必须能被平台侧访问到**（公网可达，或在平台内网可达）。

### 3.3 按你的实际情况填（三选一）

#### 情况 A：你有云服务器公网 IP / 域名（最标准）

把智能体跑在那台机器上（或让那台机器转发到你的电脑），并放行端口。

```ini
POLICY_BIND_HOST=0.0.0.0
POLICY_BIND_PORT=8443
POLICY_PUBLIC_ENDPOINT=https://agent.example.com/acps/aip/v1
POLICY_CERT_DNS=                      # 留空即可，会自动用 agent.example.com
```

> 云服务器安全组 / 防火墙要放行对应端口；URL 里带端口也可以，
> 例如 `https://203.0.113.10:8443/acps/aip/v1`。

#### 情况 B：你只有自己的电脑（家里 / 公司，没有公网 IP）→ 用内网穿透

用**隧道工具**把公网入口转发到你本机的 `8443`。隧道会给你一个公网主机名，把它填进去：

```ini
POLICY_BIND_HOST=0.0.0.0
POLICY_BIND_PORT=8443
POLICY_PUBLIC_ENDPOINT=https://<隧道分配的主机名>:<隧道端口>/acps/aip/v1
POLICY_CERT_DNS=                      # 留空即可
```

⚠️ **隧道必须是 TCP 透传（L4），不能是会终止 TLS 的 HTTP 反向代理**。
因为 mTLS 的双向认证必须由你自己的 listener 端到端完成。

| 工具 | 正确用法 | 说明 |
| --- | --- | --- |
| ngrok | `ngrok tcp 8443` | 不要用 `ngrok http`（会终止 TLS） |
| frp | `[proxy] type = "tcp"` | 标准 L4 透传 |
| cpolar | 选择 **TCP 隧道** | 免费版可能限端口/时长 |
| 花生壳 | TCP 映射 | — |
| Cloudflare Tunnel | 默认 HTTP 层，**不适用**；需要 Spectrum（付费） | — |

#### 情况 C：赛方 / 单位提供了机器或接入环境

**最省事，优先问主办方**：有没有指定服务器、域名、端口，
以及平台能不能访问你的网络。拿到主机名后按情况 A 填即可。

> 如果暂时拿不到可达地址：没关系。你仍然可以完整本地开发和自测
> （`import` / `search` / `brief` / `validate` / `acs` 都不需要 endpoint），
> 等有了地址再执行 `register`。

### 3.4 `POLICY_CERT_DNS` 到底填什么

**一句话：留空就行。** 程序会自动从 `POLICY_PUBLIC_ENDPOINT` 取主机名。

| 你的 PUBLIC_ENDPOINT | 自动得到的证书 SAN | 要不要手动填 |
| --- | --- | --- |
| `https://agent.example.com/acps/aip/v1` | `agent.example.com`（DNS SAN） | 留空 |
| `https://203.0.113.10/acps/aip/v1` | `203.0.113.10`（IP SAN） | 留空 |

只有这些情况才手动填：**你想用与 endpoint 不同的主机名接入**（多个用英文逗号分隔）。
填的是**纯主机名**，不要带 `https://`、不要带端口和路径。

### 3.4b 确认平台 profile 别填错（很容易踩的坑）

框架内置了**两个不同的部署**，账号**不通用**：

| profile | 平台 | 注册服务地址 |
| --- | --- | --- |
| `wt`（默认，参赛用这个） | 2026AIC 大赛平台 | `https://wt.ioa.pub/registry-server` |
| `ioa` | wit 内置 ioa.pub | `https://www.ioa.pub/registry` |

填错的表现是登录报 `401 USER_NOT_FOUND`——这不是密码错，而是「账号在这个平台上不存在」。
自查命令（会打印实际使用的地址）：

```bash
policy-agent validate      # 看输出里的 platform.registry_url
```

需要指向其它环境时，用环境变量覆盖：

```bash
ACPS_REGISTRY_URL=https://... ACPS_CA_URL=https://... ACPS_DISCOVERY_URL=https://... policy-agent register
```

### 3.5 怎么自测“平台能不能访问到我”

1. 先启动：`policy-agent serve`（保持前台运行）。
2. 从**另一台不在你局域网的机器**（手机热点、朋友电脑、云主机）执行：

```bash
# 测 TCP 连通性
nc -vz <你的主机名> <端口>        # 或: timeout 5 bash -c "</dev/tcp/<主机名>/<端口>" && echo open

# 触发一次 TLS 握手
curl -vk https://<你的主机名>:<端口>/
```

```powershell
# Windows 等价写法
Test-NetConnection <你的主机名> -Port <端口>
curl.exe -vk https://<你的主机名>:<端口>/
```

- 能连上 TCP 说明网络通。
- `curl` 报证书/TLS 相关错误 **是正常的**——因为你没有平台的客户端证书，
  双向认证被拒绝恰恰说明“TLS 端口通了、双向认证生效了”。

## 4. 本地校验并生成 ACS

```bash
policy-agent validate         # 编译无诊断、四个技能已投影、协议绑定正确
policy-agent acs              # 打印 ACS 草稿（可 --out 保存）
```

`ACS` 是智能体对外的“能力名片”，由 `WitAgent` 的能力声明与协议绑定自动生成；
工作区里的 token、私钥、状态文件**不会**进入 ACS。

`validate` 会同时打印 `public_endpoint` 与 `certificate_san`，便于自查证书会签成什么名字。

## 5. 推进注册（可能停在“待审核”）

```bash
policy-agent register
```

状态机：`登录 → 提交 ACS 草稿 → 平台审核 → 分配 AIC → 签发 mTLS 证书 → 落地身份`。

- 首次通常返回 `waiting_for_review`，属**正常**：等平台管理员在注册平台审核通过。
- 审核通过后**重跑** `policy-agent register`，会继续推进到 `active`。

## 6. 启动并上线

```bash
policy-agent serve            # 启动 AIP Direct listener（mTLS + AMP）
```

- listener 使用已验证的 mTLS 身份，严格模式要求 TLS 1.3 + `CERT_REQUIRED`。
- AMP 已开启（heartbeat / system / metrics），供平台监控与排名统计。
- 上线后用平台侧（Discovery / 叮当）确认可被发现并调用。

生产环境建议用 Docker 常驻（`docker compose up -d policy-agent`），
注意 `POLICY_PUBLIC_ENDPOINT` 要指向容器对外可达的地址。

## 7. Docker 方式（Linux / macOS / Windows 通用）

```bash
mkdir -p data/docs                # 放原文
cp .env.example .env              # 填好密钥与接入参数
docker compose build
docker compose run --rm policy-agent import /app/docs
docker compose run --rm policy-agent search "关键词"
docker compose up -d policy-agent
docker compose logs -f policy-agent
```

- 可写状态在命名卷 `policy-state`，**Linux 下无需 chown 宿主机目录**。
- 原文目录以只读方式挂在 `/app/docs`。
- 容器需能**出网**访问 DeepSeek 与 `wt.ioa.pub`（含 AMP 上报端口）。
- 证书与 `.wit/` **不要提交到 git**。

## 8. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| 提示“缺少 POLICY_PUBLIC_ENDPOINT” | `.env` 里还没填对外地址，见 §3.3 |
| 提示“必须以 https:// 开头” | 写成了 `http://`，严格模式不接受 |
| 提示“解析不出主机名” | 写成了 `https:///acps/aip/v1`，缺主机名 |
| `缺少 OPENAI_API_KEY` | `brief`/`serve` 需要真实 DeepSeek Key；确认 `.env` 已被读取 |
| `waiting_for_review` | 等平台管理员审核，通过后重跑 `register` |
| 证书 SAN 校验失败 | `POLICY_CERT_DNS` 与 public endpoint 主机名不一致 |
| 平台调用超时 | 地址不可达：DNS/端口/防火墙/隧道未打通（或用了终止 TLS 的 HTTP 反代） |
| 检索不到目标条文 | 语料未导入或关键词不匹配；换关键词或补录原文 |
| `scripts/setup.sh: /usr/bin/env: bad interpreter` | 脚本被 CRLF 污染；确认 `.gitattributes` 生效后重新 checkout |

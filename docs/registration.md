# 接入梧桐平台（ACPs Partner）运行手册

> 面向参加 2026AIC 算法大赛、走 **WIT/凤翎路径** 的开发者。
> 本项目的注册、证书与 listener 全部由 `wit` 托管，本手册只讲“怎么做”。

## 0. 先厘清概念

| 入口 | 是什么 | 你需要做什么 |
| --- | --- | --- |
| `https://wt.ioa.pub/flux/login` | 凤翎（Flux）Web 控制台登录页（Keycloak SSO） | 只用来登录 / 管理技能包，**不是安装页**，无需也无法在此“搭建” |
| `https://wt.ioa.pub/registry/` | ACPs 智能体注册平台 | 查看提交与审核状态 |
| 本文档 | 把自己的 Python 智能体注册为可被调用的 Partner | 按下文执行 |

## 1. 准备环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt   # 先 acps-sdk 2.2.0，再 wit-framework 2.1.0
policy-agent preflight                        # 版本 / 导入来源 / wheel 校验和
```

## 2. 准备语料（决定结论是否有依据）

```powershell
policy-agent import .\data\docs              # md/txt/html/pdf/docx，可传目录
policy-agent stats
policy-agent search "关键词 关键词"            # 确认能检索到目标条文
```

## 3. 配置模型与接入参数

复制 `.env.example` 为 `.env` 并填写：

- `OPENAI_API_KEY`：DeepSeek API Key（模型走 OpenAI 兼容协议）。
- `ACPS_USERNAME` / `ACPS_PASSWORD`：梧桐平台注册账号。
- `POLICY_PUBLIC_ENDPOINT`：**平台可达的 HTTPS 地址**，形如 `https://your-host/acps/aip/v1`。
- `POLICY_CERT_DNS`：上面的主机名（留空会自动从 endpoint 推导）。

> ⚠️ `POLICY_BIND_HOST/PORT` 只是本机监听地址；平台要访问的是 `POLICY_PUBLIC_ENDPOINT`。
> 两者可以不同（经 DNS / 反向代理 / NAT 映射），但证书 SAN 必须覆盖 public endpoint 的主机名。

## 4. 本地校验并生成 ACS

```powershell
policy-agent validate         # 编译无诊断、四个技能已投影、协议绑定正确
policy-agent acs              # 打印 ACS 草稿（可 --out 保存）
```

`ACS` 是智能体对外的“能力名片”，由 `WitAgent` 的能力声明与协议绑定自动生成；
工作区里的 token、私钥、状态文件**不会**进入 ACS。

## 5. 推进注册（可能停在“待审核”）

```powershell
policy-agent register
```

状态机：`登录 → 提交 ACS 草稿 → 平台审核 → 分配 AIC → 签发 mTLS 证书 → 落地身份`。

- 首次通常返回 `waiting_for_review`，属**正常**：等平台管理员在注册平台审核通过。
- 审核通过后**重跑** `policy-agent register`，会继续推进到 `active`。

## 6. 启动并上线

```powershell
policy-agent serve            # 启动 AIP Direct listener（mTLS + AMP）
```

- listener 使用已验证的 mTLS 身份，严格模式要求 TLS 1.3 + `CERT_REQUIRED`。
- AMP 已开启（heartbeat / system / metrics），供平台监控与排名统计。
- 上线后用平台侧（Discovery / 叮当）确认可被发现并调用。

## 7. Docker 方式

```powershell
Copy-Item .env.example .env      # 填好密钥与接入参数
docker compose build
docker compose run --rm policy-agent import /app/data/docs
docker compose run --rm policy-agent search "关键词"
docker compose up -d policy-agent
```

容器需能**出网**访问 DeepSeek 与 `wt.ioa.pub`（含 AMP 上报端口）。
证书与 `.wit/` 通过 volume 持久化，**不要提交到 git**。

## 8. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `缺少 OPENAI_API_KEY` | 未配置 `.env`；`brief`/`serve` 需要真实 Key |
| `waiting_for_review` | 等待平台管理员审核，通过后重跑 `register` |
| 证书 SAN 校验失败 | `POLICY_CERT_DNS` 未覆盖 public endpoint 主机名 |
| 平台调用超时 | `POLICY_PUBLIC_ENDPOINT` 不可达（DNS/端口/反代/NAT 未打通） |
| 检索不到目标条文 | 语料未导入或关键词不匹配；换关键词或补录原文 |

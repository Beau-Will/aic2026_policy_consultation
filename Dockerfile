# 官方政策执行解读智能体（wit / ACPs Partner）
#
# 纯 Linux 基础镜像，Linux / macOS / Windows(Docker Desktop) 通用。
# 容器内固定 CPython 3.13，与 wit 的 cp312/313/314 发行 wheel 精确匹配。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 出网 HTTPS（DeepSeek / wt.ioa.pub）所需的根证书
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# 非 root 运行（uid/gid 10001）
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home app

WORKDIR /app

# 1) 平台发行 wheel（不在 PyPI，随仓库 vendor）
COPY vendor/wheels /app/vendor/wheels
COPY pyproject.toml README.md /app/
COPY src /app/src

# 2) 安装顺序不可颠倒：先 acps-sdk 2.2.0，再 wit-framework 2.1.0
RUN python -m pip install --upgrade pip \
 && python -m pip install \
      /app/vendor/wheels/acps_sdk-2.2.0-py3-none-any.whl \
      /app/vendor/wheels/wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl \
 && python -m pip install -e /app

# 3) 运行态目录
#    /app/state -> 语料索引与注册身份/证书（建议用命名卷，避免 Linux 宿主目录权限问题）
#    /app/docs  -> 权威原文（建议只读挂载宿主机目录）
RUN mkdir -p /app/state /app/docs \
 && chown -R app:app /app

USER app

ENV POLICY_CORPUS_DB=/app/state/corpus.db \
    POLICY_DOCS_DIR=/app/docs \
    POLICY_WORKSPACE=/app/state/.wit

EXPOSE 8443

ENTRYPOINT ["policy-agent"]
CMD ["serve"]

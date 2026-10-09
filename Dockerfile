# 官方政策执行解读智能体（wit / ACPs Partner）
# 与宿主 Python 版本解耦：容器内固定 CPython 3.13，契合 wit 的 cp312/313/314 发行 wheel。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 非 root 运行
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

# 3) 运行态目录（通过 volume 挂载）
RUN mkdir -p /app/data /app/.wit /app/certs \
 && chown -R app:app /app

USER app

ENV POLICY_CORPUS_DB=/app/data/corpus.db \
    POLICY_DOCS_DIR=/app/data/docs \
    POLICY_WORKSPACE=/app/.wit

EXPOSE 8443

ENTRYPOINT ["policy-agent"]
CMD ["serve"]

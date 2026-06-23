# Stage 1: Builder — 安装依赖
FROM python:3.13-slim AS builder

# 安装 uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# 先复制依赖配置，利用 Docker 缓存层
COPY pyproject.toml uv.lock ./

# 安装生产依赖（不装项目本身，利用缓存）
RUN uv sync --no-dev --frozen --no-install-project

# Stage 2: Runner — 运行服务
FROM python:3.13-slim AS runner

# 安装 uv（运行时需要 uv run 来启动入口）
RUN pip install --no-cache-dir uv

WORKDIR /app

# 从 builder 复制已安装的 site-packages
COPY --from=builder /app/.venv ./.venv

# 复制项目源码和规则文件
COPY src/ ./src/
COPY rules/ ./rules/

# 把 .venv bin 加入 PATH
ENV PATH="/app/.venv/bin:$PATH"

# 暴露服务端口
EXPOSE 8000

# 默认启动 Web 服务
CMD ["uv", "run", "auto-qc-tool", "web", "--host", "0.0.0.0"]

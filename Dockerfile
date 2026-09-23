# ─── 阶段1：前端 build（产物 /web/dist）───
# 配合根目录 .dockerignore 排除 **/node_modules/，
# alpine 内 npm ci 会重新生成 Linux shebang 的 .bin/ shim。
FROM node:20-alpine AS web-build
WORKDIR /web
COPY faheng-web/package*.json ./
RUN npm ci
COPY faheng-web ./
RUN npm run build

# ─── 阶段2：单 uvicorn 进程 serve 静态 + API ───
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 后端依赖（单独缓存层）
COPY faheng-api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 后端业务代码
COPY faheng-api/app ./app
COPY faheng-api/scripts ./scripts
COPY faheng-api/rules ./rules

# 构建期生成内置测试合同（sample 随镜像只读发布，运行时无副本）
RUN python scripts/make_sample_docx.py \
    && ls -lh sample_contract.docx

# 前端 build 产物（来自阶段1）
COPY --from=web-build /web/dist ./web_dist

# 非 root 运行
RUN useradd --create-home --shell /bin/bash faheng \
    && chown -R faheng:faheng /app
USER faheng

EXPOSE 58069

# 健康探活：复用 /api/health（也会打一次 LLM 网关，部署时按需裁剪）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:58069/api/health', timeout=4).status==200 else 1)"

# --proxy-headers：前置 LB / Cloudflare Tunnel 时信任 X-Forwarded-Proto，
# Swagger UI 重定向会保留正确 scheme
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "58069", "--proxy-headers"]
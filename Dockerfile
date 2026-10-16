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
# scripts 需可执行：gen_cert.sh（容器内生成自签证书）、docker_start.sh 由
# /usr/local/bin 副本执行；chmod 放这里保证 tar 离线交付不依赖构建机权限位
RUN chmod +x scripts/*.sh
COPY faheng-api/rules ./rules
# contract-copilot.skill 知识库（git submodule 内容；
# 构建时需保证仓库含 submodule 文件，否则 skill 注入静默失效）
COPY faheng-api/skills ./skills

# 构建期生成内置测试合同（sample 随镜像只读发布，运行时无副本）
RUN python scripts/make_sample_docx.py \
    && ls -lh sample_contract.docx

# 前端 build 产物（来自阶段1）
COPY --from=web-build /web/dist ./web_dist

# 非 root 运行（uid 见 useradd；宿主机挂载 TLS 证书时需 chown 1000:1000）
RUN useradd --create-home --shell /bin/bash faheng \
    && chown -R faheng:faheng /app
USER faheng

# TLS 证书不进镜像（密钥不该留在镜像层）：运行时 -v 挂载 + TLS_CERT/TLS_KEY
# 环境变量开启 HTTPS。证书生成不依赖宿主机 openssl（离线服务器可能没装），
# 直接用镜像自带 openssl 在容器内生成（README「HTTPS（自签名证书）」章节）：
# docker run --rm -v $(pwd)/tls:/tls -u 0 faheng:latest /bin/bash /app/scripts/gen_cert.sh <IP>
COPY --chown=faheng:faheng faheng-api/scripts/docker_start.sh /usr/local/bin/docker_start.sh
RUN chmod 755 /usr/local/bin/docker_start.sh

EXPOSE 58069

# 健康探活：进程存活检查（/api/health 默认不打 LLM——探活不该烧 token；
# 登录后的网关检查走 /api/health?llm=1，由前端触发）
# TLS_CERT 设置时自动切 https（自签证书用 unverified 上下文，避免误报 unhealthy）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import os,sys,ssl,urllib.request as u; \
tls=os.environ.get('TLS_CERT'); \
ctx=ssl._create_unverified_context() if tls else None; \
url=('https' if tls else 'http')+'://127.0.0.1:58069/api/health'; \
sys.exit(0 if u.urlopen(url, timeout=4, context=ctx).status==200 else 1)"

# --proxy-headers：前置 LB / Cloudflare Tunnel 时信任 X-Forwarded-Proto，
# Swagger UI 重定向会保留正确 scheme。
# TLS 开关在 docker_start.sh 内（TLS_CERT/TLS_KEY 环境变量）
CMD ["/usr/local/bin/docker_start.sh"]
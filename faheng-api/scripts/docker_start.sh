#!/bin/sh
# 容器入口：按 TLS_CERT / TLS_KEY 环境变量决定 HTTP 或 HTTPS 启动。
# - 未设置（默认/本地 dev）          → 纯 HTTP，行为与旧版完全一致
# - 设置了两个变量（挂载自签名证书）→ uvicorn 原生 TLS，同源 serve 前端 + API
#
# uvicorn 不做 http→https 自动跳转：切换后旧 http:// 书签会直接失效，
# 需改用 https://IP:58069 访问（README 有说明）。
set -e

if [ -n "${TLS_CERT:-}" ] && [ -n "${TLS_KEY:-}" ]; then
  if [ ! -r "$TLS_CERT" ] || [ ! -r "$TLS_KEY" ]; then
    echo "错误：TLS_CERT/TLS_KEY 已设置但文件不可读（检查挂载路径与权限，容器内 uid 1000 需可读）" >&2
    exit 1
  fi
  echo "HTTPS 模式启动：cert=$TLS_CERT"
  exec uvicorn app.main:app --host 0.0.0.0 --port 58069 \
    --proxy-headers --ssl-certfile "$TLS_CERT" --ssl-keyfile "$TLS_KEY"
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 58069 --proxy-headers
fi

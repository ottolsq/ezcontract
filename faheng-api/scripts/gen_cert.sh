#!/bin/bash
# 容器内自签证书生成器：不依赖宿主机 openssl，直接用镜像自带工具生成
# 自签名 TLS 证书（SAN 写入公网 IP），落到挂载卷持久化。
#
# 背景：服务器按 faheng.tar.gz 离线交付，宿主机未必装有 openssl；
# python:3.11-slim 基础镜像自带 openssl 3.x 和 bash，故借容器自身生成。
#
# 用法（宿主机执行，IP 换成实际公网 IP）：
#   sudo docker run --rm -v $(pwd)/tls:/tls -u 0 faheng:latest \
#       /bin/bash /app/scripts/gen_cert.sh <公网IP>
#
# 必须加 -u 0（root）原因：挂载目录若由 Docker 自动创建则属主 root，
# 容器默认用户 faheng(1000) 无写权限。root 生成后脚本自行 chown 1000:1000，
# 保证正式容器（faheng, uid 1000）只读挂载时可读——宿主机无需任何手工 chown。
#
# 幂等：每次运行直接覆盖 /tls 下旧证书（IP 变更 / 到期续期场景）。
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "用法：gen_cert.sh <公网IP或域名>" >&2
  exit 1
fi

NAME="$1"
OUT_DIR=/tls

# SAN 类型：IPv4 / IPv6（含冒号）→ IP:，其余按域名 → DNS:
# 现代浏览器只校验 SAN，不校验 CN（CN 仅作兼容保留）
if [[ "$NAME" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ || "$NAME" == *:* ]]; then
  SAN="IP:${NAME}"
else
  SAN="DNS:${NAME}"
fi

mkdir -p "$OUT_DIR"

# 有效期 395 天：Chrome 根证书计划要求叶子证书 <= 398 天，
# 超期可能触发不可绕过的 ERR_CERT_VALIDITY_TOO_LONG；到期重跑本脚本即可。
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 395 \
  -keyout "$OUT_DIR/cert.key" -out "$OUT_DIR/cert.pem" \
  -subj "/CN=${NAME}" \
  -addext "subjectAltName=${SAN}" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"

# root 运行时把属主交给容器运行用户（faheng, uid 1000），运行容器才能读
if [[ "$(id -u)" == "0" ]]; then
  chown 1000:1000 "$OUT_DIR/cert.key" "$OUT_DIR/cert.pem"
fi
chmod 600 "$OUT_DIR/cert.key"
chmod 644 "$OUT_DIR/cert.pem"

echo
echo "证书已生成：挂载目录 tls/ 下 cert.pem（证书）+ cert.key（私钥）"
openssl x509 -in "$OUT_DIR/cert.pem" -noout -subject -dates -ext subjectAltName

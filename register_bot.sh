#!/bin/bash
# CTF Context.ai 自动注册 + API Key 获取脚本
set -e

# 代理池
PROXIES=(
    "socks5://US:5shvtLVM3C3T@proxy.dzxlol.com:2261"
    "socks5://JP:iZ8R7k32VAD6@proxy.dzxlol.com:2261"
    "socks5://SG:pQrvTx9mfy3Z@proxy.dzxlol.com:2261"
    "socks5://KR:51NLF55oX9q2@proxy.dzxlol.com:2261"
    "socks5://GB:VWfq3yYXo3dM@proxy.dzxlol.com:2261"
    "socks5://CA:22APlXeSJr9J@proxy.dzxlol.com:2261"
    "socks5://DE:hVCuH2z6K5M6@proxy.dzxlol.com:2261"
    "socks5://US:mWHjMXBf8Alj@proxy.dzxlol.com:2264"
    "socks5://US:3PY5cUXdnBn5@proxy.dzxlol.com:2262"
    "socks5://US:xXj24WuuRbVz@proxy.dzxlol.com:2265"
)

EMAIL_DOMAIN="114514heihei.eu.org"
EMAIL_ADMIN_PASS="mapiwbh@pass"
TARGET="https://workspace.context.ai"
PASSWORD="CtfB0t2026!Secure"
proxy_idx=0

next_proxy() {
    local p="${PROXIES[$proxy_idx]}"
    proxy_idx=$(( (proxy_idx + 1) % ${#PROXIES[@]} ))
    echo "$p"
}

# ---- Step 1: 创建临时邮箱 ----
echo "[步骤 1] 创建临时邮箱..."
EMAIL_NAME="ctf$(date +%s%N | tail -c 7)"
RESP=$(curl -s --max-time 10 "https://e.114514heihei.eu.org/admin/new_address" \
    -X POST -H "Content-Type: application/json" \
    -H "x-admin-auth: ${EMAIL_ADMIN_PASS}" \
    -d "{\"name\":\"${EMAIL_NAME}\",\"domain\":\"${EMAIL_DOMAIN}\"}")

EMAIL=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['address'])")
EMAIL_JWT=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['jwt'])")
echo "[+] 邮箱: $EMAIL"

# ---- Step 2: 注册 ----
echo "[步骤 2] 注册账号..."
REGISTERED=0
for i in $(seq 1 20); do
    PROXY=$(next_proxy)
    echo "[*] 尝试 #$i 代理: $PROXY"

    REG_RESP=$(curl -s --max-time 20 --proxy "$PROXY" \
        -X POST "${TARGET}/api/auth/sign-up/email" \
        -H "Content-Type: application/json" \
        -H "Origin: ${TARGET}" \
        -H "Referer: ${TARGET}/" \
        -d "{\"name\":\"CTFBot\",\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}" 2>/dev/null)

    if echo "$REG_RESP" | grep -q '"id"'; then
        echo "[+] 注册成功! $REG_RESP"
        REGISTERED=1
        break
    elif echo "$REG_RESP" | grep -q "Too many"; then
        echo "[-] 限流，切换代理..."
        sleep 1
    else
        echo "[-] 失败: ${REG_RESP:0:100}"
        sleep 1
    fi
done

if [ $REGISTERED -eq 0 ]; then
    echo "[-] 注册失败，退出"
    exit 1
fi

# ---- Step 3: 获取验证码 ----
echo "[步骤 3] 等待验证码..."
CODE=""
for i in $(seq 1 40); do
    sleep 3
    MAILS=$(curl -s --max-time 10 \
        "https://e.114514heihei.eu.org/admin/mails?limit=5&offset=0&address=${EMAIL}" \
        -H "x-admin-auth: ${EMAIL_ADMIN_PASS}" 2>/dev/null)

    CODE=$(echo "$MAILS" | python3 -c "
import sys,json,re
try:
    data = json.loads(sys.stdin.read(), strict=False)
    if data.get('count',0) > 0:
        raw = data['results'][0]['raw']
        m = re.findall(r'Your verification code: (\d{6})', raw)
        print(m[0] if m else '')
    else: print('')
except: print('')
" 2>/dev/null)

    if [ -n "$CODE" ]; then
        echo "[+] 验证码: $CODE"
        break
    fi
    echo "[*] 等待中 ($i/40)..."
done

if [ -z "$CODE" ]; then
    echo "[-] 获取验证码超时"; exit 1
fi

# ---- Step 4: 验证邮箱 ----
echo "[步骤 4] 验证邮箱..."
VERIFIED=0
for i in $(seq 1 10); do
    PROXY=$(next_proxy)
    echo "[*] 验证尝试 #$i 代理: $PROXY"

    VERIFY_RESP=$(curl -s --max-time 20 --proxy "$PROXY" \
        -X POST "${TARGET}/api/auth/email-otp/verify-email" \
        -H "Content-Type: application/json" \
        -H "Origin: ${TARGET}" \
        -H "Referer: ${TARGET}/" \
        -d "{\"email\":\"${EMAIL}\",\"otp\":\"${CODE}\"}" 2>/dev/null)

    if echo "$VERIFY_RESP" | grep -q '"emailVerified":true'; then
        echo "[+] 验证成功!"
        VERIFIED=1
        break
    elif echo "$VERIFY_RESP" | grep -q "Too many"; then
        echo "[-] 限流，切换代理..."
        sleep 2
    else
        echo "[-] 失败: ${VERIFY_RESP:0:100}"
        sleep 2
    fi
done

# ---- Step 5: 登录 ----
echo "[步骤 5] 登录..."
TOKEN=""
for i in $(seq 1 15); do
    PROXY=$(next_proxy)
    sleep 3
    echo "[*] 登录尝试 #$i 代理: $PROXY"

    LOGIN_RESP=$(curl -s --max-time 20 --proxy "$PROXY" \
        -X POST "${TARGET}/api/auth/sign-in/email" \
        -H "Content-Type: application/json" \
        -H "Origin: ${TARGET}" \
        -H "Referer: ${TARGET}/" \
        -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}" 2>/dev/null)

    if echo "$LOGIN_RESP" | grep -q '"token"'; then
        TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
        echo "[+] 登录成功! Token: ${TOKEN:0:60}..."
        break
    elif echo "$LOGIN_RESP" | grep -q "Too many"; then
        echo "[-] 限流，切换代理..."
    elif echo "$LOGIN_RESP" | grep -q "not verified"; then
        echo "[-] 邮箱未验证，重试..."
    else
        echo "[-] 失败: ${LOGIN_RESP:0:100}"
    fi
done

# ---- Step 6: 获取 API Key ----
echo "[步骤 6] 查找 API Key..."
PROXY=$(next_proxy)

# 探索多个端点
for ep in \
    "GET /api/auth/session" \
    "GET /api/user" \
    "GET /api/settings" \
    "GET /api/workspace" \
    "GET /api/workspaces" \
    "GET /api/workspace/api-keys" \
    "GET /api/api-keys" \
    "GET /api/user/api-keys" \
    "GET /api/workspace/api_key" \
    "POST /api/workspace/api-key" \
    "POST /api/auth/api-key/create" \
    "POST /api/rpc" \
; do
    METHOD=$(echo "$ep" | cut -d' ' -f1)
    PATH_EP=$(echo "$ep" | cut -d' ' -f2)

    if [ "$METHOD" = "POST" ]; then
        RESP=$(curl -s --max-time 15 --proxy "$PROXY" \
            -X POST "${TARGET}${PATH_EP}" \
            -H "Content-Type: application/json" \
            -H "Origin: ${TARGET}" \
            -H "Referer: ${TARGET}/" \
            -H "Authorization: Bearer ${TOKEN}" \
            -d '{}' 2>/dev/null)
    else
        RESP=$(curl -s --max-time 15 --proxy "$PROXY" \
            "${TARGET}${PATH_EP}" \
            -H "Origin: ${TARGET}" \
            -H "Referer: ${TARGET}/" \
            -H "Authorization: Bearer ${TOKEN}" 2>/dev/null)
    fi

    if [ -n "$RESP" ] && ! echo "$RESP" | grep -qE '"error"|"not_found"'; then
        echo "[+] $METHOD $PATH_EP => ${RESP:0:300}"
    fi
done

# ---- 总结 ----
echo ""
echo "==========================================="
echo "  账号信息"
echo "  邮箱: $EMAIL"
echo "  密码: $PASSWORD"
echo "  Token: ${TOKEN:-N/A}"
echo "  邮箱JWT: $EMAIL_JWT"
echo "==========================================="

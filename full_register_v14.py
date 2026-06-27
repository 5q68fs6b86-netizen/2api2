#!/usr/bin/env python3
"""
完整注册机 v14 - 纯 API/RPC 驱动，零 Playwright 依赖

合并 full_register_v2.py（API 注册流程 + 代理轮换）和
create_inference_api_key.py（RPC 创建 API key + 推理测试）的最佳部分。

流程：创建邮箱 → 注册 → 验证码 → 验证邮箱 → 登录 → onboarding → 获取 agentId
      → 创建 API key → 测试推理 API → 保存结果
"""
import json
import re
import subprocess
import sys
import time
from http.cookies import SimpleCookie
from email.message import Message
from pathlib import Path
from urllib import error, request

# ============================================================
# 配置常量
# ============================================================
TARGET = "https://workspace.context.ai"
EMAIL_DOMAIN = "114514heihei.eu.org"
EMAIL_ADMIN_PASS = "mapiwbh@pass"
EMAIL_API = "https://e.114514heihei.eu.org"
PASSWORD = "CtfBot2026!Secure"
DEFAULT_MODEL = "context-gateway/zai/glm-5.2"

PROXIES = [
    "socks5://JP:iZ8R7k32VAD6@proxy.dzxlol.com:2261",
    "socks5://SG:pQrvTx9mfy3Z@proxy.dzxlol.com:2261",
    "socks5://KR:51NLF55oX9q2@proxy.dzxlol.com:2261",
    "socks5://US:5shvtLVM3C3T@proxy.dzxlol.com:2261",
    "socks5://GB:VWfq3yYXo3dM@proxy.dzxlol.com:2261",
]

OUTPUT_PATH = Path(__file__).resolve().with_name("ctx_account.json")

# ============================================================
# 代理轮换
# ============================================================
_proxy_idx = 0


def next_proxy():
    """轮换获取下一个代理"""
    global _proxy_idx
    p = PROXIES[_proxy_idx % len(PROXIES)]
    _proxy_idx += 1
    return p


# ============================================================
# HTTP 工具 (urllib + 代理支持)
# ============================================================


class HttpResponse:
    """HTTP 响应封装"""

    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body)


def http_request(method, url, headers=None, payload=None, timeout=30, proxy=None):
    """
    通用 HTTP 请求，支持 socks5 代理。

    对于 socks5 代理，urllib 需要 PySocks（pip install PySocks）。
    如果系统没有 PySocks，则用 curl 子进程兜底。
    """
    if proxy and proxy.startswith("socks5"):
        # socks5 代理走 curl 子进程（更可靠）
        return _curl_request(method, url, headers, payload, timeout, proxy)

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = dict(headers or {})
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")

    proxy_handler = None
    if proxy and not proxy.startswith("socks5"):
        proxy_handler = request.ProxyHandler({"http": proxy, "https": proxy})
        opener = request.build_opener(proxy_handler)
    else:
        opener = request.build_opener()

    req = request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return HttpResponse(
                resp.status, resp.headers, resp.read().decode("utf-8", "replace")
            )
    except error.HTTPError as exc:
        return HttpResponse(
            exc.code, exc.headers, exc.read().decode("utf-8", "replace")
        )
    except Exception as exc:
        return HttpResponse(0, Message(), str(exc))


def _curl_request(method, url, headers=None, payload=None, timeout=30, proxy=None):
    """用 curl 子进程执行 HTTP 请求（用于 socks5 代理）"""
    status_marker = "\n__CURL_HTTP_STATUS__:"
    cmd = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout),
        "-X",
        method,
        url,
        "-D",
        "-",
        "-w",
        f"{status_marker}%{{http_code}}",
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    req_headers = dict(headers or {})
    if payload is not None:
        req_headers.setdefault("Content-Type", "application/json")
    if req_headers:
        for k, v in req_headers.items():
            cmd += ["-H", f"{k}: {v}"]
    if payload is not None:
        cmd += ["-d", json.dumps(payload)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return HttpResponse(0, Message(), result.stderr.strip() or result.stdout)

    raw = result.stdout
    status = 0
    if status_marker in raw:
        raw, status_text = raw.rsplit(status_marker, 1)
        status_match = re.search(r"\d{3}", status_text)
        status = int(status_match.group(0)) if status_match else 0

    resp_headers, body = _parse_curl_response(raw)
    return HttpResponse(status, resp_headers, body)


def _parse_curl_response(raw):
    """解析 curl -D - 输出，保留最后一个 HTTP 响应头块。"""
    pos = 0
    last_header_block = ""
    while raw.startswith("HTTP/", pos):
        crlf_end = raw.find("\r\n\r\n", pos)
        lf_end = raw.find("\n\n", pos)
        candidates = [idx for idx in (crlf_end, lf_end) if idx != -1]
        if not candidates:
            break
        end = min(candidates)
        separator_len = 4 if end == crlf_end else 2
        last_header_block = raw[pos:end]
        pos = end + separator_len

    headers = Message()
    for line in last_header_block.replace("\r\n", "\n").split("\n")[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers.add_header(name.strip(), value.strip())
    return headers, raw[pos:]


def extract_session_cookie(headers):
    """从 Set-Cookie 响应头中提取 session_token"""
    set_cookie_values = headers.get_all("Set-Cookie", []) if hasattr(headers, "get_all") else []
    for raw in set_cookie_values:
        cookie = SimpleCookie(raw)
        for name, morsel in cookie.items():
            if "session_token" in name:
                return morsel.value
    return None


# ============================================================
# 邮箱管理 (来自 full_register_v2.py)
# ============================================================


def curl_api(method, url, headers=None, data=None, proxy=None, timeout=20):
    """简化版 curl 调用，返回原始文本"""
    cmd = ["curl", "-sS", "--max-time", str(timeout), "-X", method, url]
    if proxy:
        cmd += ["--proxy", proxy]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout if result.stdout else result.stderr.strip()


def create_temp_email():
    """通过邮件 API 创建临时邮箱，返回 (address, jwt)"""
    name = f"bot{int(time.time())}{int(time.time() * 1000) % 1000}"
    resp = curl_api(
        "POST",
        f"{EMAIL_API}/admin/new_address",
        headers={
            "Content-Type": "application/json",
            "x-admin-auth": EMAIL_ADMIN_PASS,
        },
        data={"name": name, "domain": EMAIL_DOMAIN},
    )
    try:
        data = json.loads(resp)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"创建临时邮箱失败: {resp[:500] or '<empty response>'}") from exc
    if not data.get("address") or not data.get("jwt"):
        raise RuntimeError(f"创建临时邮箱响应缺少 address/jwt: {resp[:500]}")
    return data["address"], data["jwt"]


def get_verification_code(email, timeout=90):
    """
    轮询获取验证码。

    每 3 秒检查一次邮件 API，查找最新的验证码。
    返回验证码字符串，或 None（超时）。
    """
    for _ in range(timeout // 3):
        time.sleep(3)
        try:
            resp = curl_api(
                "GET",
                f"{EMAIL_API}/admin/mails?limit=5&offset=0&address={email}",
                headers={"x-admin-auth": EMAIL_ADMIN_PASS},
            )
            data = json.loads(resp, strict=False)
            if data.get("count", 0) > 0:
                raw = data["results"][0]["raw"]
                codes = re.findall(r"Your verification code: (\d{6})", raw)
                if codes:
                    return codes[0]
        except Exception:
            pass
    return None


# ============================================================
# 注册 + 验证 + 登录 (API 驱动，代理轮换)
# ============================================================


def register_user(email, password, max_attempts=20):
    """
    通过 API 注册账号，使用代理轮换应对限流。

    Raises RuntimeError on failure.
    """
    print("[*] 注册账号...")
    for i in range(max_attempts):
        proxy = next_proxy()
        proxy_label = proxy.split("@")[1] if "@" in proxy else proxy
        print(f"  尝试 #{i + 1} 代理: {proxy_label}")
        resp = curl_api(
            "POST",
            f"{TARGET}/api/auth/sign-up/email",
            headers={
                "Content-Type": "application/json",
                "Origin": TARGET,
                "Referer": f"{TARGET}/",
            },
            data={"name": "CTFBot", "email": email, "password": password},
            proxy=proxy,
        )
        if '"id"' in resp:
            print("[+] 注册成功!")
            return json.loads(resp)
        elif "Too many" in resp or "429" in resp:
            print("  限流(429)，切换代理...")
        elif "already" in resp.lower() or "exist" in resp.lower():
            print(f"  账号已存在: {resp[:100]}")
            return json.loads(resp) if resp.strip().startswith("{") else {"email": email}
        else:
            print(f"  失败: {resp[:100]}")
        time.sleep(1.5)
    raise RuntimeError(f"注册失败（{max_attempts} 次尝试均失败）")


def verify_email(email, otp, max_attempts=10):
    """
    通过 API 验证邮箱。

    Raises RuntimeError on failure.
    """
    print("[*] 验证邮箱...")
    for i in range(max_attempts):
        proxy = next_proxy()
        resp = curl_api(
            "POST",
            f"{TARGET}/api/auth/email-otp/verify-email",
            headers={
                "Content-Type": "application/json",
                "Origin": TARGET,
                "Referer": f"{TARGET}/",
            },
            data={"email": email, "otp": otp},
            proxy=proxy,
            timeout=25,
        )
        if "emailVerified" in resp or "true" in resp.lower():
            print("[+] 邮箱验证成功!")
            return True
        elif "Too many" in resp or "429" in resp:
            print("  限流(429)，切换代理...")
        else:
            print(f"  失败: {resp[:100]}")
        time.sleep(2)
    raise RuntimeError(f"邮箱验证失败（{max_attempts} 次尝试均失败）")


def login_and_get_cookie(email, password, max_attempts=15):
    """
    登录并提取 session cookie。

    返回 session_token 字符串。

    Raises RuntimeError on failure.
    """
    print("[*] 登录获取 session cookie...")
    for i in range(max_attempts):
        proxy = next_proxy()
        time.sleep(1.5)
        resp = http_request(
            "POST",
            f"{TARGET}/api/auth/sign-in/email",
            headers={
                "Content-Type": "application/json",
                "Origin": TARGET,
                "Referer": f"{TARGET}/",
            },
            payload={"email": email, "password": password},
            proxy=proxy,
            timeout=25,
        )
        # 用 urllib 直接请求以获取完整的 Set-Cookie header
        # curl 子进程拿不到 headers，所以登录用 http_request
        if resp.status < 400:
            cookie = extract_session_cookie(resp.headers)
            if cookie:
                print(f"[+] 登录成功! Cookie: {cookie[:60]}...")
                return cookie

        # 对于 curl 代理的场景，检查 body
        try:
            data = json.loads(resp.body) if resp.body else {}
            if data.get("token"):
                # 有 token 但没 cookie，用 get-session 端点
                print("[*] 有 token 但无 cookie，尝试 get-session...")
                session_resp = http_request(
                    "POST",
                    f"{TARGET}/api/auth/get-session",
                    headers={
                        "Content-Type": "application/json",
                        "Origin": TARGET,
                        "Referer": f"{TARGET}/",
                        "Authorization": f"Bearer {data['token']}",
                    },
                    proxy=proxy,
                    timeout=20,
                )
                cookie = extract_session_cookie(session_resp.headers)
                if cookie:
                    print(f"[+] 通过 get-session 获取 cookie 成功!")
                    return cookie
        except Exception:
            pass

        if resp.status == 429 or "Too many" in (resp.body or ""):
            print("  限流(429)，切换代理...")
        else:
            print(f"  失败: HTTP {resp.status} {resp.body[:80] if resp.body else ''}")
    raise RuntimeError(f"登录失败（{max_attempts} 次尝试均失败）")


# ============================================================
# RPC 调用 (来自 create_inference_api_key.py)
# ============================================================


def rpc_call(session_cookie, name, payload, timeout=30):
    """
    通用 RPC 调用。

    Args:
        session_cookie: session_token 值
        name: RPC 方法名（如 "onboarding/complete"、"apiKey/create"）
        payload: RPC 请求体中的数据部分（不含 json/meta 包装）

    Returns:
        HttpResponse
    """
    return http_request(
        "POST",
        f"{TARGET}/api/rpc/{name}",
        headers={
            "Content-Type": "application/json",
            "Origin": TARGET,
            "Referer": f"{TARGET}/client",
            "Cookie": f"__Secure-better-auth.session_token={session_cookie}",
        },
        payload={"json": payload, "meta": []},
        timeout=timeout,
    )


# ============================================================
# Onboarding → 获取 agentId
# ============================================================


def complete_onboarding(session_cookie, agent_name="CTFBot"):
    """
    完成 onboarding 并获取自动创建的 agent ID。

    onboarding/complete RPC 的响应中包含:
      - orgId
      - workspaceId
      - agentId  ← 这就是我们需要的!

    Returns:
        agentId 字符串

    Raises RuntimeError on failure.
    """
    print("[*] 完成 onboarding...")
    resp = rpc_call(session_cookie, "onboarding/complete", {"agentName": agent_name})
    if resp.status >= 400:
        raise RuntimeError(f"onboarding 失败: HTTP {resp.status} {resp.body[:500]}")

    data = resp.json()
    inner = data.get("json", data)
    agent_id = inner.get("agentId", "")
    org_id = inner.get("orgId", "")
    workspace_id = inner.get("workspaceId", "")

    if not agent_id:
        raise RuntimeError(f"onboarding 响应中未找到 agentId: {resp.body[:500]}")

    print(f"[+] Agent ID: {agent_id}")
    print(f"[+] Org ID: {org_id}")
    print(f"[+] Workspace ID: {workspace_id}")
    return agent_id


# ============================================================
# 创建 API Key (来自 create_inference_api_key.py)
# ============================================================


def create_api_key(session_cookie, agent_id, key_name):
    """
    通过 RPC 为指定 agent 创建推理 API key。

    Returns:
        dict: {"key": "sk-xxx", "info": {...}}

    Raises RuntimeError on failure.
    """
    print(f"[*] 创建 API key (name={key_name})...")
    resp = rpc_call(session_cookie, "apiKey/create", {"agentId": agent_id, "name": key_name})
    if resp.status >= 400:
        raise RuntimeError(f"apiKey/create 失败: HTTP {resp.status} {resp.body[:500]}")

    data = resp.json().get("json", {})
    api_key = data.get("key")
    if not api_key:
        raise RuntimeError(f"apiKey/create 未返回 key: {resp.body[:500]}")

    print(f"[+] API Key: {api_key}")
    return data


# ============================================================
# 推理 API 测试 (来自 create_inference_api_key.py)
# ============================================================


def test_inference(api_key, model=DEFAULT_MODEL, timeout=90):
    """
    用新创建的 API key 测试推理 API。

    Returns:
        HttpResponse
    """
    print(f"[*] 测试推理 API (model={model})...")
    payload = {
        "prompt": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Reply with exactly: CTF_INFERENCE_OK"}
                ],
            }
        ],
        "maxOutputTokens": 20,
        "temperature": 0,
    }
    resp = http_request(
        "POST",
        f"{TARGET}/api/inference/vercel/v1/ai/language-model",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "ai-gateway-protocol-version": "0.0.1",
            "ai-gateway-auth-method": "api-key",
            "ai-language-model-specification-version": "4",
            "ai-language-model-id": model,
            "ai-language-model-streaming": "false",
        },
        payload=payload,
        timeout=timeout,
    )
    print(f"[*] 推理 API 返回: HTTP {resp.status}")
    print(f"    {resp.body[:500]}")
    if resp.status == 402:
        try:
            err = resp.json().get("error", {})
        except json.JSONDecodeError:
            err = {}
        if err.get("type") == "quota_for_entity_exceeded":
            print(f"[-] 推理 API 额度不足: {err.get('message', '')[:300]}")
    return resp


# ============================================================
# 主流程
# ============================================================


def main():
    print("=" * 60)
    print("  完整注册机 v14 - API/RPC 驱动")
    print("=" * 60)

    # --- Phase 1: 创建临时邮箱 ---
    email, email_jwt = create_temp_email()
    print(f"\n[+] 临时邮箱: {email}")

    # --- Phase 2: 注册 ---
    print()
    register_user(email, PASSWORD)

    # --- Phase 3: 获取验证码 ---
    print("\n[*] 等待验证码...")
    code = get_verification_code(email)
    if not code:
        print("[-] 验证码获取超时")
        return 1
    print(f"[+] 验证码: {code}")

    # --- Phase 4: 验证邮箱 ---
    print()
    verify_email(email, code)

    # --- Phase 5: 登录获取 session cookie ---
    print()
    session_cookie = login_and_get_cookie(email, PASSWORD)

    # --- Phase 6: 完成 onboarding → 获取 agentId ---
    print()
    agent_id = complete_onboarding(session_cookie, "CTFBot")

    # --- Phase 7: 创建 API key ---
    print()
    key_name = f"ctf-reg-{int(time.time())}"
    api_key_data = create_api_key(session_cookie, agent_id, key_name)

    # --- Phase 8: 测试推理 API ---
    print()
    inference_resp = test_inference(api_key_data["key"], DEFAULT_MODEL)

    # --- Phase 9: 保存结果 ---
    output = {
        "email": email,
        "password": PASSWORD,
        "agent_id": agent_id,
        "session_cookie": session_cookie,
        "api_key": api_key_data["key"],
        "api_key_name": key_name,
        "api_key_info": api_key_data.get("info"),
        "inference_endpoint": f"{TARGET}/api/inference/vercel/v1/ai/language-model",
        "inference_model": DEFAULT_MODEL,
        "inference_status": inference_resp.status,
        "inference_response": inference_resp.body[:4000],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("  注册完成!")
    print("=" * 60)
    print(f"  邮箱:     {email}")
    print(f"  密码:     {PASSWORD}")
    print(f"  Agent ID: {agent_id}")
    print(f"  API Key:  {api_key_data['key']}")
    print(f"  推理测试: HTTP {inference_resp.status}")
    print(f"  结果文件: {OUTPUT_PATH}")
    print("=" * 60)

    return 0 if inference_resp.status < 400 else 2


if __name__ == "__main__":
    sys.exit(main())

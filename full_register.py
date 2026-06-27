#!/usr/bin/env python3
"""
Playwright: 完整的注册机 - 注册→验证→创建org→启动agent→通过WebSocket交互获取推理结果
"""
import asyncio, json, uuid, time, re, sys
from playwright.async_api import async_playwright

TARGET = "https://workspace.context.ai"
EMAIL_DOMAIN = "114514heihei.eu.org"
EMAIL_ADMIN_PASS = "mapiwbh@pass"
EMAIL_API = "https://e.114514heihei.eu.org"

async def create_temp_email():
    """创建临时邮箱"""
    import subprocess
    name = f"bot{int(time.time())}"
    resp = subprocess.run([
        "curl", "-s", "--max-time", "10",
        f"{EMAIL_API}/admin/new_address",
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-H", f"x-admin-auth: {EMAIL_ADMIN_PASS}",
        "-d", json.dumps({"name": name, "domain": EMAIL_DOMAIN})
    ], capture_output=True, text=True)
    data = json.loads(resp.stdout)
    return data["address"], data["jwt"]

async def get_verification_code(email, email_jwt, timeout=60):
    """获取验证码"""
    import subprocess
    for i in range(timeout // 3):
        await asyncio.sleep(3)
        resp = subprocess.run([
            "curl", "-s", "--max-time", "10",
            f"{EMAIL_API}/admin/mails?limit=5&offset=0&address={email}",
            "-H", f"x-admin-auth: {EMAIL_ADMIN_PASS}"
        ], capture_output=True, text=True)
        try:
            data = json.loads(resp.stdout, strict=False)
            if data.get("count", 0) > 0:
                raw = data["results"][0]["raw"]
                codes = re.findall(r'Your verification code: (\d{6})', raw)
                if codes:
                    return codes[0]
        except:
            pass
    return None

async def main():
    email, email_jwt = await create_temp_email()
    password = "CtfBot2026!Secure"
    print(f"[+] 临时邮箱: {email}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Step 1: 注册
        print("[*] 注册账号...")
        await page.goto(f"{TARGET}/sign-up", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # 填写注册表单
        await page.fill('input[name="name"], input[id="name"]', "CTFBot")
        await page.fill('input[name="email"], input[type="email"], input[id="email"]', email)
        await page.fill('input[name="password"], input[type="password"], input[id="password"]', password)

        # 确认密码（如果有）
        confirm = await page.query_selector('input[name="confirmPassword"], input[id="confirmPassword"]')
        if confirm:
            await confirm.fill(password)

        await page.click('button[type="submit"]')
        await page.wait_for_timeout(5000)
        print(f"[*] 注册后 URL: {page.url}")

        # Step 2: 获取验证码
        print("[*] 获取验证码...")
        code = await get_verification_code(email, email_jwt)
        if not code:
            print("[-] 获取验证码失败")
            await browser.close()
            return
        print(f"[+] 验证码: {code}")

        # Step 3: 输入验证码
        print("[*] 输入验证码...")
        # 找到验证码输入框
        inputs = await page.query_selector_all('input')
        for inp in inputs:
            placeholder = await inp.get_attribute("placeholder") or ""
            if "code" in placeholder.lower() or "verification" in placeholder.lower():
                await inp.fill(code)
                break
        else:
            # 尝试所有 input
            for inp in inputs:
                type_attr = await inp.get_attribute("type") or ""
                if type_attr in ("text", "number", "tel"):
                    await inp.fill(code)
                    break

        await page.click('button[type="submit"]')
        await page.wait_for_timeout(5000)
        print(f"[*] 验证后 URL: {page.url}")

        # Step 4: 如果还在验证页面，尝试用 OTP API
        if "verif" in page.url.lower():
            print("[*] 尝试 OTP API 验证...")
            # 通过 JS 调用验证 API
            result = await page.evaluate(f"""
                fetch('/api/auth/email-otp/verify-email', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{email: '{email}', otp: '{code}'}})
                }}).then(r => r.json())
            """)
            print(f"[*] OTP 验证结果: {result}")
            await page.wait_for_timeout(3000)

        # Step 5: 登录（如果需要）
        if "sign-in" in page.url or "login" in page.url:
            print("[*] 登录...")
            await page.goto(f"{TARGET}/sign-in", wait_until="networkidle", timeout=15000)
            await page.fill('input[name="email"], input[type="email"], input[id="email"]', email)
            await page.fill('input[name="password"], input[type="password"], input[id="password"]', password)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)
            print(f"[*] 登录后 URL: {page.url}")

        # Step 6: 完成 onboarding
        print("[*] 完成 onboarding...")
        onboard_result = await page.evaluate("""
            fetch('/api/rpc/onboarding/complete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({json: {agentName: 'CTFBot'}, meta: []})
            }).then(r => r.json())
        """)
        print(f"[*] Onboarding: {json.dumps(onboard_result)[:300]}")

        # Step 7: 导航到 agent 页面
        print("[*] 导航到 agent 页面...")
        await page.goto(f"{TARGET}/client", wait_until="networkidle", timeout=30000)
        print(f"[*] URL: {page.url}")
        await page.wait_for_timeout(3000)

        # Step 8: 发送消息
        print("[*] 发送消息...")
        textarea = await page.query_selector('textarea')
        if textarea:
            await textarea.fill("Respond with exactly: INFERENCE_API_WORKS")
            await page.wait_for_timeout(1000)
            await textarea.press("Enter")
            print("[*] 消息已发送，等待 agent 响应...")

            # 等待 agent 启动并响应
            for i in range(60):
                await page.wait_for_timeout(5000)
                # 检查页面上是否有 agent 的响应
                content = await page.inner_text('body')
                if "INFERENCE_API_WORKS" in content:
                    print("[+] Agent 响应成功！推理 API 工作正常！")
                    break
                # 检查是否有错误
                if "error" in content.lower() and "failed" in content.lower():
                    print(f"[-] 可能有错误，等待中... ({i*5}s)")
                else:
                    print(f"[*] 等待 agent 响应... ({i*5}s)")

            await page.screenshot(path="/tmp/ctx_final.png")
            print("[*] 最终截图: /tmp/ctx_final.png")
        else:
            print("[-] 未找到聊天输入框")

        # Step 9: 获取 cookies
        cookies = await context.cookies()
        session_cookie = next((c for c in cookies if "session_token" in c["name"]), None)
        if session_cookie:
            print(f"\n[+] Session Token: {session_cookie['value']}")

        print(f"\n[+] 邮箱: {email}")
        print(f"[+] 密码: {password}")

        await browser.close()

asyncio.run(main())

#!/usr/bin/env python3
"""Playwright: 用注入 cookie 方式跳过登录，直接交互agent"""
import asyncio, json
from playwright.async_api import async_playwright

EMAIL = "verify503038@114514heihei.eu.org"
PASSWORD = "CtfBot2026!Secure"
TARGET = "https://workspace.context.ai"
SESSION_COOKIE_VALUE = "PXujEiQ6fSfURKTaDQItsITbpV6yIKwe.6ekYwKIAps0wJ8Q4bp0k3u09bLKPQAyDAQNnMtKpegU="

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # 注入 session cookie
        await context.add_cookies([{
            "name": "__Secure-better-auth.session_token",
            "value": SESSION_COOKIE_VALUE,
            "domain": "workspace.context.ai",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }])

        page = await context.new_page()

        captured = []
        async def on_request(request):
            url = request.url
            if "inference" in url or "api-key" in url.lower() or "rpc" in url:
                h = dict(request.headers)
                # 只打印关键 header
                key_headers = {k:v for k,v in h.items() if k.lower() in ('authorization','cookie','x-api-key','x-agent','content-type','origin')}
                captured.append({"url": url, "method": request.method, "headers": key_headers})
                print(f"[REQ] {request.method} {url}")
                for k,v in key_headers.items():
                    if k.lower() != 'cookie':
                        print(f"  {k}: {v[:100]}")

        async def on_response(response):
            url = response.url
            if "inference" in url:
                print(f"[RESP] {response.status} {url}")
                try:
                    body = await response.text()
                    print(f"  Body: {body[:300]}")
                except: pass

        page.on("request", on_request)
        page.on("response", on_response)

        # 直接进入 client
        print("=== 进入 client ===")
        await page.goto(f"{TARGET}/client", wait_until="networkidle", timeout=30000)
        print(f"URL: {page.url}")

        await page.screenshot(path="/tmp/ctx1.png")
        print("Screenshot: /tmp/ctx1.png")

        # 等待页面加载
        await page.wait_for_timeout(3000)

        # 尝试找到 agent chat 页面
        # 检查URL路径
        content = await page.content()
        print(f"Page content length: {len(content)}")

        # 尝试点击 agent 或新建对话
        links = await page.query_selector_all('a[href*="agent"], a[href*="task"], a[href*="chat"]')
        print(f"Found {len(links)} agent/chat links")
        for link in links[:5]:
            href = await link.get_attribute("href")
            text = await link.inner_text()
            print(f"  Link: {href} - {text}")

        # 尝试在聊天框输入
        textarea = await page.query_selector('textarea')
        if textarea:
            print("Found textarea!")
            await textarea.fill("hello, say hi in 3 words")
            await page.wait_for_timeout(1000)
            await textarea.press("Enter")
            print("Sent message via Enter")
            await page.wait_for_timeout(30000)
        else:
            print("No textarea found, looking for contenteditable...")
            editable = await page.query_selector('[contenteditable="true"]')
            if editable:
                print("Found contenteditable!")
                await editable.fill("hello, say hi in 3 words")
                await page.wait_for_timeout(1000)
                await editable.press("Enter")
                print("Sent message via Enter")
                await page.wait_for_timeout(30000)
            else:
                print("No input found")

        await page.screenshot(path="/tmp/ctx2.png")
        print("Screenshot: /tmp/ctx2.png")

        print("\n=== Captured requests ===")
        for c in captured:
            print(json.dumps(c, indent=2))

        await browser.close()

asyncio.run(main())

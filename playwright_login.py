#!/usr/bin/env python3
"""
Playwright script to:
1. Login to workspace.context.ai
2. Navigate to agent/settings pages
3. Intercept inference API calls to capture auth headers
"""
import asyncio
import json
from playwright.async_api import async_playwright

EMAIL = "verify503038@114514heihei.eu.org"
PASSWORD = "CtfBot2026!Secure"
TARGET = "https://workspace.context.ai"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        captured_inference_calls = []

        # Intercept all network requests
        async def handle_request(request):
            url = request.url
            if "inference" in url or "api-key" in url or "apiKey" in url:
                headers = request.headers
                print(f"[REQUEST] {request.method} {url}")
                print(f"  Headers: {json.dumps(dict(headers), indent=2)}")
                captured_inference_calls.append({
                    "url": url,
                    "method": request.method,
                    "headers": dict(headers),
                })

        async def handle_response(response):
            url = response.url
            if "inference" in url or "api-key" in url:
                print(f"[RESPONSE] {response.status} {url}")
                try:
                    body = await response.text()
                    print(f"  Body: {body[:500]}")
                except:
                    pass

        page.on("request", handle_request)
        page.on("response", handle_response)

        # Step 1: Navigate to the site
        print("=== Step 1: Navigating to site ===")
        await page.goto(TARGET, wait_until="networkidle", timeout=30000)
        print(f"Page title: {await page.title()}")
        print(f"URL: {page.url}")

        # Step 2: Login
        print("\n=== Step 2: Login ===")
        # Check if we need to login
        if "/sign-in" in page.url or "login" in page.url:
            print("On login page, filling credentials...")
            await page.fill('input[name="email"], input[type="email"]', EMAIL)
            await page.fill('input[name="password"], input[type="password"]', PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_url("**/client/**", timeout=15000)
            print(f"Logged in! URL: {page.url}")
        else:
            # Try to navigate to sign-in
            await page.goto(f"{TARGET}/sign-in", wait_until="networkidle", timeout=15000)
            print(f"Sign-in page URL: {page.url}")
            if "sign-in" in page.url:
                await page.fill('input[name="email"], input[type="email"]', EMAIL)
                await page.fill('input[name="password"], input[type="password"]', PASSWORD)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(5000)
                print(f"After login URL: {page.url}")

        # Step 3: Navigate to agent chat
        print("\n=== Step 3: Navigate to agent ===")
        await page.goto(f"{TARGET}/client", wait_until="networkidle", timeout=15000)
        print(f"Client URL: {page.url}")

        # Step 4: Try to send a message
        print("\n=== Step 4: Try to send message ===")
        # Look for chat input
        textarea = await page.query_selector('textarea, [contenteditable="true"], input[type="text"]')
        if textarea:
            await textarea.fill("hello, please respond with just 'hi'")
            # Find and click send button
            send_btn = await page.query_selector('button[type="submit"], button[aria-label*="send"], button[aria-label*="Send"]')
            if send_btn:
                await send_btn.click()
                print("Message sent! Waiting for response...")
                await page.wait_for_timeout(30000)
            else:
                # Try pressing Enter
                await textarea.press("Enter")
                print("Pressed Enter to send...")
                await page.wait_for_timeout(30000)
        else:
            print("No chat input found")

        # Step 5: Check captured inference calls
        print("\n=== Step 5: Captured inference calls ===")
        for call in captured_inference_calls:
            print(json.dumps(call, indent=2))

        # Step 6: Try to navigate to settings
        print("\n=== Step 6: Settings ===")
        await page.goto(f"{TARGET}/client/settings", wait_until="networkidle", timeout=15000)
        print(f"Settings URL: {page.url}")
        content = await page.content()
        print(f"Page content length: {len(content)}")

        # Take screenshot
        await page.screenshot(path="/tmp/context_screenshot.png")
        print("Screenshot saved to /tmp/context_screenshot.png")

        await browser.close()

asyncio.run(main())

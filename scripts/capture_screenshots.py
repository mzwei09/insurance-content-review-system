#!/usr/bin/env python3
"""
前端页面截图脚本

使用 Playwright 自动截取 README 所需的 6 张页面截图。
需先安装: pip install playwright && playwright install chromium

用法:
    # 确保服务已启动 (bash start.sh)
    python scripts/capture_screenshots.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


async def capture_screenshots():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("请先安装 Playwright:")
        print("  pip install playwright")
        print("  playwright install chromium")
        sys.exit(1)

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # 1. 登录页
            await page.goto(BASE_URL, wait_until="networkidle")
            await page.evaluate("() => { localStorage.clear(); location.reload(); }")
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path=SCREENSHOTS_DIR / "01-login.png")
            print("✓ 01-login.png")

            # 2. 注册页
            await page.click('a[data-page="register"]')
            await page.wait_for_selector("#page-register.active", timeout=3000)
            await page.screenshot(path=SCREENSHOTS_DIR / "02-register.png")
            print("✓ 02-register.png")

            # 3. 注册并登录（用于后续截图）
            username = f"screenshot_{int(time.time())}"
            await page.click('a[data-page="register"]')
            await page.wait_for_selector("#page-register.active", timeout=3000)
            await page.fill("#register-username", username)
            await page.fill("#register-password", "screenshot123")
            await page.click('#register-form button[type="submit"]')
            await page.wait_for_selector("#page-review", state="visible", timeout=5000)

            # 4. 审核页 - 空状态
            await page.screenshot(path=SCREENSHOTS_DIR / "03-review-empty.png")
            print("✓ 03-review-empty.png")

            # 5. 审核页 - 文本审核（需要 API 密钥，可能失败）
            await page.fill("#review-input", "年化收益高达15%，稳赚不赔！")
            await page.click("#review-btn")
            try:
                await page.wait_for_selector("#review-result-content:not(.hidden)", timeout=30000)
                await page.screenshot(path=SCREENSHOTS_DIR / "04-review-text.png")
                print("✓ 04-review-text.png")
            except Exception as e:
                print("⚠ 04-review-text.png 跳过（需配置 API 密钥）:", e)

            # 6. 个人中心
            await page.click('a:has-text("个人中心")')
            await page.wait_for_selector("#page-profile.active", timeout=3000)
            await page.screenshot(path=SCREENSHOTS_DIR / "06-profile.png")
            print("✓ 06-profile.png")

            # 7. 图片审核（需要 API 密钥和图片，可能失败）
            await page.click('a[data-page="review"]')  # 返回审核页
            await page.wait_for_selector("#page-review", state="visible", timeout=3000)
            # 上传 test_images 中的图片
            test_img = ROOT / "test_images" / "1_违规_夸大收益.png"
            if test_img.exists():
                await page.set_input_files("#image-input", str(test_img))
                await page.wait_for_timeout(1000)
                await page.click("#review-btn")
                try:
                    await page.wait_for_selector("#review-details-section:not(.hidden)", timeout=60000)
                    await page.screenshot(path=SCREENSHOTS_DIR / "05-review-images.png")
                    print("✓ 05-review-images.png")
                except Exception as e:
                    print("⚠ 05-review-images.png 跳过:", e)
            else:
                print("⚠ 05-review-images.png 跳过（test_images/ 不存在）")

        finally:
            await browser.close()

    print("\n截图已保存至:", SCREENSHOTS_DIR)


if __name__ == "__main__":
    asyncio.run(capture_screenshots())

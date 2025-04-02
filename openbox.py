import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import os
from datetime import datetime
from urllib.parse import urlparse

# 配置文件路径和URL常量
USER_FILE = 'user.txt'
LOGIN_URL = 'https://game.everdawn.io/enter/'
POST_LOGIN_URL = 'https://game.everdawn.io/me/inventory/'
STORE_OPEN_URL = 'https://game.everdawn.io/store/packs/open'

async def get_parent_href(page, element):
    """获取元素最近的包含href的父级链接"""
    return await page.evaluate('''(element) => {
        const anchor = element.closest('a[href]');
        return anchor ? anchor.href : null;
    }''', element)

async def handle_open_buttons(page, username, max_open_count=10):
    """改进版Open按钮处理（预判跳转链接）"""
    processed_count = 0
    max_retries = 2  # 最大重试次数
    
    while max_retries > 0 and processed_count < max_open_count:
        # 确保页面状态
        if not page.url.startswith(POST_LOGIN_URL):
            await page.goto(POST_LOGIN_URL, timeout=8000)
            await page.wait_for_load_state("networkidle")

        # 获取所有候选按钮
        raw_buttons = await page.query_selector_all(
            'button:has-text("Open"), [class*="open-button"], .open-action-element'
        )
        print(f"[{username}] 发现 {len(raw_buttons)} 个候选按钮")

        valid_buttons = []
        for btn in raw_buttons:
            # 预检测跳转链接
            try:
                parent_href = await get_parent_href(page, btn)
                if parent_href and urlparse(parent_href).path == urlparse(STORE_OPEN_URL).path:
                    print(f"[{username}] 跳过预检测到商店链接的按钮")
                    continue
                
                if await btn.is_visible():
                    valid_buttons.append(btn)
            except Exception as e:
                print(f"[{username}] 按钮预检测失败: {str(e)}")

        if not valid_buttons:
            print(f"[{username}] 本轮无有效按钮")
            if processed_count > 0:
                return True  # 正常完成
            max_retries -= 1
            await page.wait_for_timeout(3000)
            continue

        print(f"[{username}] 开始处理 {len(valid_buttons)} 个有效按钮")
        for btn in valid_buttons:
            if processed_count >= max_open_count:
                print(f"[{username}] 已达到最大处理数量 ({max_open_count})，停止处理")
                return True

            try:
                # 二次验证可见性
                await btn.scroll_into_view_if_needed()
                if not await btn.is_visible():
                    continue

                # 尝试关闭拦截弹窗
                try:
                    close_button = await page.wait_for_selector(
                        'button.close-modal, [aria-label="Close"]', 
                        timeout=2000
                    )
                    if close_button:
                        await close_button.click()
                        print(f"[{username}] 已关闭拦截弹窗")
                except PlaywrightTimeoutError:
                    print(f"[{username}] 未找到关闭按钮，可能没有弹窗")

                # 尝试等待拦截元素消失
                try:
                    await page.wait_for_selector(
                        '#headlessui-portal-root', 
                        state='hidden', 
                        timeout=5000
                    )
                    print(f"[{username}] 拦截元素已消失")
                except PlaywrightTimeoutError:
                    print(f"[{username}] 拦截元素未消失，继续尝试点击")

                # 点击按钮
                try:
                    await btn.click(delay=150)
                except Exception as e:
                    print(f"[{username}] 普通点击失败，尝试通过 JavaScript 点击: {str(e)}")
                    await page.evaluate('''(button) => button.click()''', btn)

                # 处理 Set Max 和 Confirm
                try:
                    set_max_button = await page.wait_for_selector(
                        'button:has-text("Set Max")', 
                        timeout=2000,
                        state="visible"
                    )
                    if set_max_button:
                        print(f"[{username}] 发现 Set Max 按钮，点击 Set Max")
                        await set_max_button.click()
                        await page.wait_for_timeout(1000)  # 等待1秒

                    confirm_button = await page.wait_for_selector(
                        'button:has-text("Confirm")', 
                        timeout=2000,
                        state="visible"
                    )
                    if confirm_button:
                        print(f"[{username}] 点击 Confirm 按钮")
                        await confirm_button.click()
                except PlaywrightTimeoutError:
                    print(f"[{username}] 未发现 Set Max 或 Confirm 按钮")

                # 等待8秒后点击空白处关闭弹窗
                await page.wait_for_timeout(8000)
                await page.click('body', position={'x': 2, 'y': 2}, timeout=1000)
                await page.click('body', position={'x': 2, 'y': 2}, timeout=1000)

                # 等待1秒后处理下一个按钮
                await page.wait_for_timeout(1000)
                processed_count += 1
                print(f"[{username}] 成功处理按钮 ({processed_count})")

            except Exception as e:
                print(f"[{username}] 按钮处理异常: {str(e)}")
                continue

        # 防止无限循环
        if len(valid_buttons) == 0 and processed_count == 0:
            print(f"[{username}] 未找到可处理按钮")
            break

    return True

async def perform_user_flow(playwright, username, password):
    """单个用户的完整流程"""
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    try:
        print(f"[{username}] 打开登录页面: {LOGIN_URL}")
        await page.goto(LOGIN_URL, timeout=10000)
        await page.wait_for_load_state('networkidle')
        await page.click('body', position={'x': 10, 'y': 10}, timeout=1000)
        await page.click('body', position={'x': 10, 'y': 10}, timeout=1000)
        print(f"[{username}] 登录页面加载完成")

        # 点击空白处关闭弹窗（如果有的话）
        try:
            print(f"[{username}] 尝试点击空白处关闭弹窗")
            await page.click('body', position={'x': 2, 'y': 2}, timeout=1000)
            await page.click('body', position={'x': 10, 'y': 10}, timeout=1000)
            await page.click('body', position={'x': 10, 'y': 10}, timeout=1000)
            print(f"[{username}] 已尝试关闭弹窗")
        except PlaywrightTimeoutError:
            print(f"[{username}] 点击空白处关闭弹窗操作超时，可能没有弹窗或无需此操作")

        print(f"[{username}] 开始填写用户名密码")
        await page.fill('input[type="text"]', username)
        await page.fill('input[type="password"]', password)
        print(f"[{username}] 用户名密码填写完成")

        # 点击登录按钮
        print(f"[{username}] 尝试点击 'LOG IN' 按钮")
        login_button = await page.query_selector('button:has-text("LOG IN")')
        if not login_button:
            raise Exception("未找到登录按钮")

        try:
            await login_button.click(timeout=8000)
            print(f"[{username}] 登录按钮点击成功")
        except PlaywrightTimeoutError:
            raise Exception("点击登录按钮超时，页面上可能有遮挡元素")

        # 等待5秒以处理登录后台逻辑
        print(f"[{username}] 等待5秒让页面处理登录后逻辑")
        await page.wait_for_timeout(5000)

        print(f"[{username}] 尝试导航到库存页面 {POST_LOGIN_URL}")
        try:
            await page.goto(POST_LOGIN_URL, timeout=8000)
            print(f"[{username}] 导航到库存页面成功")
        except PlaywrightTimeoutError:
            raise Exception("跳转到库存页面超时")

        # 再等待15秒确保页面加载完成
        await page.wait_for_timeout(8000)
        print(f"[{username}] 库存页面加载完成")

        # 处理Open按钮
        print(f"[{username}] 开始处理库存...")
        success = await handle_open_buttons(page, username, max_open_count=15)
        if success:
            print(f"[{username}] 所有Open处理完成")
        else:
            print(f"[{username}] Open处理可能未完全完成")

    except Exception as e:
        print(f"[{username}] 流程出错: {e}")
    finally:
        await context.close()
        await browser.close()

async def process_users(playwright):
    """批量处理用户"""
    if not os.path.exists(USER_FILE):
        print("用户文件不存在")
        return

    with open(USER_FILE, "r") as f:
        users = [line.strip().split("|") for line in f if "|" in line]

    for username, password in users:
        print(f"\n{'='*30}\n开始处理用户: {username}\n{'='*30}")
        try:
            await perform_user_flow(playwright, username, password)
        except Exception as e:
            print(f"[{username}] 用户处理失败: {str(e)}")
        await asyncio.sleep(3)  # 用户间间隔

async def main():
    """主入口"""
    print(f"\n{'#'*20} 任务启动 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {'#'*20}")
    async with async_playwright() as playwright:
        await process_users(playwright)
    print(f"\n{'#'*20} 任务完成 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {'#'*20}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断操作")

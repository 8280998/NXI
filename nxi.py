import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import os
from datetime import datetime
import aiohttp
import random
import sys

USER_FILE = 'user.txt'
POINTS_DIR = 'points'
EXECUTION_INTERVAL = 2 * 60 * 60  # 2小时执行一次
LOGIN_URL = 'https://game.everdawn.io/enter/'
BASE_POST_LOGIN_URL = 'https://game.everdawn.io/quests/3/{}/send/'
API_URL_TEMPLATE = 'https://api.everdawn.io/campaign/leaderboards?limit=50&page=1&search={}'

os.makedirs(POINTS_DIR, exist_ok=True)

sys.stdout = open(sys.stdout.fileno(), 'w', buffering=1)

async def take_screenshot(page, prefix):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    screenshot_path = f'{prefix}_{timestamp}.png'
    await page.screenshot(path=screenshot_path, full_page=True)
    print(f"截图已保存: {screenshot_path}")

async def perform_user_flow(playwright, username, password):
    # 为每个用户生成随机数字 1-6
    random_number = random.randint(1, 6)
    POST_LOGIN_URL = BASE_POST_LOGIN_URL.format(random_number)
    
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    try:
        print(f"[{username}] 打开登录页面: {LOGIN_URL}")
        await page.goto(LOGIN_URL, timeout=60000)
        await page.wait_for_load_state('networkidle')
        await page.click('body', position={'x': 10, 'y': 10}, timeout=2000)
        await page.click('body', position={'x': 10, 'y': 10}, timeout=2000)
        print(f"[{username}] 登录页面加载完成")

        # 点击空白处关闭弹窗（如果有的话）
        try:
            print(f"[{username}] 尝试点击空白处关闭弹窗")
            await page.click('body', position={'x': 2, 'y': 2}, timeout=2000)
            await page.click('body', position={'x': 10, 'y': 10}, timeout=2000)
            await page.click('body', position={'x': 10, 'y': 10}, timeout=2000)
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
            await login_button.click(timeout=30000)
            print(f"[{username}] 登录按钮点击成功")
        except PlaywrightTimeoutError:
            await take_screenshot(page, f"screenshot_{username}_login_click_timeout")
            raise Exception("点击登录按钮超时，页面上可能有遮挡元素")

        # 等待5秒以处理登录后台逻辑
        print(f"[{username}] 等待5秒让页面处理登录后逻辑")
        await page.wait_for_timeout(5000)

        print(f"[{username}] 尝试导航到任务页面 {POST_LOGIN_URL}")
        try:
            await page.goto(POST_LOGIN_URL, timeout=30000)
            print(f"[{username}] 导航到任务页面成功 (使用随机URL: {POST_LOGIN_URL})")
        except PlaywrightTimeoutError:
            raise Exception("跳转到任务页面超时")

        # 再等待15秒确保页面加载完成
        await page.wait_for_timeout(25000)
        print(f"[{username}] 任务页面加载完成")

        # 点击 "Select All" 按钮
        print(f"[{username}] 尝试点击 'Select All' 按钮")
        select_all_button = await page.query_selector('button:has-text("Select All")')
        if not select_all_button:
            raise Exception("'Select All' 按钮未找到")

        try:
            await select_all_button.click(timeout=30000)
            print(f"[{username}] 'Select All' 按钮点击成功")
        except PlaywrightTimeoutError:
            raise Exception("'Select All' 按钮点击超时")

        # 点击第一次 "Confirm" 按钮
        await page.wait_for_timeout(2000)
        print(f"[{username}] 尝试点击第一次 'Confirm' 按钮")
        confirm_button = await page.query_selector('button:has-text("Confirm")')
        if not confirm_button:
            raise Exception("'Confirm' 按钮未找到")

        try:
            await confirm_button.click(timeout=30000)
            print(f"[{username}] 第一次 'Confirm' 按钮点击成功")
        except PlaywrightTimeoutError:
            raise Exception("'Confirm' 按钮点击超时")

        # 弹出窗口出现，等待5秒后再次点击Confirm（第二次Confirm）
        print(f"[{username}] 等待5秒再处理弹窗中的Confirm")
        await page.wait_for_timeout(5000)

        # 使用locator选择第二个Confirm按钮
        popup_confirm_locator = page.locator('button:has-text("Confirm")').nth(1)
        try:
            await popup_confirm_locator.wait_for(timeout=30000)  # 等待该按钮出现
            await popup_confirm_locator.click(timeout=30000, force=True)
            print(f"[{username}] 弹窗的 'Confirm' 按钮点击成功")
        except PlaywrightTimeoutError:
            raise Exception("弹窗Confirm按钮点击超时")

        # 等待5秒后关闭浏览器
        print(f"[{username}] 等待5秒后关闭浏览器")
        await page.wait_for_timeout(5000)

    except Exception as e:
        print(f"[{username}] 执行用户流程出错: {e}")
    finally:
        await context.close()
        await browser.close()

async def query_user_points(session, username):
    api_url = API_URL_TEMPLATE.format(username)
    try:
        async with session.get(api_url, timeout=10) as response:
            if response.status != 200:
                print(f"[{username}] 积分查询请求失败，状态码: {response.status}")
                return None
            data = await response.json()
            records = data.get('items', [])
            for user in records:
                if user.get('username') == username:
                    return {
                        'user_id': user.get('user_id'),
                        'points': user.get('points'),
                        'position': user.get('position')
                    }
            return None
    except asyncio.TimeoutError:
        print(f"[{username}] 积分查询请求超时")
        raise
    except Exception as e:
        print(f"[{username}] 积分查询请求出错: {e}")
        return None

async def append_points(username, user_data):
    timestamp = datetime.now().strftime('%Y-%m-%d')
    line = f'{timestamp} "user_id": {user_data["user_id"]} "points": {user_data["points"]} "position": {user_data["position"]}\n'
    file_path = os.path.join(POINTS_DIR, f'{username}.txt')
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(line)
    print(f"[{username}] 积分信息已追加到 {file_path}")

async def process_users(playwright):
    if not os.path.exists(USER_FILE):
        print(f"用户文件 {USER_FILE} 不存在")
        return

    with open(USER_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    users = []
    for line in lines:
        parts = line.strip().split('|')
        if len(parts) != 2:
            print(f"无效的用户行格式: {line.strip()}")
            continue
        users.append((parts[0], parts[1]))

    # 执行用户流程
    for username, password in users:
        print(f"开始处理用户: {username}")
        await perform_user_flow(playwright, username, password)
        print(f"完成用户: {username}")

    # 查询所有用户积分
    async with aiohttp.ClientSession() as session:
        for username, _ in users:
            print(f"[{username}] 开始查询积分")
            try:
                user_data = await query_user_points(session, username)
                if user_data:
                    await append_points(username, user_data)
                else:
                    print(f"[{username}] 未获取到该用户的匹配积分信息或用户名不匹配")
            except asyncio.TimeoutError:
                print("积分查询超时")
                return

async def main():
    while True:
        print(f"任务开始于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        async with async_playwright() as playwright:
            await process_users(playwright)
        print(f"任务结束于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"等待 {EXECUTION_INTERVAL} 秒后再次执行...")
        await asyncio.sleep(EXECUTION_INTERVAL)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("脚本已手动停止。")

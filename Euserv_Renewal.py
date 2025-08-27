# SPDX-License-Identifier: GPL-3.0-or-later
# 版本说明: 最终版，使用Playwright进行浏览器模拟登录，以绕过JS质询。

import os
import re
import json
import time
import base64
import requests
from bs4 import BeautifulSoup
import imaplib
import email
from datetime import date
from playwright.sync_api import sync_playwright # <-- 导入Playwright

# --- 配置和常量 (保持不变) ---
EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
# ... 其他Secrets ...
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/95.0.4638.69 Safari/537.36"
)
# ... 其他常量 ...

def log(info: str):
    print(info)

# --- 核心功能函数 ---

def solve_captcha(image_bytes):
    """使用TrueCaptcha API解决验证码 (接收图片字节)"""
    log("正在调用TrueCaptcha API...")
    encoded_string = base64.b64encode(image_bytes).decode('ascii')
    url = 'https://api.apitruecaptcha.org/one/gettext'
    data = {'userid': os.getenv('CAPTCHA_USERID'), 'apikey': os.getenv('CAPTCHA_APIKEY'), 'data': encoded_string}
    
    api_response = requests.post(url=url, json=data)
    api_response.raise_for_status()
    result_data = api_response.json()

    if result_data.get('status') == 'error':
        raise Exception(f"CAPTCHA API返回错误: {result_data.get('message')}")
    captcha_text = result_data.get('result')
    if not captcha_text:
        raise Exception(f"未能从API响应中获取验证码结果: {result_data}")

    log(f"API识别结果: {captcha_text}")
    try:
        return str(eval(captcha_text.replace('x', '*').replace('X', '*')))
    except Exception as e:
        raise ValueError(f"无法计算识别出的数学表达式 '{captcha_text}': {e}")

def login(username, password):
    """使用Playwright模拟真实浏览器登录"""
    log("步骤 1/7: 开始Playwright浏览器登录流程...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        try:
            log("正在导航到登录页面...")
            page.goto("https://support.euserv.com/", timeout=60000)
            page.wait_for_selector('form[name="login"]', timeout=30000)
            log("登录页面加载完成。")

            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            log("正在点击登录按钮...")
            page.click('button[type="submit"]')
            page.wait_for_load_state('networkidle', timeout=30000)
            content = page.content()

            if "solve the following captcha" in content:
                log("检测到验证码，正在处理...")
                img_locator = page.locator('img[src*="securimage_show.php"]')
                image_bytes = img_locator.screenshot() # 直接对验证码元素截图
                
                captcha_answer = solve_captcha(image_bytes)
                log(f"验证码计算结果是: {captcha_answer}")

                page.fill('input[name="captcha_code"]', str(captcha_answer))
                page.click('button[type="submit"]')
                page.wait_for_load_state('networkidle', timeout=30000)
                content = page.content()

            if "Hello" in content or "Confirm or change your customer data here" in content:
                log("🎉 Playwright登录成功！")
                final_sess_id_match = re.search(r'name="sess_id" value="(\w+)"', content)
                if not final_sess_id_match: raise ValueError("登录成功但无法找到最终的sess_id")
                
                # 关键一步：创建并返回一个继承了浏览器Cookies的requests.Session对象
                session = requests.Session()
                session.cookies.update({c['name']: c['value'] for c in context.cookies()})
                browser.close()
                return final_sess_id_match.group(1), session
            else:
                log("❌ Playwright登录失败，最终页面不包含成功标识。")
                page.screenshot(path='error_screenshot.png')
                log("已保存错误截图到Actions的Artifacts中，请下载查看。")
                browser.close()
                return "-1", None
        except Exception as e:
            log(f"❌ Playwright执行出错: {e}")
            try:
                page.screenshot(path='error_screenshot.png')
                log("已保存错误截图到Actions的Artifacts中，请下载查看。")
            except: pass
            browser.close()
            return "-1", None

# ... get_pin_from_gmail, get_servers, renew, check_status_after_renewal, main 函数 ...
# ... 这些函数完全保持我们之前的版本不变，因为它们是基于requests的，现在会使用login函数返回的已认证session ...

# get_pin_from_gmail, get_servers, renew, check_status_after_renewal, main 等函数请保持我们上次的版本，无需修改。
# 为了完整性，这里贴出main函数，确认其调用逻辑不变。
def main():
    """主函数，处理单个账户的续期"""
    if not all([EUSERV_USERNAME, EUSERV_PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY, EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD]):
        log("一个或多个必要的Secrets未设置，请检查GitHub仓库配置。")
        exit(1)
    
    log("--- 开始 Euserv 自动续期任务 ---")
    
    sess_id, s = login(EUSERV_USERNAME, EUSERV_PASSWORD) # 调用新的Playwright登录函数
    if sess_id == "-1" or s is None:
        log("❗ 登录失败，脚本终止。")
        exit(1)
        
    servers_to_renew = get_servers(sess_id, s)
    
    if not servers_to_renew:
        log("✅ 检测到所有服务器均无需续期。")
    else:
        log(f"🔍 检测到 {len(servers_to_renew)} 台服务器需要续期: {', '.join(servers_to_renew)}")
        for server_id in servers_to_renew:
            log(f"\n🔄 --- 正在为服务器 {server_id} 执行续期 ---")
            try:
                if renew(sess_id, s, server_id):
                    log(f"✔️ 服务器 {server_id} 的续期流程已成功提交。")
                else:
                    log(f"❌ 服务器 {server_id} 的续期流程提交失败。")
            except Exception as e:
                log(f"❌ 为服务器 {server_id} 续期时发生严重错误: {e}")
            time.sleep(5)

    time.sleep(15)
    check_status_after_renewal(sess_id, s)
    log("\n🏁 --- 所有工作完成 ---")

if __name__ == "__main__":
     main()

# (请确保您文件中的get_pin_from_gmail, get_servers, renew, check_status_after_renewal函数是我们之前确定的版本)

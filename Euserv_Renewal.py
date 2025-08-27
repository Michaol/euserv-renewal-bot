# SPDX-License-Identifier: GPL-3.0-or-later

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
from playwright.sync_api import sync_playwright

# --- 配置区域 ---
EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
CAPTCHA_USERID = os.getenv('CAPTCHA_USERID')
CAPTCHA_APIKEY = os.getenv('CAPTCHA_APIKEY')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/95.0.4638.69 Safari/537.36"
)
WAITING_TIME_OF_PIN = 15

def log(info: str):
    print(info)

# --- 核心功能函数 ---
def solve_captcha(image_bytes):
    log("正在调用TrueCaptcha API...")
    encoded_string = base64.b64encode(image_bytes).decode('ascii')
    url = 'https://api.apitruecaptcha.org/one/gettext'
    data = {'userid': CAPTCHA_USERID, 'apikey': CAPTCHA_APIKEY, 'data': encoded_string}
    
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
    log("步骤 1/7: 开始Playwright浏览器登录流程...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        try:
            log("正在导航到登录页面...")
            page.goto("https://support.euserv.com/", timeout=60000)
            log("正在等待登录表单元素可见...")
            page.wait_for_selector('input[type="password"]', timeout=30000)
            log("登录页面加载完成。")

            page.get_by_label("Email address or customer ID").fill(username)
            page.get_by_label("Password").fill(password)
            log("正在点击登录按钮...")
            page.get_by_role("button", name="Login").click()
            page.wait_for_load_state('networkidle', timeout=30000)
            content = page.content()

            if "solve the following captcha" in content:
                log("检测到验证码，正在处理...")
                img_locator = page.locator('img[src*="securimage_show.php"]')
                image_bytes = img_locator.screenshot()
                
                captcha_answer = solve_captcha(image_bytes)
                log(f"验证码计算结果是: {captcha_answer}")

                page.fill('input[name="captcha_code"]', str(captcha_answer))
                page.get_by_role("button", name="Login").click()
                page.wait_for_load_state('networkidle', timeout=30000)
                content = page.content()

            if "Hello" in content or "Confirm or change your customer data here" in content:
                log("🎉 Playwright登录成功！")
                final_sess_id_match = re.search(r'name="sess_id" value="(\w+)"', content)
                if not final_sess_id_match: raise ValueError("登录成功但无法找到最终的sess_id")
                
                session = requests.Session()
                session.cookies.update({c['name']: c['value'] for c in context.cookies()})
                browser.close()
                return final_sess_id_match.group(1), session
            else:
                log("❌ Playwright登录失败，最终页面不包含成功标识。")
                page.screenshot(path='error_screenshot.png')
                log("已保存错误截图。在工作流页面可以下载此文件进行分析。")
                browser.close()
                return "-1", None
        except Exception as e:
            log(f"❌ Playwright执行出错: {e}")
            try:
                page.screenshot(path='error_screenshot.png')
                log("已保存错误截图。在工作流页面可以下载此文件进行分析。")
            except: pass
            browser.close()
            return "-1", None

def get_pin_from_gmail(host, username, password):
    log("正在连接Gmail获取PIN码...")
    today_str = date.today().strftime('%d-%b-%Y')
    for i in range(3):
        try:
            with imaplib.IMAP4_SSL(host) as mail:
                mail.login(username, password)
                mail.select('inbox')
                search_criteria = f'(SINCE "{today_str}" FROM "no-reply@euserv.com" SUBJECT "EUserv - PIN for the Confirmation of a Security Check")'
                status, messages = mail.search(None, search_criteria)
                if status == 'OK' and messages[0]:
                    latest_email_id = messages[0].split()[-1]
                    _, data = mail.fetch(latest_email_id, '(RFC822)')
                    raw_email = data[0][1].decode('utf-8')
                    msg = email.message_from_string(raw_email)
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()
                    pin_match = re.search(r"PIN:\s*\n?(\d{6})", body, re.IGNORECASE)
                    if pin_match:
                        pin = pin_match.group(1)
                        log(f"成功从Gmail获取PIN码: {pin}")
                        return pin
            log(f"第{i+1}次尝试：未找到PIN邮件，等待30秒...")
            time.sleep(30)
        except Exception as e:
            log(f"获取PIN码时发生错误: {e}")
            raise
    raise Exception("多次尝试后仍无法获取PIN码邮件。")

def get_servers(sess_id, session):
    servers_to_renew = []
    url = f"https://support.euserv.com/customer_contract.php?sess_id={sess_id}"
    headers = {"user-agent": USER_AGENT}
    f = session.get(url=url, headers=headers)
    f.raise_for_status()
    soup = BeautifulSoup(f.text, "html.parser")
    for tr in soup.select("#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr"):
        server_id_tag = tr.select_one(".td-z1-sp1-kc")
        if not server_id_tag: continue
        server_id = server_id_tag.get_text(strip=True)
        action_container = tr.select_one(".td-z1-sp2-kc .kc2_order_action_container")
        if action_container and "Contract extension possible from" not in action_container.get_text():
            servers_to_renew.append(server_id)
    return servers_to_renew

def renew(sess_id, session, order_id):
    url = "https://support.euserv.com/index.iphp"
    headers = {"user-agent": USER_AGENT, "Host": "support.euserv.com", "origin": "https://support.euserv.com"}
    data = {
        "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
        "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
    }
    session.post(url, headers=headers, data=data)
    session.post(
        url, headers=headers,
        data={
            "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
            "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
        },
    )
    time.sleep(WAITING_TIME_OF_PIN)
    pin = get_pin_from_gmail(EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD)
    data = {
        "auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1,
        "ident": f"kc2_customer_contract_details_extend_contract_{order_id}",
    }
    f = session.post(url, headers=headers, data=data)
    f.raise_for_status()
    response_json = f.json()
    if response_json.get("rs") != "success":
        raise Exception(f"获取Token失败: {f.text}")
    token = response_json["token"]["value"]
    log("成功获取续期Token")
    data = {
        "sess_id": sess_id, "ord_id": order_id,
        "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token,
    }
    final_res = session.post(url, headers=headers, data=data)
    final_res.raise_for_status()
    return True

def check_status_after_renewal(sess_id, session):
    log("正在进行续期后状态检查...")
    servers_still_to_renew = get_servers(sess_id, session)
    if not servers_still_to_renew:
        log("🎉 所有服务器均已成功续订或无需续订！")
    else:
        for server_id in servers_still_to_renew:
            log(f"⚠️ 警告: 服务器 {server_id} 在续期操作后仍显示为可续约状态。")

def main():
    if not all([EUSERV_USERNAME, EUSERV_PASSWORD, CAPTCHA_USERID, CAPTCHA_APIKEY, EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD]):
        log("一个或多个必要的Secrets未设置，请检查GitHub仓库配置。")
        exit(1)
    
    log("--- 开始 Euserv 自动续期任务 ---")
    
    sess_id, s = login(EUSERV_USERNAME, EUSERV_PASSWORD)
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

# SPDX-License-Identifier: GPL-3.0-or-later

"""
euserv 自动续期脚本 (单账户Gmail版)
功能:
- 使用我们之前的Gmail IMAP方式获取PIN码。
- 保留了最精确的登录和续期逻辑（包括获取token）。
- 移除了多账户、Telegram、Mailparser等功能。
- 修正并简化了TrueCaptcha API的调用。
"""
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

# --- 配置区域 ---

# 1. GitHub Secrets 中读取的凭据
EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
TRUECAPTCHA_USERID = os.getenv('CAPTCHA_USERID') # 注意这里Secret名称我们之前定的是CAPTCHA_USERID
TRUECAPTCHA_APIKEY = os.getenv('CAPTCHA_APIKEY') # 注意这里Secret名称我们之前定的是CAPTCHA_APIKEY
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

# 2. 常量设置
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/95.0.4638.69 Safari/537.36"
)
LOGIN_MAX_RETRY_COUNT = 3
WAITING_TIME_OF_PIN = 15 # 等待PIN邮件到达的时间（秒）

# --- 日志与装饰器 ---

def log(info: str):
    """格式化日志输出"""
    print(info)

def login_retry(max_retry):
    """登录重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(max_retry):
                if i > 0:
                    log(f"登录尝试第 {i + 1}/{max_retry} 次...")
                    time.sleep(5)
                sess_id, session = func(*args, **kwargs)
                if sess_id != "-1":
                    return sess_id, session
            log("登录失败次数过多，退出脚本。")
            return "-1", None
        return wrapper
    return decorator

# --- 核心功能函数 ---

def solve_captcha(session, captcha_image_url):
    """使用TrueCaptcha API解决验证码 (简化修正版)"""
    log("正在调用TrueCaptcha API...")
    
    response = session.get(captcha_image_url, headers={'user-agent': USER_AGENT})
    response.raise_for_status()
    
    encoded_string = base64.b64encode(response.content).decode('ascii')
    url = 'https://api.apitruecaptcha.org/one/gettext'
    data = {
        'userid': TRUECAPTCHA_USERID,
        'apikey': TRUECAPTCHA_APIKEY,
        'data': encoded_string
    }
    
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
        # 使用 eval() 安全计算结果
        return str(eval(captcha_text))
    except Exception as e:
        raise ValueError(f"无法计算识别出的数学表达式 '{captcha_text}': {e}")


def get_pin_from_gmail(host, username, password):
    """
    我们之前的Gmail PIN获取函数，用于替代Mailparser
    """
    log("正在连接Gmail获取PIN码...")
    today_str = date.today().strftime('%d-%b-%Y')
    
    for i in range(3): # 尝试三次
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


@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username, password):
    """登录EUserv并获取session"""
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    captcha_image_url = "https://support.euserv.com/securimage_show.php"
    session = requests.Session()

    sess = session.get(url, headers=headers)
    sess_id_match = re.search(r'name="sess_id" value="(\w+)"', sess.text)
    if not sess_id_match: raise ValueError("无法找到sess_id")
    sess_id = sess_id_match.group(1)
    
    login_data = {
        "email": username, "password": password, "form_selected_language": "en",
        "Submit": "Login", "subaction": "login", "sess_id": sess_id,
    }
    f = session.post(url, headers=headers, data=login_data)
    f.raise_for_status()

    if "Hello" not in f.text and "Confirm or change your customer data here" not in f.text:
        if "solve the following captcha" not in f.text:
            log(f"!!! 未知页面内容如下 !!!\n{f.text}\n--- 未知页面内容结束 ---")
            log("登录失败，响应页面既不包含成功标识，也不包含验证码。")
            return "-1", session
        else:
            log("检测到验证码，正在处理...")
            captcha_code = solve_captcha(session, captcha_image_url)
            log(f"验证码计算结果是: {captcha_code}")

            f2 = session.post(
                url, headers=headers,
                data={"subaction": "login", "sess_id": sess_id, "captcha_code": str(captcha_code)}
            )
            if "solve the following captcha" not in f2.text:
                log("验证通过")
                return sess_id, session
            else:
                log("验证失败")
                return "-1", session
    else:
        log("登录成功")
        return sess_id, session

def get_servers(sess_id, session):
    """获取可续约的服务器列表"""
    servers_to_renew = []
    # 导航到正确的合同页面
    url = f"https://support.euserv.com/customer_contract.php?sess_id={sess_id}"
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
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
    """执行完整的续期操作（包括获取token）"""
    url = "https://support.euserv.com/index.iphp"
    headers = {"user-agent": USER_AGENT, "Host": "support.euserv.com", "origin": "https://support.euserv.com"}
    
    # 1. 选择合同
    data = {
        "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
        "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
    }
    session.post(url, headers=headers, data=data)

    # 2. 触发'Security Check'窗口，这将自动触发'发送PIN'
    session.post(
        url, headers=headers,
        data={
            "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
            "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
        },
    )

    # 3. 等待并从Gmail获取PIN
    time.sleep(WAITING_TIME_OF_PIN)
    pin = get_pin_from_gmail(EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD)

    # 4. 使用PIN获取token
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

    # 5. 使用token执行最终续期
    data = {
        "sess_id": sess_id, "ord_id": order_id,
        "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token,
    }
    final_res = session.post(url, headers=headers, data=data)
    final_res.raise_for_status()
    
    # 返回True表示成功发起续期请求
    return True


def check_status_after_renewal(sess_id, session):
    """续期后再次检查状态以确认结果"""
    log("正在进行续期后状态检查...")
    servers_still_to_renew = get_servers(sess_id, session)
    if not servers_still_to_renew:
        log("🎉 所有服务器均已成功续订或无需续订！")
    else:
        for server_id in servers_still_to_renew:
            log(f"⚠️ 警告: 服务器 {server_id} 在续期操作后仍显示为可续约状态。")


def main():
    """主函数，处理单个账户的续期"""
    if not all([EUSERV_USERNAME, EUSERV_PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY, EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD]):
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
            time.sleep(5) # 每个服务器操作之间稍作停顿

    time.sleep(15) # 等待Euserv后台处理
    check_status_after_renewal(sess_id, s)
    log("\n🏁 --- 所有工作完成 ---")


if __name__ == "__main__":
     main()

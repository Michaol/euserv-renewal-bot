# SPDX-License-Identifier: GPL-3.0-or-later

import os
import re
import json
import time
import base64
import ast
import operator
import requests
from bs4 import BeautifulSoup
import imaplib
import email
from datetime import date, datetime
import smtplib
from email.mime.text import MIMEText
import hmac
import struct

EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
EUSERV_2FA = os.getenv('EUSERV_2FA')
CAPTCHA_USERID = os.getenv('CAPTCHA_USERID')
CAPTCHA_APIKEY = os.getenv('CAPTCHA_APIKEY')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL')

# ========== 配置常量 ==========
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
LOGIN_MAX_RETRY_COUNT = 3
WAITING_TIME_OF_PIN = 30
DEFAULT_TIMEOUT = 30  # HTTP请求超时时间（秒）

EUSERV_BASE_URL = "https://support.euserv.com"
EUSERV_INDEX_URL = f"{EUSERV_BASE_URL}/index.iphp"
EUSERV_CAPTCHA_URL = f"{EUSERV_BASE_URL}/securimage_show.php"
# ===============================

LOG_MESSAGES = []

def log(info: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"[{timestamp}] {info}"
    print(message)
    LOG_MESSAGES.append(message)

def send_status_email(subject_status, log_content):
    if not (NOTIFICATION_EMAIL and EMAIL_USERNAME and EMAIL_PASSWORD):
        log("邮件通知所需的一个或多个Secrets未设置，跳过发送邮件。")
        return
    log("正在准备发送状态通知邮件...")
    sender = EMAIL_USERNAME
    recipient = NOTIFICATION_EMAIL
    subject = f"Euserv 续约脚本运行报告 - {subject_status}"
    body = "Euserv 自动续约脚本本次运行的详细日志如下：\n\n" + log_content
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient
    try:
        smtp_host = EMAIL_HOST.replace("imap", "smtp")
        server = smtplib.SMTP(smtp_host, 587)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()
        log("🎉 状态通知邮件已成功发送！")
    except Exception as e:
        log(f"❌ 发送邮件失败: {e}")

def login_retry(max_retry):
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

def hotp(key, counter, digits=6, digest='sha1'):
    key = base64.b32decode(key.upper() + '=' * ((8 - len(key)) % 8))
    counter = struct.pack('>Q', counter)
    mac = hmac.new(key, counter, digest).digest()
    offset = mac[-1] & 0x0f
    binary = struct.unpack('>L', mac[offset:offset+4])[0] & 0x7fffffff
    return str(binary)[-digits:].zfill(digits)

def totp(key, time_step=30, digits=6, digest='sha1'):
    return hotp(key, int(time.time() / time_step), digits, digest)

def safe_eval_math(expression):
    """安全地计算简单数学表达式（支持 +, -, *, /）"""
    operators_map = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }
    
    def _eval(node):
        if isinstance(node, ast.Num):  # Python 3.7-
            return node.n
        elif isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op = operators_map.get(type(node.op))
            if op is None:
                raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        else:
            raise ValueError(f"不支持的表达式类型: {type(node).__name__}")
    
    expression = expression.replace('x', '*').replace('X', '*')
    tree = ast.parse(expression, mode='eval')
    return int(_eval(tree.body))

def solve_captcha(image_bytes):
    log("正在以通用模式调用TrueCaptcha API...")
    encoded_string = base64.b64encode(image_bytes).decode('ascii')
    url = 'https://api.apitruecaptcha.org/one/gettext'
    data = {
        'userid': CAPTCHA_USERID,
        'apikey': CAPTCHA_APIKEY,
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
    
    log(f"API识别出的原始文本是: {captcha_text}")
    
    try:
        if re.search(r'[a-wy-zA-WY-Z]', captcha_text):
             log("识别结果为纯文本，直接返回原始文本。")
             return captcha_text
        calculated_result = str(safe_eval_math(captcha_text))
        log(f"脚本计算出的最终答案是: {calculated_result}")
        return calculated_result
    except (ValueError, SyntaxError) as e:
        log(f"无法计算API返回的文本 '{captcha_text}'（{e}），将直接使用原始文本。")
        return captcha_text

@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username, password):
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
    url = EUSERV_INDEX_URL
    captcha_image_url = EUSERV_CAPTCHA_URL
    session = requests.Session()
    sess_res = session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    sess_res.raise_for_status()
    cookies = sess_res.cookies
    sess_id = cookies.get('PHPSESSID')
    if not sess_id:
        raise ValueError("无法从初始响应的Cookie中找到PHPSESSID")
    session.get(f"{EUSERV_BASE_URL}/pic/logo_small.png", headers=headers, timeout=DEFAULT_TIMEOUT)
    login_data = {
        "email": username, "password": password, "form_selected_language": "en",
        "Submit": "Login", "subaction": "login", "sess_id": sess_id,
    }
    f = session.post(url, headers=headers, data=login_data, timeout=DEFAULT_TIMEOUT)
    f.raise_for_status()
    if "Hello" not in f.text and "Confirm or change your customer data here" not in f.text:
        if "To finish the login process please solve the following captcha." in f.text:
            log("检测到图片验证码，正在处理...")
            image_res = session.get(captcha_image_url, headers={'user-agent': USER_AGENT}, timeout=DEFAULT_TIMEOUT)
            image_res.raise_for_status()
            timestamp = int(time.time())
            captcha_image_filename = f"captcha_image_{timestamp}.png"
            captcha_page_filename = f"captcha_page_{timestamp}.html"
            log(f"正在保存验证码图片到 {captcha_image_filename}")
            with open(captcha_image_filename, "wb") as img_file:
                img_file.write(image_res.content)
            log(f"正在保存验证码页面到 {captcha_page_filename}")
            with open(captcha_page_filename, "w", encoding="utf-8") as html_file:
                html_file.write(f.text)
            captcha_code = solve_captcha(image_res.content)
            log(f"验证码计算结果是: {captcha_code}")
            f = session.post(
                url, headers=headers,
                data={"subaction": "login", "sess_id": sess_id, "captcha_code": str(captcha_code)},
                timeout=DEFAULT_TIMEOUT
            )
            if "To finish the login process please solve the following captcha." in f.text:
                log("图片验证码验证失败，保留文件用于检查")
                return "-1", session
            log("图片验证码验证通过，清理临时文件")
            # 验证成功，删除临时文件
            try:
                os.remove(captcha_image_filename)
                os.remove(captcha_page_filename)
            except OSError:
                pass
        if "To finish the login process enter the PIN that is shown in yout authenticator app." in f.text:
            log("检测到需要2FA验证")
            if not EUSERV_2FA:
                log("未配置EUSERV_2FA Secret，无法进行2FA登录。")
                return "-1", session
            two_fa_code = totp(EUSERV_2FA)
            log("2FA动态密码已生成")
            soup = BeautifulSoup(f.text, "html.parser")
            hidden_inputs = soup.find_all("input", type="hidden")
            two_fa_data = {inp["name"]: inp.get("value", "") for inp in hidden_inputs}
            two_fa_data["pin"] = two_fa_code
            f = session.post(url, headers=headers, data=two_fa_data, timeout=DEFAULT_TIMEOUT)
            if "To finish the login process enter the PIN that is shown in yout authenticator app." in f.text:
                log("2FA验证失败")
                return "-1", session
            log("2FA验证通过")
        if "Hello" in f.text or "Confirm or change your customer data here" in f.text:
            log("登录成功")
            return sess_id, session
        else:
            log("登录失败，所有验证尝试后仍未成功。")
            return "-1", session
    else:
        log("登录成功")
        return sess_id, session

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
    log("正在访问服务器列表页面...")
    server_list = []
    url = f"{EUSERV_INDEX_URL}?sess_id={sess_id}"
    headers = {"user-agent": USER_AGENT}
    f = session.get(url=url, headers=headers, timeout=DEFAULT_TIMEOUT)
    f.raise_for_status()
    soup = BeautifulSoup(f.text, "html.parser")
    selector = "#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr, #kc2_order_customer_orders_tab_content_2 .kc2_order_table.kc2_content_table tr"
    for tr in soup.select(selector):
        server_id_tag = tr.select_one(".td-z1-sp1-kc")
        if not server_id_tag: continue
        server_id = server_id_tag.get_text(strip=True)
        action_container = tr.select_one(".td-z1-sp2-kc .kc2_order_action_container")
        if action_container:
            action_text = action_container.get_text()
            if "Contract extension possible from" in action_text:
                renewal_date_match = re.search(r'\d{4}-\d{2}-\d{2}', action_text)
                renewal_date = renewal_date_match.group(0) if renewal_date_match else "未知日期"
                server_list.append({"id": server_id, "renewable": False, "date": renewal_date})
            else:
                server_list.append({"id": server_id, "renewable": True, "date": None})
    return server_list

def renew(sess_id, session, order_id):
    log(f"正在为服务器 {order_id} 触发续订流程...")
    url = EUSERV_INDEX_URL
    headers = {"user-agent": USER_AGENT, "Host": "support.euserv.com", "origin": "https://support.euserv.com"}
    data1 = {
        "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
        "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
    }
    session.post(url, headers=headers, data=data1, timeout=DEFAULT_TIMEOUT)
    data2 = {
        "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
    }
    session.post(url, headers=headers, data=data2, timeout=DEFAULT_TIMEOUT)
    time.sleep(WAITING_TIME_OF_PIN)
    pin = get_pin_from_gmail(EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD)
    data3 = {
        "auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1,
        "ident": f"kc2_customer_contract_details_extend_contract_{order_id}",
    }
    f = session.post(url, headers=headers, data=data3, timeout=DEFAULT_TIMEOUT)
    f.raise_for_status()
    response_json = f.json()
    if response_json.get("rs") != "success":
        raise Exception(f"获取Token失败: {f.text}")
    token = response_json["token"]["value"]
    log("成功获取续期Token")
    data4 = {
        "sess_id": sess_id, "ord_id": order_id,
        "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token,
    }
    final_res = session.post(url, headers=headers, data=data4, timeout=DEFAULT_TIMEOUT)
    final_res.raise_for_status()
    return True

def check_status_after_renewal(sess_id, session):
    log("正在进行续期后状态检查...")
    server_list = get_servers(sess_id, session)
    servers_still_to_renew = [s["id"] for s in server_list if s["renewable"]]
    if not servers_still_to_renew:
        log("🎉 所有服务器均已成功续订或无需续订！")
    else:
        for server_id in servers_still_to_renew:
            log(f"⚠️ 警告: 服务器 {server_id} 在续期操作后仍显示为可续约状态。")

def main():
    if not all([EUSERV_USERNAME, EUSERV_PASSWORD, CAPTCHA_USERID, CAPTCHA_APIKEY, EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD]):
        log("一个或多个必要的Secrets未设置，请检查GitHub仓库配置。")
        if LOG_MESSAGES:
            send_status_email("配置错误", "\n".join(LOG_MESSAGES))
        exit(1)
    
    status = "成功"
    try:
        log("--- 开始 Euserv 自动续期任务 ---")
        sess_id, s = login(EUSERV_USERNAME, EUSERV_PASSWORD)
        if sess_id == "-1" or s is None:
            raise Exception("登录失败")
        
        all_servers = get_servers(sess_id, s)
        servers_to_renew = [server for server in all_servers if server["renewable"]]
        
        if not all_servers:
            log("✅ 未检测到任何服务器合同。")
        elif not servers_to_renew:
            log("✅ 检测到所有服务器均无需续期。详情如下：")
            for server in all_servers:
                if not server["renewable"]:
                    log(f"   - 服务器 {server['id']}: 可续约日期为 {server['date']}")
        else:
            log(f"🔍 检测到 {len(servers_to_renew)} 台服务器需要续期: {[s['id'] for s in servers_to_renew]}")
            for server in servers_to_renew:
                log(f"\n🔄 --- 正在为服务器 {server['id']} 执行续期 ---")
                try:
                    renew(sess_id, s, server['id'])
                    log(f"✔️ 服务器 {server['id']} 的续期流程已成功提交。")
                except Exception as e:
                    log(f"❌ 为服务器 {server['id']} 续期时发生严重错误: {e}")
                    status = "失败"
        
        time.sleep(15)
        check_status_after_renewal(sess_id, s)
        log("\n🏁 --- 所有工作完成 ---")
    
    except Exception as e:
        status = "失败"
        log(f"❗ 脚本执行过程中发生致命错误: {e}")
        raise 
    finally:
        send_status_email(status, "\n".join(LOG_MESSAGES))

if __name__ == "__main__":
    main()

# SPDX-License-Identifier: GPL-3.0-or-later
# Inspired by https://github.com/zensea/AutoEUServerlessWith2FA and https://github.com/WizisCool/AutoEUServerless

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
import smtplib
from email.mime.text import MIMEText
import hmac
import struct


# 自定义异常类
class CaptchaError(Exception):
    """验证码处理相关错误"""
    pass


class PinRetrievalError(Exception):
    """PIN码获取相关错误"""
    pass


class LoginError(Exception):
    """登录相关错误"""
    pass


class RenewalError(Exception):
    """续期相关错误"""
    pass


EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
EUSERV_2FA = os.getenv('EUSERV_2FA')
CAPTCHA_USERID = os.getenv('CAPTCHA_USERID')
CAPTCHA_APIKEY = os.getenv('CAPTCHA_APIKEY')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL')

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/95.0.4638.69 Safari/537.36"
)
LOGIN_MAX_RETRY_COUNT = 3
WAITING_TIME_OF_PIN = 30

LOG_MESSAGES = []

def log(info: str):
    print(info)
    LOG_MESSAGES.append(info)

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

def _solve_captcha_local(image_bytes):
    """使用本地 ddddocr 识别验证码"""
    import ddddocr
    
    ocr = ddddocr.DdddOcr(show_ad=False)
    captcha_text = ocr.classification(image_bytes)
    
    if not captcha_text:
        return None
    
    # 尝试作为数学表达式计算
    math_text = captcha_text.replace('x', '*').replace('X', '*').replace('=', '').strip()
    cleaned = ''.join(c for c in math_text if c in '0123456789+-*/')
    
    if cleaned and any(op in cleaned for op in ['+', '-', '*', '/']):
        try:
            return str(eval(cleaned))
        except:
            pass
    
    return captcha_text


def _solve_captcha_api(image_bytes):
    """使用 TrueCaptcha API 识别验证码"""
    encoded_string = base64.b64encode(image_bytes).decode('ascii')
    url = 'https://api.apitruecaptcha.org/one/gettext'
    
    data = {
        'userid': CAPTCHA_USERID, 
        'apikey': CAPTCHA_APIKEY, 
        'data': encoded_string
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            api_response = requests.post(url=url, json=data, timeout=20)
            api_response.raise_for_status()
            result_data = api_response.json()
            
            if result_data.get('status') == 'error':
                log(f"API返回错误: {result_data.get('message')}")
                return None
            
            captcha_text = result_data.get('result')
            if captcha_text:
                # 尝试数学计算
                try:
                    return str(eval(captcha_text.replace('x', '*').replace('X', '*')))
                except:
                    return captcha_text
                    
        except requests.RequestException as e:
            log(f"API请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
    
    return None


def solve_captcha(image_bytes):
    """双保险验证码识别：本地优先，API兜底"""
    
    # 第一阶段：尝试本地 OCR (最多3次)
    log("正在使用本地 OCR (ddddocr) 识别验证码...")
    for attempt in range(3):
        try:
            result = _solve_captcha_local(image_bytes)
            if result:
                log(f"本地 OCR 识别成功: {result}")
                return result
            log(f"本地 OCR 返回空结果 (尝试 {attempt+1}/3)")
        except Exception as e:
            log(f"本地 OCR 识别失败 (尝试 {attempt+1}/3): {e}")
    
    # 第二阶段：回退到 TrueCaptcha API
    log("本地 OCR 多次失败，切换到 TrueCaptcha API...")
    if CAPTCHA_USERID and CAPTCHA_APIKEY:
        result = _solve_captcha_api(image_bytes)
        if result:
            log(f"API 识别成功: {result}")
            return result
        raise CaptchaError("TrueCaptcha API 也无法识别验证码")
    else:
        raise CaptchaError("本地 OCR 失败且未配置 API 凭据")


def _handle_captcha(session, url, captcha_image_url, headers, sess_id):
    """处理图片验证码，返回更新后的响应"""
    log("检测到图片验证码，正在处理...")
    image_res = session.get(captcha_image_url, headers={'user-agent': USER_AGENT})
    image_res.raise_for_status()
    captcha_code = solve_captcha(image_res.content)

    log(f"验证码计算结果是: {captcha_code}")
    response = session.post(
        url, headers=headers,
        data={"subaction": "login", "sess_id": sess_id, "captcha_code": str(captcha_code)}
    )
    if "To finish the login process please solve the following captcha." in response.text:
        log("图片验证码验证失败")
        return None
    log("图片验证码验证通过")
    return response


def _handle_2fa(session, url, headers, response_text):
    """处理2FA验证，返回更新后的响应"""
    log("检测到需要2FA验证")
    if not EUSERV_2FA:
        log("未配置EUSERV_2FA Secret，无法进行2FA登录。")
        return None
    
    two_fa_code = totp(EUSERV_2FA)
    log(f"生成的2FA动态密码: {two_fa_code}")
    
    soup = BeautifulSoup(response_text, "html.parser")
    hidden_inputs = soup.find_all("input", type="hidden")
    two_fa_data = {inp["name"]: inp.get("value", "") for inp in hidden_inputs}
    two_fa_data["pin"] = two_fa_code
    
    response = session.post(url, headers=headers, data=two_fa_data)
    if "To finish the login process enter the PIN that is shown in yout authenticator app." in response.text:
        log("2FA验证失败")
        return None
    log("2FA验证通过")
    return response


def _is_login_success(response_text):
    """检查是否登录成功"""
    return "Hello" in response_text or "Confirm or change your customer data here" in response_text


@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username, password):
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    captcha_image_url = "https://support.euserv.com/securimage_show.php"
    session = requests.Session()

    sess_res = session.get(url, headers=headers)
    sess_res.raise_for_status()
    sess_id = sess_res.cookies.get('PHPSESSID')
    if not sess_id:
        raise ValueError("无法从初始响应的Cookie中找到PHPSESSID")
    
    session.get("https://support.euserv.com/pic/logo_small.png", headers=headers)

    login_data = {
        "email": username, "password": password, "form_selected_language": "en",
        "Submit": "Login", "subaction": "login", "sess_id": sess_id,
    }
    f = session.post(url, headers=headers, data=login_data)
    f.raise_for_status()

    if _is_login_success(f.text):
        log("登录成功")
        return sess_id, session

    # 处理验证码
    if "To finish the login process please solve the following captcha." in f.text:
        f = _handle_captcha(session, url, captcha_image_url, headers, sess_id)
        if f is None:
            return "-1", session

    # 处理2FA
    if "To finish the login process enter the PIN that is shown in yout authenticator app." in f.text:
        f = _handle_2fa(session, url, headers, f.text)
        if f is None:
            return "-1", session

    if _is_login_success(f.text):
        log("登录成功")
        return sess_id, session
    
    log("登录失败，所有验证尝试后仍未成功。")
    return "-1", session

def _extract_email_body(msg):
    """从邮件消息中提取正文内容"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
        return ""
    return msg.get_payload(decode=True).decode()


def _fetch_pin_from_email(mail, search_criteria):
    """从邮箱中搜索并提取PIN码"""
    status, messages = mail.search(None, search_criteria)
    if status != 'OK' or not messages[0]:
        return None
    
    latest_email_id = messages[0].split()[-1]
    _, data = mail.fetch(latest_email_id, '(RFC822)')
    raw_email = data[0][1].decode('utf-8')
    msg = email.message_from_string(raw_email)
    body = _extract_email_body(msg)
    
    pin_match = re.search(r"PIN:\s*\n?(\d{6})", body, re.IGNORECASE)
    if pin_match:
        return pin_match.group(1)
    return None


def get_pin_from_gmail(host, username, password):
    log("正在连接Gmail获取PIN码...")
    today_str = date.today().strftime('%d-%b-%Y')
    search_criteria = f'(SINCE "{today_str}" FROM "no-reply@euserv.com" SUBJECT "EUserv - PIN for the Confirmation of a Security Check")'
    
    for i in range(3):
        try:
            with imaplib.IMAP4_SSL(host) as mail:
                mail.login(username, password)
                mail.select('inbox')
                pin = _fetch_pin_from_email(mail, search_criteria)
                if pin:
                    log(f"成功从Gmail获取PIN码: {pin}")
                    return pin
            log(f"第{i+1}次尝试：未找到PIN邮件，等待30秒...")
            time.sleep(30)
        except (imaplib.IMAP4.error, OSError) as e:
            log(f"获取PIN码时发生错误: {e}")
            raise PinRetrievalError(f"邮件连接错误: {e}") from e
    raise PinRetrievalError("多次尝试后仍无法获取PIN码邮件。")

def get_servers(sess_id, session):
    log("正在访问服务器列表页面...")
    server_list = []
    url = f"https://support.euserv.com/index.iphp?sess_id={sess_id}"
    headers = {"user-agent": USER_AGENT}
    f = session.get(url=url, headers=headers)
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
    url = "https://support.euserv.com/index.iphp"
    headers = {"user-agent": USER_AGENT, "Host": "support.euserv.com", "origin": "https://support.euserv.com"}
    data1 = {
        "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
        "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
    }
    session.post(url, headers=headers, data=data1)
    data2 = {
        "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
    }
    session.post(url, headers=headers, data=data2)
    time.sleep(WAITING_TIME_OF_PIN)
    pin = get_pin_from_gmail(EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD)
    data3 = {
        "auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1,
        "ident": f"kc2_customer_contract_details_extend_contract_{order_id}",
    }
    f = session.post(url, headers=headers, data=data3)
    f.raise_for_status()
    response_json = f.json()
    if response_json.get("rs") != "success":
        raise RenewalError(f"获取Token失败: {f.text}")
    token = response_json["token"]["value"]
    log("成功获取续期Token")
    data4 = {
        "sess_id": sess_id, "ord_id": order_id,
        "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token,
    }
    final_res = session.post(url, headers=headers, data=data4)
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

def _check_required_secrets():
    """检查必要的Secrets是否已配置"""
    required = [EUSERV_USERNAME, EUSERV_PASSWORD, CAPTCHA_USERID, 
                CAPTCHA_APIKEY, EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD]
    return all(required)


def _log_non_renewable_servers(all_servers):
    """记录无需续期的服务器信息"""
    log("✅ 检测到所有服务器均无需续期。详情如下：")
    for server in all_servers:
        if not server["renewable"]:
            log(f"   - 服务器 {server['id']}: 可续约日期为 {server['date']}")


def _process_renewals(sess_id, session, servers_to_renew):
    """处理服务器续期，返回是否全部成功"""
    log(f"🔍 检测到 {len(servers_to_renew)} 台服务器需要续期: {[s['id'] for s in servers_to_renew]}")
    all_success = True
    for server in servers_to_renew:
        log(f"\n🔄 --- 正在为服务器 {server['id']} 执行续期 ---")
        try:
            renew(sess_id, session, server['id'])
            log(f"✔️ 服务器 {server['id']} 的续期流程已成功提交。")
        except (RenewalError, requests.RequestException) as e:
            log(f"❌ 为服务器 {server['id']} 续期时发生严重错误: {e}")
            all_success = False
    return all_success


def main():
    if not _check_required_secrets():
        log("一个或多个必要的Secrets未设置，请检查GitHub仓库配置。")
        if LOG_MESSAGES:
            send_status_email("配置错误", "\n".join(LOG_MESSAGES))
        exit(1)
    
    status = "成功"
    try:
        log("--- 开始 Euserv 自动续期任务 ---")
        sess_id, s = login(EUSERV_USERNAME, EUSERV_PASSWORD)
        if sess_id == "-1" or s is None:
            raise LoginError("登录失败")
            
        all_servers = get_servers(sess_id, s)
        servers_to_renew = [server for server in all_servers if server["renewable"]]
        
        if not all_servers:
            log("✅ 未检测到任何服务器合同。")
        elif not servers_to_renew:
            _log_non_renewable_servers(all_servers)
        else:
            if not _process_renewals(sess_id, s, servers_to_renew):
                status = "失败"
        
        time.sleep(15)
        check_status_after_renewal(sess_id, s)
        log("\n🏁 --- 所有工作完成 ---")
    
    except (LoginError, RenewalError, PinRetrievalError, CaptchaError) as e:
        status = "失败"
        log(f"❗ 脚本执行过程中发生致命错误: {e}")
        raise
    finally:
        send_status_email(status, "\n".join(LOG_MESSAGES))

if __name__ == "__main__":
     main()
# SPDX-License-Identifier: GPL-3.0-or-later
# Inspired by https://github.com/zensea/AutoEUServerlessWith2FA and https://github.com/WizisCool/AutoEUServerless

import os
import re
import time
import base64
from enum import Enum
import requests
from bs4 import BeautifulSoup
import imaplib
import email
from datetime import date
import smtplib
from email.mime.text import MIMEText
import hmac
import struct
import ast
import operator


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

# 时间配置 (秒)
LOGIN_MAX_RETRY_COUNT = 3
WAITING_TIME_OF_PIN = 30
HTTP_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 5
API_TIMEOUT_SECONDS = 20
POST_RENEWAL_CHECK_DELAY = 15
EMAIL_CHECK_INTERVAL = 30
EMAIL_MAX_RETRIES = 3

# 退出码定义 (用于智能调度)
EXIT_SUCCESS = 0      # 续约成功或无需续约
EXIT_FAILURE = 1      # 续约失败，需要重试
EXIT_SKIPPED = 2      # 未到续约日期，跳过执行

# SMTP 配置 (可选环境变量)
SMTP_HOST = os.getenv('SMTP_HOST') or (EMAIL_HOST.replace("imap", "smtp") if EMAIL_HOST else None)
_smtp_port_env = os.getenv('SMTP_PORT')
SMTP_PORT = int(_smtp_port_env) if _smtp_port_env and _smtp_port_env.strip() else 587

# GitHub Actions 输出文件
GITHUB_OUTPUT = os.getenv('GITHUB_OUTPUT')

# 登录检测字符串常量
CAPTCHA_PROMPT = "To finish the login process please solve the following captcha."
TWO_FA_PROMPT = "To finish the login process enter the PIN that is shown in yout authenticator app."
LOGIN_SUCCESS_INDICATORS = ("Hello", "Confirm or change your customer data here")
RENEWAL_DATE_PATTERN = r"Contract extension possible from"

LOG_MESSAGES: list[str] = []
CURRENT_LOGIN_ATTEMPT = 1


class LogLevel(Enum):
    """日志级别枚举"""
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "❌"
    PROGRESS = "🔄"
    CELEBRATION = "🎉"


def log(info: str, level: LogLevel = LogLevel.INFO) -> None:
    """记录日志消息"""
    formatted = f"{level.value} {info}" if level != LogLevel.INFO else info
    print(formatted)
    LOG_MESSAGES.append(formatted)


def validate_config() -> tuple[bool, list[str]]:
    """验证必需配置，返回 (是否通过, 缺失项列表)"""
    required = {
        "EUSERV_USERNAME": EUSERV_USERNAME,
        "EUSERV_PASSWORD": EUSERV_PASSWORD,
        "EMAIL_HOST": EMAIL_HOST,
        "EMAIL_USERNAME": EMAIL_USERNAME,
        "EMAIL_PASSWORD": EMAIL_PASSWORD,
    }
    missing = [k for k, v in required.items() if not v]
    return len(missing) == 0, missing

def send_status_email(subject_status: str, log_content: str) -> None:
    if not (NOTIFICATION_EMAIL and EMAIL_USERNAME and EMAIL_PASSWORD):
        log("邮件通知所需的一个或多个Secrets未设置，跳过发送邮件。")
        return
    if not SMTP_HOST:
        log("无法推断 SMTP 服务器地址，跳过发送邮件。")
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
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()
        log("状态通知邮件已成功发送！", LogLevel.CELEBRATION)
    except Exception as e:
        log(f"发送邮件失败: {e}", LogLevel.ERROR)

def login_retry(max_retry):
    def decorator(func):
        def wrapper(*args, **kwargs):
            global CURRENT_LOGIN_ATTEMPT
            for i in range(max_retry):
                CURRENT_LOGIN_ATTEMPT = i + 1
                if i > 0:
                    log(f"登录尝试第 {i + 1}/{max_retry} 次...")
                    time.sleep(RETRY_DELAY_SECONDS)
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


def safe_eval_math(expr: str) -> int | None:
    """安全计算简单数学表达式 (仅支持 +, -, *, /)"""
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.floordiv
    }
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        raise ValueError("Unsupported expression")
    try:
        return int(_eval(ast.parse(expr, mode='eval').body))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError):
        return None


# OCR 实例缓存（懒加载单例）
_ocr_instance = None


def _get_ocr():
    """获取或创建 OCR 实例（懒加载单例，避免重复加载模型）"""
    global _ocr_instance
    if _ocr_instance is None:
        import ddddocr
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


def _solve_captcha_local(image_bytes):
    """使用本地 ddddocr 识别验证码"""
    ocr = _get_ocr()  # 使用缓存实例
    captcha_text = ocr.classification(image_bytes)

    if not captcha_text:
        return None

    # 尝试作为数学表达式计算
    math_text = captcha_text.replace('x', '*').replace('X', '*').replace('=', '').strip()
    cleaned = ''.join(c for c in math_text if c in '0123456789+-*/')

    if cleaned and any(op in cleaned for op in ['+', '-', '*', '/']):
        result = safe_eval_math(cleaned)
        if result is not None:
            return str(result)

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
            api_response = requests.post(url=url, json=data, timeout=API_TIMEOUT_SECONDS)
            api_response.raise_for_status()
            result_data = api_response.json()
            
            if result_data.get('status') == 'error':
                log(f"API返回错误: {result_data.get('message')}")
                return None
            
            captcha_text = result_data.get('result')
            if captcha_text:
                # 尝试数学计算
                math_expr = captcha_text.replace('x', '*').replace('X', '*')
                result = safe_eval_math(math_expr)
                if result is not None:
                    return str(result)
                return captcha_text
                    
        except requests.RequestException as e:
            log(f"API请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    
    return None


def solve_captcha(image_bytes):
    """双保险验证码识别：本地优先，第3次尝试起强制使用API兜底"""
    
    # 获取全局重试次数
    global CURRENT_LOGIN_ATTEMPT
    
    # 如果是第3次（或更多次）尝试，且配置了 API，则直接使用 API
    if CURRENT_LOGIN_ATTEMPT >= 3 and CAPTCHA_USERID and CAPTCHA_APIKEY:
        log(f"检测到第 {CURRENT_LOGIN_ATTEMPT} 次登录尝试，为保证成功率，直接切换到 TrueCaptcha API...")
        result = _solve_captcha_api(image_bytes)
        if result:
            log(f"API 识别成功: {result}")
            return result
    
    # 否则优先尝试本地 OCR
    log("正在使用本地 OCR (ddddocr) 识别验证码...")
    try:
        result = _solve_captcha_local(image_bytes)
        if result:
            log(f"本地 OCR 识别成功: {result}")
            return result
    except Exception as e:
        log(f"本地 OCR 识别报错: {e}")
    
    # 如果本地识别失败（返回 None 或报错），回退到 API
    log("本地 OCR 识别失败，尝试切换到 TrueCaptcha API...")
    if CAPTCHA_USERID and CAPTCHA_APIKEY:
        result = _solve_captcha_api(image_bytes)
        if result:
            log(f"API 识别成功: {result}")
            return result
        raise CaptchaError("TrueCaptcha API 也无法识别验证码")
    else:
        raise CaptchaError("本地 OCR 识别失败且未配置 API 凭据")


def _handle_captcha(session, url, captcha_image_url, headers, sess_id, username, password):
    """处理图片验证码，返回更新后的响应"""
    log("检测到图片验证码，正在处理...")
    image_res = session.get(captcha_image_url, headers={'user-agent': USER_AGENT}, timeout=HTTP_TIMEOUT_SECONDS)
    image_res.raise_for_status()
    image_bytes = image_res.content
    
    captcha_code = solve_captcha(image_bytes)

    log(f"验证码计算结果是: {captcha_code}")
    post_data = {
        "email": username, 
        "password": password, 
        "subaction": "login", 
        "sess_id": sess_id, 
        "captcha_code": str(captcha_code)
    }
    response = session.post(url, headers=headers, data=post_data, timeout=HTTP_TIMEOUT_SECONDS)
    
    if CAPTCHA_PROMPT in response.text:
        log("图片验证码验证失败")
        # 验证失败时保存验证码图片用于调试
        try:
            with open('captcha_failed.png', 'wb') as f:
                f.write(image_bytes)
            log(f"失败的验证码图片已保存到 captcha_failed.png，识别结果为: {captcha_code}")
        except OSError as e:
            log(f"保存验证码图片失败: {e}")
        return None
    log("图片验证码验证通过")
    return response


def _handle_2fa(session: requests.Session, url: str, headers: dict, response_text: str) -> requests.Response | None:
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
    
    response = session.post(url, headers=headers, data=two_fa_data, timeout=HTTP_TIMEOUT_SECONDS)
    if TWO_FA_PROMPT in response.text:
        log("2FA验证失败")
        return None
    log("2FA验证通过")
    return response


def _is_login_success(response_text: str) -> bool:
    """检查是否登录成功"""
    return any(indicator in response_text for indicator in LOGIN_SUCCESS_INDICATORS)


@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username, password):
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    captcha_image_url = "https://support.euserv.com/securimage_show.php"
    session = requests.Session()

    sess_res = session.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    sess_res.raise_for_status()
    sess_id = sess_res.cookies.get('PHPSESSID')
    if not sess_id:
        raise ValueError("无法从初始响应的Cookie中找到PHPSESSID")
    
    session.get("https://support.euserv.com/pic/logo_small.png", headers=headers, timeout=HTTP_TIMEOUT_SECONDS)

    login_data = {
        "email": username, "password": password, "form_selected_language": "en",
        "Submit": "Login", "subaction": "login", "sess_id": sess_id,
    }
    f = session.post(url, headers=headers, data=login_data, timeout=HTTP_TIMEOUT_SECONDS)
    f.raise_for_status()

    if _is_login_success(f.text):
        log("登录成功")
        return sess_id, session

    # 处理验证码
    if CAPTCHA_PROMPT in f.text:
        f = _handle_captcha(session, url, captcha_image_url, headers, sess_id, username, password)
        if f is None:
            return "-1", session

    # 处理2FA
    if TWO_FA_PROMPT in f.text:
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
    
    for i in range(EMAIL_MAX_RETRIES):
        try:
            with imaplib.IMAP4_SSL(host) as mail:
                mail.login(username, password)
                mail.select('inbox')
                pin = _fetch_pin_from_email(mail, search_criteria)
                if pin:
                    log(f"成功从Gmail获取PIN码: {pin}")
                    return pin
            log(f"第{i+1}次尝试：未找到PIN邮件，等待30秒...")
            time.sleep(EMAIL_CHECK_INTERVAL)
        except (imaplib.IMAP4.error, OSError) as e:
            log(f"获取PIN码时发生错误: {e}")
            raise PinRetrievalError(f"邮件连接错误: {e}") from e
    raise PinRetrievalError("多次尝试后仍无法获取PIN码邮件。")

def get_servers(sess_id: str, session: requests.Session) -> list[dict]:
    """获取服务器列表及其续约状态"""
    log("正在访问服务器列表页面...")
    server_list: list[dict] = []
    url = f"https://support.euserv.com/index.iphp?sess_id={sess_id}"
    headers = {"user-agent": USER_AGENT}
    f = session.get(url=url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
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
            if RENEWAL_DATE_PATTERN in action_text:
                renewal_date_match = re.search(r'\d{4}-\d{2}-\d{2}', action_text)
                renewal_date = renewal_date_match.group(0) if renewal_date_match else "未知日期"
                server_list.append({"id": server_id, "renewable": False, "date": renewal_date})
            else:
                server_list.append({"id": server_id, "renewable": True, "date": None})
    return server_list

def renew(sess_id: str, session: requests.Session, order_id: str) -> bool:
    """执行服务器续约流程"""
    log(f"正在为服务器 {order_id} 触发续订流程...")
    url = "https://support.euserv.com/index.iphp"
    headers = {"user-agent": USER_AGENT, "Host": "support.euserv.com", "origin": "https://support.euserv.com"}
    data1 = {
        "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
        "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
    }
    session.post(url, headers=headers, data=data1, timeout=HTTP_TIMEOUT_SECONDS)
    data2 = {
        "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
    }
    session.post(url, headers=headers, data=data2, timeout=HTTP_TIMEOUT_SECONDS)
    time.sleep(WAITING_TIME_OF_PIN)
    pin = get_pin_from_gmail(EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD)
    data3 = {
        "auth": pin, "sess_id": sess_id, "subaction": "kc2_security_password_get_token",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1,
        "ident": f"kc2_customer_contract_details_extend_contract_{order_id}",
    }
    f = session.post(url, headers=headers, data=data3, timeout=HTTP_TIMEOUT_SECONDS)
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
    final_res = session.post(url, headers=headers, data=data4, timeout=HTTP_TIMEOUT_SECONDS)
    final_res.raise_for_status()
    return True

def check_status_after_renewal(sess_id, session):
    log("正在进行续期后状态检查...")
    server_list = get_servers(sess_id, session)
    servers_still_to_renew = [s["id"] for s in server_list if s["renewable"]]
    if not servers_still_to_renew:
        log("所有服务器均已成功续订或无需续订！", LogLevel.CELEBRATION)
    else:
        for server_id in servers_still_to_renew:
            log(f"警告: 服务器 {server_id} 在续期操作后仍显示为可续约状态。", LogLevel.WARNING)



class RenewalBot:
    """
    Euserv VPS 自动续期机器人类。
    
    封装了全局状态，提供更好的可测试性和可维护性。
    """
    
    def __init__(self):
        """初始化机器人实例。"""
        self.log_messages: list[str] = []
        self.current_login_attempt = 1
        self.session: requests.Session | None = None
        self.sess_id: str | None = None
    
    def log(self, info: str, level: LogLevel = LogLevel.INFO) -> None:
        """记录日志消息到实例日志列表。"""
        formatted = f"{level.value} {info}" if level != LogLevel.INFO else info
        print(formatted)
        self.log_messages.append(formatted)
    
    def validate_config(self) -> tuple[bool, list[str]]:
        """验证必需配置，返回 (是否通过, 缺失项列表)。"""
        required = {
            "EUSERV_USERNAME": EUSERV_USERNAME,
            "EUSERV_PASSWORD": EUSERV_PASSWORD,
            "EMAIL_HOST": EMAIL_HOST,
            "EMAIL_USERNAME": EMAIL_USERNAME,
            "EMAIL_PASSWORD": EMAIL_PASSWORD,
        }
        missing = [k for k, v in required.items() if not v]
        return len(missing) == 0, missing
    
    def send_status_email(self, subject_status: str) -> None:
        """发送状态通知邮件。"""
        if not (NOTIFICATION_EMAIL and EMAIL_USERNAME and EMAIL_PASSWORD):
            self.log("邮件通知所需的一个或多个Secrets未设置，跳过发送邮件。")
            return
        if not SMTP_HOST:
            self.log("无法推断 SMTP 服务器地址，跳过发送邮件。")
            return
        self.log("正在准备发送状态通知邮件...")
        sender = EMAIL_USERNAME
        recipient = NOTIFICATION_EMAIL
        subject = f"Euserv 续约脚本运行报告 - {subject_status}"
        body = "Euserv 自动续约脚本本次运行的详细日志如下：\n\n" + "\n".join(self.log_messages)
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = recipient
        try:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.sendmail(sender, [recipient], msg.as_string())
            server.quit()
            self.log("状态通知邮件已成功发送！", LogLevel.CELEBRATION)
        except Exception as e:
            self.log(f"发送邮件失败: {e}", LogLevel.ERROR)

    def _perform_login(self) -> tuple[str, requests.Session]:
        """执行登录流程。"""
        sess_id, session = login(EUSERV_USERNAME, EUSERV_PASSWORD)
        if sess_id == "-1" or session is None:
            raise LoginError("登录失败")
        self.sess_id = sess_id
        self.session = session
        return sess_id, session

    def _log_non_renewable_servers(self, all_servers: list) -> None:
        """记录无需续期的服务器信息并输出下次续约日期。"""
        self.log("检测到所有服务器均无需续期。详情如下：", LogLevel.SUCCESS)
        earliest_date = None
        for server in all_servers:
            if not server["renewable"]:
                self.log(f"   - 服务器 {server['id']}: 可续约日期为 {server['date']}")
                # 记录最早的续约日期
                if server['date'] and server['date'] != "未知日期":
                    if earliest_date is None or server['date'] < earliest_date:
                        earliest_date = server['date']
        
        # 输出下次续约日期的 cron 表达式到 GITHUB_OUTPUT
        if earliest_date and GITHUB_OUTPUT:
            self._output_next_schedule(earliest_date)
    
    def _output_next_schedule(self, date_str: str) -> None:
        """输出下次续约日期的 cron 表达式到 GITHUB_OUTPUT。"""
        try:
            # 解析日期 (YYYY-MM-DD)
            parts = date_str.split('-')
            if len(parts) == 3:
                _, month, day = parts
                # 生成 cron 表达式: 分 时 日 月 周 (0 0 DD MM *)
                cron_expr = f"0 0 {int(day)} {int(month)} *"
                self.log(f"📅 下次续约日期: {date_str}", LogLevel.INFO)
                self.log(f"🔄 设置下次运行 cron: {cron_expr}", LogLevel.INFO)
                
                # 写入 GITHUB_OUTPUT
                with open(GITHUB_OUTPUT, 'a') as f:
                    f.write(f"next_cron={cron_expr}\n")
                    f.write(f"next_date={date_str}\n")
        except Exception as e:
            self.log(f"解析续约日期失败: {e}", LogLevel.WARNING)

    def _process_server_renewals(self, sess_id: str, session: requests.Session, 
                                  servers_to_renew: list) -> bool:
        """处理服务器续期，返回是否全部成功。"""
        self.log(f"🔍 检测到 {len(servers_to_renew)} 台服务器需要续期: {[s['id'] for s in servers_to_renew]}")
        all_success = True
        for server in servers_to_renew:
            self.log(f"\n🔄 --- 正在为服务器 {server['id']} 执行续期 ---")
            try:
                renew(sess_id, session, server['id'])
                self.log(f"服务器 {server['id']} 的续期流程已成功提交。", LogLevel.SUCCESS)
            except (RenewalError, requests.RequestException) as e:
                self.log(f"为服务器 {server['id']} 续期时发生严重错误: {e}", LogLevel.ERROR)
                all_success = False
        return all_success

    def _check_post_renewal_status(self, sess_id: str, session: requests.Session) -> None:
        """检查续期后的服务器状态，并显示下次续约日期。"""
        time.sleep(POST_RENEWAL_CHECK_DELAY)
        server_list = get_servers(sess_id, session)
        
        # 如果没有读取到日期，再等 30 秒重试一次（Euserv 可能需要时间更新状态）
        has_valid_date = any(s['date'] and s['date'] != "未知日期" for s in server_list)
        if not has_valid_date:
            self.log("首次读取未获取到续约日期，等待 30 秒后重试...")
            time.sleep(30)
            server_list = get_servers(sess_id, session)
        
        servers_still_to_renew = [sv["id"] for sv in server_list if sv["renewable"]]
        
        if not servers_still_to_renew:
            self.log("所有服务器均已成功续订或无需续订！", LogLevel.CELEBRATION)
            # 显示每台服务器的下次续约日期
            earliest_date = None
            for server in server_list:
                if server['date'] and server['date'] != "未知日期":
                    self.log(f"   - 服务器 {server['id']}: 下次可续约日期 {server['date']}")
                    if earliest_date is None or server['date'] < earliest_date:
                        earliest_date = server['date']
            
            # 输出最早的续约日期
            if earliest_date:
                self.log(f"📅 下次续约窗口开启时间: {earliest_date}", LogLevel.INFO)
                if GITHUB_OUTPUT:
                    self._output_next_schedule(earliest_date)
        else:
            for server_id in servers_still_to_renew:
                self.log(f"警告: 服务器 {server_id} 在续期操作后仍显示为可续约状态。", LogLevel.WARNING)

    def run(self) -> int:
        """执行续期任务的主入口。
        
        Returns:
            EXIT_SUCCESS (0): 续约成功或无需续约
            EXIT_FAILURE (1): 续约失败
            EXIT_SKIPPED (2): 未到续约日期
        """
        config_ok, missing = self.validate_config()
        if not config_ok:
            self.log(f"必要的配置未设置: {', '.join(missing)}", LogLevel.ERROR)
            if self.log_messages:
                self.send_status_email("配置错误")
            return EXIT_FAILURE

        status = "成功"
        exit_code = EXIT_SUCCESS
        try:
            self.log("--- 开始 Euserv 自动续期任务 ---")
            sess_id, s = self._perform_login()

            all_servers = get_servers(sess_id, s)
            servers_to_renew = [server for server in all_servers if server["renewable"]]

            if not all_servers:
                self.log("未检测到任何服务器合同。", LogLevel.SUCCESS)
            elif not servers_to_renew:
                # 智能调度：未到续约日期，跳过执行
                self._log_non_renewable_servers(all_servers)
                self.log("ℹ️ 未到续约日期，跳过执行。", LogLevel.INFO)
                return EXIT_SKIPPED
            else:
                if not self._process_server_renewals(sess_id, s, servers_to_renew):
                    status = "失败"
                    exit_code = EXIT_FAILURE

            self._check_post_renewal_status(sess_id, s)
            self.log("\n🏁 --- 所有工作完成 ---")

        except (LoginError, RenewalError, PinRetrievalError, CaptchaError) as e:
            status = "失败"
            exit_code = EXIT_FAILURE
            self.log(f"❗ 脚本执行过程中发生致命错误: {e}")
        finally:
            self.send_status_email(status)
        
        return exit_code


def main() -> None:
    """向后兼容的入口点，使用 RenewalBot 实例。"""
    bot = RenewalBot()
    exit_code = bot.run()
    exit(exit_code)


if __name__ == "__main__":
    main()
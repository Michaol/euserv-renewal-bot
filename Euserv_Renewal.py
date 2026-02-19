# SPDX-License-Identifier: GPL-3.0-or-later
# Inspired by https://github.com/zensea/AutoEUServerlessWith2FA and https://github.com/WizisCool/AutoEUServerless

import os
import re
import time
import base64
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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


# 环境变量配置
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
    "Chrome/131.0.0.0 Safari/537.36"
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

# URL 常量
EUSERV_BASE_URL = "https://support.euserv.com/index.iphp"
EUSERV_CAPTCHA_URL = "https://support.euserv.com/securimage_show.php"
TRUECAPTCHA_API_URL = "https://api.apitruecaptcha.org/one/gettext"


class LogLevel(Enum):
    """日志级别枚举"""
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "❌"
    PROGRESS = "🔄"
    CELEBRATION = "🎉"


def _hotp(key: str, counter: int, digits: int = 6, digest: str = 'sha1') -> str:
    """HOTP 算法实现"""
    key_bytes = base64.b32decode(key.upper() + '=' * ((8 - len(key)) % 8))
    counter_bytes = struct.pack('>Q', counter)
    mac = hmac.new(key_bytes, counter_bytes, digest).digest()
    offset = mac[-1] & 0x0f
    binary = struct.unpack('>L', mac[offset:offset+4])[0] & 0x7fffffff
    return str(binary)[-digits:].zfill(digits)


def _totp(key: str, time_step: int = 30, digits: int = 6, digest: str = 'sha1') -> str:
    """TOTP 算法实现"""
    return _hotp(key, int(time.time() / time_step), digits, digest)


def _safe_eval_math(expr: str) -> int | None:
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


def _clean_math_expr(raw: str) -> str:
    """统一清洗验证码数学表达式：替换常见字符并保留数字与运算符。"""
    cleaned = raw.replace('x', '*').replace('X', '*').replace('=', '').strip()
    return ''.join(c for c in cleaned if c in '0123456789+-*/')


def _try_solve_math(raw: str) -> str | None:
    """尝试将原始文本作为数学表达式求解，失败返回 None。"""
    cleaned = _clean_math_expr(raw)
    if cleaned and any(op in cleaned for op in ['+', '-', '*', '/']):
        result = _safe_eval_math(cleaned)
        if result is not None:
            return str(result)
    return None


class RenewalBot:
    """
    Euserv VPS 自动续期机器人类。
    
    封装了所有业务逻辑和状态，提供更好的可测试性和可维护性。
    """
    
    def __init__(self):
        """初始化机器人实例。"""
        self.log_messages: list[str] = []
        self.current_login_attempt = 1
        self.session: requests.Session | None = None
        self.sess_id: str | None = None
        self._ocr = None  # OCR 实例懒加载
    
    def _cleanup(self) -> None:
        """清理资源，关闭 HTTP Session"""
        if self.session:
            self.session.close()
            self.session = None
    
    # ==================== 日志相关 ====================
    
    def log(self, info: str, level: LogLevel = LogLevel.INFO) -> None:
        """记录日志消息到实例日志列表。"""
        formatted = f"{level.value} {info}" if level != LogLevel.INFO else info
        print(formatted)
        self.log_messages.append(formatted)
    
    # ==================== 配置验证 ====================
    
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
    
    # ==================== 邮件发送 ====================
    
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
        except smtplib.SMTPException as e:
            self.log(f"发送邮件失败: {e}", LogLevel.ERROR)
    
    # ==================== OCR 相关 ====================
    
    def _get_ocr(self):
        """获取或创建 OCR 实例（懒加载单例）"""
        if self._ocr is None:
            import ddddocr
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr
    
    def prewarm_ocr(self) -> None:
        """预加载 OCR 模型，减少首次识别延迟"""
        self.log("正在预加载 OCR 模型...", LogLevel.PROGRESS)
        try:
            self._get_ocr()
            self.log("OCR 模型预加载完成", LogLevel.SUCCESS)
        except Exception as e:
            self.log(f"OCR 预加载失败 (将在需要时重试): {e}", LogLevel.WARNING)
    
    def _solve_captcha_local(self, image_bytes: bytes) -> str | None:
        """使用本地 ddddocr 识别验证码"""
        ocr = self._get_ocr()
        # 限制字符集为数字和运算符，提高数学验证码识别率
        ocr.set_ranges("0123456789+-x/=")
        captcha_text = ocr.classification(image_bytes)

        if not captcha_text:
            return None

        # 尝试作为数学表达式计算
        result = _try_solve_math(captcha_text)
        return result if result else captcha_text
    
    def _solve_captcha_api(self, image_bytes: bytes) -> str | None:
        """使用 TrueCaptcha API 识别验证码"""
        encoded_string = base64.b64encode(image_bytes).decode('ascii')
        
        data = {
            'userid': CAPTCHA_USERID, 
            'apikey': CAPTCHA_APIKEY, 
            'data': encoded_string
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                api_response = requests.post(url=TRUECAPTCHA_API_URL, json=data, timeout=API_TIMEOUT_SECONDS)
                api_response.raise_for_status()
                result_data = api_response.json()
                
                if result_data.get('status') == 'error':
                    self.log(f"API返回错误: {result_data.get('message')}")
                    return None
                
                captcha_text = result_data.get('result')
                if captcha_text:
                    # 使用统一的数学表达式求解
                    result = _try_solve_math(captcha_text)
                    return result if result else captcha_text
                        
            except requests.RequestException as e:
                self.log(f"API请求失败 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
        
        return None
    
    def _solve_captcha(self, image_bytes: bytes) -> str:
        """双保险验证码识别：本地优先，第3次尝试起强制使用API兜底"""
        
        # 如果是第3次（或更多次）尝试，且配置了 API，则直接使用 API
        if self.current_login_attempt >= 3 and CAPTCHA_USERID and CAPTCHA_APIKEY:
            self.log(f"检测到第 {self.current_login_attempt} 次登录尝试，为保证成功率，直接切换到 TrueCaptcha API...")
            result = self._solve_captcha_api(image_bytes)
            if result:
                self.log(f"API 识别成功: {result}")
                return result
        
        # 否则优先尝试本地 OCR
        self.log("正在使用本地 OCR (ddddocr) 识别验证码...")
        try:
            result = self._solve_captcha_local(image_bytes)
            if result:
                self.log(f"本地 OCR 识别成功: {result}")
                return result
        except Exception as e:
            self.log(f"本地 OCR 识别报错: {e}")
        
        # 如果本地识别失败，回退到 API
        self.log("本地 OCR 识别失败，尝试切换到 TrueCaptcha API...")
        if CAPTCHA_USERID and CAPTCHA_APIKEY:
            result = self._solve_captcha_api(image_bytes)
            if result:
                self.log(f"API 识别成功: {result}")
                return result
            raise CaptchaError("TrueCaptcha API 也无法识别验证码")
        else:
            raise CaptchaError("本地 OCR 识别失败且未配置 API 凭据")
    
    # ==================== 验证码和2FA处理 ====================
    
    def _handle_captcha(self, url: str, captcha_image_url: str, headers: dict, 
                        sess_id: str, username: str, password: str) -> requests.Response | None:
        """处理图片验证码，返回更新后的响应"""
        self.log("检测到图片验证码，正在处理...")
        image_res = self.session.get(captcha_image_url, headers={'user-agent': USER_AGENT}, timeout=HTTP_TIMEOUT_SECONDS)
        image_res.raise_for_status()
        image_bytes = image_res.content
        
        captcha_code = self._solve_captcha(image_bytes)

        self.log(f"验证码计算结果是: {captcha_code}")
        post_data = {
            "email": username, 
            "password": password, 
            "subaction": "login", 
            "sess_id": sess_id, 
            "captcha_code": str(captcha_code)
        }
        response = self.session.post(url, headers=headers, data=post_data, timeout=HTTP_TIMEOUT_SECONDS)
        
        if CAPTCHA_PROMPT in response.text:
            self.log("图片验证码验证失败")
            # 验证失败时保存验证码图片用于调试
            try:
                with open('captcha_failed.png', 'wb') as f:
                    f.write(image_bytes)
                self.log(f"失败的验证码图片已保存到 captcha_failed.png，识别结果为: {captcha_code}")
            except OSError as e:
                self.log(f"保存验证码图片失败: {e}")
            return None
        self.log("图片验证码验证通过")
        return response
    
    def _handle_2fa(self, url: str, headers: dict, response_text: str) -> requests.Response | None:
        """处理2FA验证，返回更新后的响应"""
        self.log("检测到需要2FA验证")
        if not EUSERV_2FA:
            self.log("未配置EUSERV_2FA Secret，无法进行2FA登录。")
            return None
        
        two_fa_code = _totp(EUSERV_2FA)
        self.log(f"已生成2FA动态密码: ****{two_fa_code[-2:]}")
        
        soup = BeautifulSoup(response_text, "html.parser")
        hidden_inputs = soup.find_all("input", type="hidden")
        two_fa_data = {inp["name"]: inp.get("value", "") for inp in hidden_inputs}
        two_fa_data["pin"] = two_fa_code
        
        response = self.session.post(url, headers=headers, data=two_fa_data, timeout=HTTP_TIMEOUT_SECONDS)
        if TWO_FA_PROMPT in response.text:
            self.log("2FA验证失败")
            return None
        self.log("2FA验证通过")
        return response
    
    @staticmethod
    def _is_login_success(response_text: str) -> bool:
        """检查是否登录成功"""
        return any(indicator in response_text for indicator in LOGIN_SUCCESS_INDICATORS)
    
    # ==================== 登录流程 ====================
    
    def _perform_login(self) -> tuple[str, requests.Session]:
        """执行登录流程，包含重试逻辑"""
        headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
        self.session = requests.Session()
        
        # 配置自动重试策略 (仅对连接错误和 5xx 状态码重试)
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=['GET', 'POST'],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

        for attempt in range(LOGIN_MAX_RETRY_COUNT):
            self.current_login_attempt = attempt + 1
            if attempt > 0:
                self.log(f"登录尝试第 {attempt + 1}/{LOGIN_MAX_RETRY_COUNT} 次...")
                time.sleep(RETRY_DELAY_SECONDS)
            
            try:
                result = self._attempt_login(headers)
                if result:
                    return result
            except (requests.RequestException, ValueError) as e:
                self.log(f"登录尝试失败: {e}")
        
        raise LoginError("登录失败次数过多，退出脚本。")
    
    def _attempt_login(self, headers: dict) -> tuple[str, requests.Session] | None:
        """单次登录尝试"""
        sess_res = self.session.get(EUSERV_BASE_URL, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        sess_res.raise_for_status()
        sess_id = sess_res.cookies.get('PHPSESSID')
        if not sess_id:
            raise ValueError("无法从初始响应的Cookie中找到PHPSESSID")
        
        # 模拟浏览器行为：请求 logo 以获取完整的 Cookie 链
        self.session.get("https://support.euserv.com/pic/logo_small.png", headers=headers, timeout=HTTP_TIMEOUT_SECONDS)

        login_data = {
            "email": EUSERV_USERNAME, "password": EUSERV_PASSWORD, "form_selected_language": "en",
            "Submit": "Login", "subaction": "login", "sess_id": sess_id,
        }
        f = self.session.post(EUSERV_BASE_URL, headers=headers, data=login_data, timeout=HTTP_TIMEOUT_SECONDS)
        f.raise_for_status()

        if self._is_login_success(f.text):
            self.log("登录成功")
            self.sess_id = sess_id
            return sess_id, self.session

        # 处理验证码
        if CAPTCHA_PROMPT in f.text:
            f = self._handle_captcha(EUSERV_BASE_URL, EUSERV_CAPTCHA_URL, headers, sess_id, EUSERV_USERNAME, EUSERV_PASSWORD)
            if f is None:
                return None

        # 处理2FA
        if TWO_FA_PROMPT in f.text:
            f = self._handle_2fa(EUSERV_BASE_URL, headers, f.text)
            if f is None:
                return None

        if self._is_login_success(f.text):
            self.log("登录成功")
            self.sess_id = sess_id
            return sess_id, self.session
        
        self.log("登录失败，所有验证尝试后仍未成功。")
        return None
    
    # ==================== PIN 码获取 ====================
    
    @staticmethod
    def _extract_email_body(msg: email.message.Message) -> str:
        """从邮件消息中提取正文内容"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode()
            return ""
        return msg.get_payload(decode=True).decode()
    
    def _fetch_pin_from_email(self, mail: imaplib.IMAP4_SSL, search_criteria: str) -> str | None:
        """从邮箱中搜索并提取PIN码"""
        status, messages = mail.search(None, search_criteria)
        if status != 'OK' or not messages[0]:
            return None
        
        latest_email_id = messages[0].split()[-1]
        _, data = mail.fetch(latest_email_id, '(RFC822)')
        raw_email = data[0][1].decode('utf-8')
        msg = email.message_from_string(raw_email)
        body = self._extract_email_body(msg)
        
        pin_match = re.search(r"PIN:\s*\n?(\d{6})", body, re.IGNORECASE)
        if pin_match:
            return pin_match.group(1)
        return None
    
    def _get_pin_from_gmail(self) -> str:
        """从Gmail获取PIN码"""
        self.log("正在连接Gmail获取PIN码...")
        today_str = date.today().strftime('%d-%b-%Y')
        search_criteria = f'(SINCE "{today_str}" FROM "no-reply@euserv.com" SUBJECT "EUserv - PIN for the Confirmation of a Security Check")'
        
        for i in range(EMAIL_MAX_RETRIES):
            try:
                with imaplib.IMAP4_SSL(EMAIL_HOST) as mail:
                    mail.login(EMAIL_USERNAME, EMAIL_PASSWORD)
                    mail.select('inbox')
                    pin = self._fetch_pin_from_email(mail, search_criteria)
                    if pin:
                        self.log(f"成功从Gmail获取PIN码: ****{pin[-2:]}")
                        return pin
                self.log(f"第{i+1}次尝试：未找到PIN邮件，等待30秒...")
                time.sleep(EMAIL_CHECK_INTERVAL)
            except (imaplib.IMAP4.error, OSError) as e:
                self.log(f"获取PIN码时发生错误: {e}")
                raise PinRetrievalError(f"邮件连接错误: {e}") from e
        raise PinRetrievalError("多次尝试后仍无法获取PIN码邮件。")
    
    # ==================== 服务器列表 ====================
    
    def _parse_server_row(self, tr) -> dict | None:
        """解析单行 <tr> 元素，返回服务器信息字典，无效行返回 None。"""
        server_id_tag = tr.select_one(".td-z1-sp1-kc")
        if not server_id_tag:
            return None
        server_id = server_id_tag.get_text(strip=True)
        action_container = tr.select_one(".td-z1-sp2-kc .kc2_order_action_container")
        if not action_container:
            return None
        action_text = action_container.get_text()
        if RENEWAL_DATE_PATTERN in action_text:
            renewal_date_match = re.search(r'\d{4}-\d{2}-\d{2}', action_text)
            renewal_date = renewal_date_match.group(0) if renewal_date_match else "未知日期"
            return {"id": server_id, "renewable": False, "date": renewal_date}
        return {"id": server_id, "renewable": True, "date": None}

    def _get_servers(self) -> list[dict]:
        """获取服务器列表及其续约状态"""
        self.log("正在访问服务器列表页面...")
        url = f"{EUSERV_BASE_URL}?sess_id={self.sess_id}"
        headers = {"user-agent": USER_AGENT}
        f = self.session.get(url=url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        f.raise_for_status()
        soup = BeautifulSoup(f.text, "html.parser")
        selector = "#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr, #kc2_order_customer_orders_tab_content_2 .kc2_order_table.kc2_content_table tr"
        matched_rows = soup.select(selector)
        server_list = [s for tr in matched_rows if (s := self._parse_server_row(tr)) is not None]
        self.log(f"发现 {len(server_list)} 台服务器合同")
        
        if not server_list:
            self.log("⚠️ 未能从页面解析出任何服务器信息，可能是页面结构变化！", LogLevel.WARNING)
            # 保存 HTML 用于离线调试
            try:
                with open('debug_page.html', 'w', encoding='utf-8') as debug_f:
                    debug_f.write(f.text)
                self.log("已保存页面 HTML 到 debug_page.html", LogLevel.INFO)
            except OSError as e:
                self.log(f"保存调试页面失败: {e}", LogLevel.WARNING)
        
        return server_list
    
    # ==================== 续期流程 ====================
    
    def _renew(self, order_id: str) -> bool:
        """执行服务器续约流程"""
        self.log(f"正在为服务器 {order_id} 触发续订流程...")
        url = EUSERV_BASE_URL
        headers = {"user-agent": USER_AGENT, "Host": "support.euserv.com", "origin": "https://support.euserv.com"}
        data1 = {
            "Submit": "Extend contract", "sess_id": self.sess_id, "ord_no": order_id,
            "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
        }
        self.session.post(url, headers=headers, data=data1, timeout=HTTP_TIMEOUT_SECONDS)
        data2 = {
            "sess_id": self.sess_id, "subaction": "show_kc2_security_password_dialog",
            "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
        }
        self.session.post(url, headers=headers, data=data2, timeout=HTTP_TIMEOUT_SECONDS)
        time.sleep(WAITING_TIME_OF_PIN)
        pin = self._get_pin_from_gmail()
        data3 = {
            "auth": pin, "sess_id": self.sess_id, "subaction": "kc2_security_password_get_token",
            "prefix": "kc2_customer_contract_details_extend_contract_", "type": 1,
            "ident": f"kc2_customer_contract_details_extend_contract_{order_id}",
        }
        f = self.session.post(url, headers=headers, data=data3, timeout=HTTP_TIMEOUT_SECONDS)
        f.raise_for_status()
        response_json = f.json()
        if response_json.get("rs") != "success":
            raise RenewalError(f"获取Token失败: {f.text}")
        token = response_json["token"]["value"]
        self.log("成功获取续期Token")
        data4 = {
            "sess_id": self.sess_id, "ord_id": order_id,
            "subaction": "kc2_customer_contract_details_extend_contract_term", "token": token,
        }
        final_res = self.session.post(url, headers=headers, data=data4, timeout=HTTP_TIMEOUT_SECONDS)
        final_res.raise_for_status()
        return True
    
    # ==================== 续期后检查 ====================
    
    def _log_non_renewable_servers(self, all_servers: list) -> None:
        """记录无需续期的服务器信息并输出下次续约日期。"""
        self.log("检测到所有服务器均无需续期。详情如下：", LogLevel.SUCCESS)
        earliest_date = None
        for server in all_servers:
            if not server["renewable"]:
                self.log(f"   - 服务器 {server['id']}: 可续约日期为 {server['date']}")
                if server['date'] and server['date'] != "未知日期":
                    if earliest_date is None or server['date'] < earliest_date:
                        earliest_date = server['date']
        
        if earliest_date and GITHUB_OUTPUT:
            self._output_next_schedule(earliest_date)
    
    def _output_next_schedule(self, date_str: str) -> None:
        """输出下次续约日期的 cron 表达式到 GITHUB_OUTPUT。"""
        try:
            parts = date_str.split('-')
            if len(parts) == 3:
                _, month, day = parts
                cron_expr = f"0 0 {int(day)} {int(month)} *"
                self.log(f"📅 下次续约日期: {date_str}", LogLevel.INFO)
                self.log(f"🔄 设置下次运行 cron: {cron_expr}", LogLevel.INFO)
                
                with open(GITHUB_OUTPUT, 'a') as f:
                    f.write(f"next_cron={cron_expr}\n")
                    f.write(f"next_date={date_str}\n")
        except (ValueError, OSError) as e:
            self.log(f"解析续约日期失败: {e}", LogLevel.WARNING)

    def _process_server_renewals(self, servers_to_renew: list) -> bool:
        """处理服务器续期，返回是否全部成功。"""
        self.log(f"🔍 检测到 {len(servers_to_renew)} 台服务器需要续期: {[s['id'] for s in servers_to_renew]}")
        all_success = True
        for server in servers_to_renew:
            self.log(f"\n🔄 --- 正在为服务器 {server['id']} 执行续期 ---")
            try:
                self._renew(server['id'])
                self.log(f"服务器 {server['id']} 的续期流程已成功提交。", LogLevel.SUCCESS)
            except (RenewalError, requests.RequestException) as e:
                self.log(f"为服务器 {server['id']} 续期时发生严重错误: {e}", LogLevel.ERROR)
                all_success = False
        return all_success

    def _check_post_renewal_status(self) -> None:
        """检查续期后的服务器状态，并显示下次续约日期。"""
        time.sleep(POST_RENEWAL_CHECK_DELAY)
        server_list = self._fetch_server_list_with_retry()
        servers_still_to_renew = [sv["id"] for sv in server_list if sv["renewable"]]
        
        if servers_still_to_renew:
            for server_id in servers_still_to_renew:
                self.log(f"警告: 服务器 {server_id} 在续期操作后仍显示为可续约状态。", LogLevel.WARNING)
        else:
            self.log("所有服务器均已成功续订或无需续订！", LogLevel.CELEBRATION)
        
        # 无论续约状态如何，都尝试输出下次续约日期
        self._display_next_renewal_dates(server_list)

    def _fetch_server_list_with_retry(self) -> list[dict]:
        """获取服务器列表，如果没有日期则重试一次。"""
        server_list = self._get_servers()
        has_valid_date = any(s['date'] and s['date'] != "未知日期" for s in server_list)
        if not has_valid_date:
            self.log("首次读取未获取到续约日期，等待 30 秒后重试...")
            time.sleep(30)
            server_list = self._get_servers()
        return server_list

    def _display_next_renewal_dates(self, server_list: list[dict]) -> None:
        """显示每台服务器的下次续约日期并输出最早日期。"""
        earliest_date = None
        for server in server_list:
            if server['date'] and server['date'] != "未知日期":
                self.log(f"   - 服务器 {server['id']}: 下次可续约日期 {server['date']}")
                if earliest_date is None or server['date'] < earliest_date:
                    earliest_date = server['date']
        
        if earliest_date:
            self.log(f"📅 下次续约窗口开启时间: {earliest_date}", LogLevel.INFO)
            if GITHUB_OUTPUT:
                self._output_next_schedule(earliest_date)
    
    # ==================== 主入口 ====================
    
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
            
            # 预加载 OCR 模型，减少首次验证码识别延迟
            self.prewarm_ocr()
            
            self._perform_login()

            all_servers = self._get_servers()
            servers_to_renew = [server for server in all_servers if server["renewable"]]

            if not all_servers:
                self.log("未检测到任何服务器合同，请检查页面是否正常！", LogLevel.WARNING)
                status = "异常"
                exit_code = EXIT_FAILURE
            elif not servers_to_renew:
                # 智能调度：未到续约日期，跳过执行
                self._log_non_renewable_servers(all_servers)
                self.log("ℹ️ 未到续约日期，跳过执行。", LogLevel.INFO)
                return EXIT_SKIPPED
            else:
                if not self._process_server_renewals(servers_to_renew):
                    status = "失败"
                    exit_code = EXIT_FAILURE

            self._check_post_renewal_status()
            self.log("\n🏁 --- 所有工作完成 ---")

        except (LoginError, RenewalError, PinRetrievalError, CaptchaError) as e:
            status = "失败"
            exit_code = EXIT_FAILURE
            self.log(f"❗ 脚本执行过程中发生致命错误: {e}")
        finally:
            self._cleanup()  # 关闭 HTTP Session
            self.send_status_email(status)
        
        return exit_code


def main() -> None:
    """向后兼容的入口点，使用 RenewalBot 实例。"""
    bot = RenewalBot()
    exit_code = bot.run()
    exit(exit_code)


if __name__ == "__main__":
    main()
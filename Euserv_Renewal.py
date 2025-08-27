# SPDX-License-Identifier: GPL-3.0-or-later
# 版本说明: 本脚本基于用户提供的 Github_Action.py 文件进行精简，用于最终的 requests 库登录测试。

import os
import re
import json
import time
import base64
import requests
from bs4 import BeautifulSoup

# --- 1. GitHub Secrets 中读取的凭据 ---
EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
TRUECAPTCHA_USERID = os.getenv('CAPTCHA_USERID')
TRUECAPTCHA_APIKEY = os.getenv('CAPTCHA_APIKEY')

# --- 2. 常量设置 ---
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/95.0.4638.69 Safari/537.36"
)
LOGIN_MAX_RETRY_COUNT = 3

def log(info: str):
    """格式化日志输出"""
    print(info)

# --- 核心功能函数 (完全来自您提供的 Github_Action.py) ---

def captcha_solver(session, captcha_image_url):
    """验证码解决器"""
    response = session.get(captcha_image_url)
    encoded_string = base64.b64encode(response.content).decode('ascii')
    url = "https://api.apitruecaptcha.org/one/gettext"
    data = {
        "userid": TRUECAPTCHA_USERID,
        "apikey": TRUECAPTCHA_APIKEY,
        "data": encoded_string,
    }
    r = requests.post(url=url, json=data)
    return r.json()

def handle_captcha_solved_result(solved):
    """处理验证码计算"""
    if "result" in solved:
        text = solved["result"]
        # 尝试直接计算
        try:
            # 替换 'x' 和 'X' 为 '*'
            text_to_eval = text.replace('x', '*').replace('X', '*')
            return str(eval(text_to_eval))
        except:
            # 如果计算失败，返回原始文本
            return text
    else:
        raise KeyError(f"未在验证码响应中找到'result': {solved}")

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
            log("登录失败次数过多，脚本终止。")
            return "-1", None
        return wrapper
    return decorator

@login_retry(max_retry=LOGIN_MAX_RETRY_COUNT)
def login(username, password):
    """登录 EUserv 并获取 session"""
    headers = {"user-agent": USER_AGENT, "origin": "https://www.euserv.com"}
    url = "https://support.euserv.com/index.iphp"
    captcha_image_url = "https://support.euserv.com/securimage_show.php"
    session = requests.Session()

    sess_res = session.get(url, headers=headers)
    sess_res.raise_for_status()

    # 从响应头中提取 PHPSESSID
    cookies = sess_res.cookies
    sess_id = cookies.get('PHPSESSID')
    if not sess_id:
         raise ValueError("无法从初始响应的Cookie中找到PHPSESSID")

    login_data = {
        "email": username,
        "password": password,
        "form_selected_language": "en",
        "Submit": "Login",
        "subaction": "login",
        "sess_id": sess_id,
    }

    log("正在提交登录信息...")
    f = session.post(url, headers=headers, data=login_data)
    f.raise_for_status()

    # --- 调试代码 ---
    log("------------------ DEBUGGING START ------------------")
    log(f"页面状态码 (Status Code): {f.status_code}")
    log(f"页面内容 (f.text) 长度: {len(f.text)} characters")
    log(f"页面内容预览 (前500字符): \n{f.text[:500]}")
    log("------------------- DEBUGGING END -------------------")

    if "Hello" not in f.text and "Confirm or change your customer data here" not in f.text:
        if "To finish the login process please solve the following captcha." not in f.text:
            log("登录失败，响应页面既不包含成功标识，也不包含验证码。")
            return "-1", session
        else:
            log("检测到验证码，正在处理...")
            solved_result = captcha_solver(session, captcha_image_url)
            captcha_code = handle_captcha_solved_result(solved_result)
            log(f"验证码计算结果是: {captcha_code}")

            f2 = session.post(
                url,
                headers=headers,
                data={
                    "subaction": "login",
                    "sess_id": sess_id,
                    "captcha_code": captcha_code,
                },
            )
            if "To finish the login process please solve the following captcha." not in f2.text:
                log("验证通过")
                return sess_id, session
            else:
                log("验证失败")
                return "-1", session
    else:
        log("登录成功")
        return sess_id, session

def main():
    """主函数"""
    log("--- 开始 Euserv 自动续期任务 (基于 Github_Action.py 简化版) ---")
    
    if not all([EUSERV_USERNAME, EUSERV_PASSWORD, TRUECAPTCHA_USERID, TRUECAPTCHA_APIKEY]):
        log("一个或多个必要的Secrets未设置，请检查GitHub仓库配置。")
        exit(1)

    sess_id, s = login(EUSERV_USERNAME, EUSERV_PASSWORD)
    
    if sess_id == "-1" or s is None:
        log("❗ 登录失败，脚本终止。")
        exit(1)
    
    log("🎉 登录测试成功！可以继续构建后续逻辑。")
    # 此处可以继续添加 get_servers, renew 等函数的调用

if __name__ == "__main__":
     main()

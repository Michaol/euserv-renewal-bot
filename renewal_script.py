# renewal_script.py
import os
import requests
from bs4 import BeautifulSoup
import pin_extractor
import sys
import base64
import re
import time

# --- 从环境变量中获取所有凭据 ---
EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
CAPTCHA_USERID = os.getenv('CAPTCHA_USERID')
CAPTCHA_APIKEY = os.getenv('CAPTCHA_APIKEY')

# --- 功能函数 ---

def solve_captcha_api(image_bytes):
    """使用 apitruecaptcha.org API 解决验证码并计算结果"""
    print("正在调用 apitruecaptcha API...")
    encoded_string = base64.b64encode(image_bytes).decode('ascii')
    url = 'https://api.apitruecaptcha.org/one/gettext'
    data = {
        'userid': CAPTCHA_USERID,
        'apikey': CAPTCHA_APIKEY,
        'data': encoded_string
    }
    
    response = requests.post(url=url, json=data)
    response.raise_for_status()
    result_data = response.json()

    if result_data.get('status') == 'error':
        raise Exception(f"CAPTCHA API返回错误: {result_data.get('message')}")
    
    captcha_result = result_data.get('result')
    if not captcha_result:
        raise Exception(f"未能从API响应中获取验证码结果: {result_data}")
        
    print(f"成功获取验证码识别结果: {captcha_result}")

    try:
        # 使用 eval() 计算结果, 例如 "8+5" -> 13
        final_answer = str(eval(captcha_result))
        print(f"计算后的最终答案: {final_answer}")
        return final_answer
    except Exception as e:
        raise ValueError(f"无法计算识别出的数学表达式 '{captcha_result}': {e}")


def login(session):
    """处理登录全过程，包括获取sess_id和解决验证码。"""
    print("步骤 1/7: 开始登录流程...")
    
    # 访问主登录页获取会话ID
    login_page_url = "https://support.euserv.com/"
    response = session.get(login_page_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    login_form = soup.find('form', {'name': 'login'})
    if not login_form: raise ValueError("在页面上找不到登录表单。")
    action_url = login_form.get('action')
    if not action_url: raise ValueError("登录表单没有 'action' 属性。")
    login_post_url = f"https://support.euserv.com/{action_url}"

    # 提交用户名和密码
    login_payload = {
        'username': EUSERV_USERNAME, 'password': EUSERV_PASSWORD, 'language': 'English'
    }
    login_response = session.post(login_post_url, data=login_payload)
    login_response.raise_for_status()

    # 检查是否需要解决验证码
    if "solve the following captcha" in login_response.text:
        print("检测到验证码页面...")
        captcha_soup = BeautifulSoup(login_response.text, 'html.parser')
        
        # 下载验证码图片
        captcha_img_tag = captcha_soup.find('img', {'src': lambda x: 'captcha.php' in x})
        if not captcha_img_tag: raise ValueError("未在页面中找到验证码图片")
        captcha_img_url = "https://support.euserv.com/" + captcha_img_tag['src']
        image_res = session.get(captcha_img_url)
        image_res.raise_for_status()

        # 解决验证码
        captcha_answer = solve_captcha_api(image_res.content)
        
        # 提交验证码结果
        captcha_form = captcha_soup.find('form')
        captcha_action_url = "https://support.euserv.com/" + captcha_form.get('action')
        captcha_input = captcha_soup.find('input', {'type': 'text'})
        captcha_payload = {captcha_input.get('name'): captcha_answer}
        
        print(f"正在提交验证码答案: {captcha_answer}")
        final_login_response = session.post(captcha_action_url, data=captcha_payload)
        final_login_response.raise_for_status()

        if "Control Panel" not in final_login_response.text or "Logout" not in final_login_response.text:
            raise Exception("提交验证码后登录失败！")
        
        print("登录成功。")
        return final_login_response
    
    print("无需验证码，登录成功。")
    return login_response


def find_server_and_trigger_renewal(session):
    """导航到服务器列表，查找免费VPS，并触发续约（如果需要）。"""
    print("步骤 2/7 & 3/7: 寻找服务器并检查续约状态...")
    
    # TODO: 1. 确认并填写服务器/合同列表页面的URL
    contracts_url = "https://support.euserv.com/customer_contract.php"
    print(f"正在访问合同列表页面: {contracts_url}")
    
    response = session.get(contracts_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # TODO: 2. 确认并填写能定位到VPS行的HTML标签和class
    contracts = soup.find_all('tr') 

    for contract in contracts:
        # TODO: 3. 确认并填写能识别出这是免费VPS的文本
        if "vServer FREE" in contract.text:
            print("已找到免费VPS合同。")
            
            # TODO: 4. 确认并填写查找“续约”按钮或链接的逻辑
            renewal_link = contract.find('a', href=lambda x: x and 'renew' in x)
            
            if renewal_link:
                renewal_url = "https://support.euserv.com/" + renewal_link['href']
                print(f"需要续约。找到续约链接: {renewal_url}")
                
                print("步骤 4/7: 正在点击续约链接以触发PIN码邮件...")
                pin_page_response = session.get(renewal_url)
                pin_page_response.raise_for_status()
                print("PIN码邮件已请求发送。")
                return pin_page_response # 返回请求PIN后的页面
            else:
                print("检查完成：无需续约。未找到续约链接。")
                return None

    raise Exception("在合同页面未找到指定的免费VPS。")


def submit_pin_and_confirm(session, pin, pin_page_response):
    """在页面输入PIN码并提交，完成续约。"""
    print("步骤 6/7 & 7/7: 准备提交PIN码并确认...")
    soup = BeautifulSoup(pin_page_response.text, 'html.parser')
    
    # TODO: 1. 确认并填写PIN码提交表单的定位逻辑
    pin_form = soup.find('form', action=lambda x: x and 'pin_check' in x)
    if not pin_form: raise ValueError("未找到PIN码提交表单")
    
    pin_action_url = "https://support.euserv.com/" + pin_form.get('action')
    pin_input = pin_form.find('input', {'type': 'text'})
    if not pin_input: raise ValueError("未找到PIN码输入框")
    
    payload = {pin_input.get('name'): pin}
    
    # 查找所有隐藏的input并添加到payload
    hidden_inputs = pin_form.find_all('input', {'type': 'hidden'})
    for hidden in hidden_inputs:
        payload[hidden.get('name')] = hidden.get('value')
    
    print(f"正在向 {pin_action_url} 提交PIN码: {pin}")
    final_response = session.post(pin_action_url, data=payload)
    final_response.raise_for_status()
    
    # TODO: 2. 确认并填写续约成功的提示文本
    if "renewal was successful" in final_response.text.lower():
        print("续约成功！")
    else:
        raise Exception("续约失败，响应页面未包含成功标识。请登录网站确认。")


def main():
    """完整续约流程的协调器。"""
    if not all([EUSERV_USERNAME, EUSERV_PASSWORD, EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD, CAPTCHA_USERID, CAPTCHA_APIKEY]):
        print("错误：一个或多个Secrets未设置。", file=sys.stderr)
        sys.exit(1)

    with requests.Session() as s:
        login(s)
        pin_page_response = find_server_and_trigger_renewal(s)
        
        if pin_page_response:
            print("步骤 5/7: 开始获取PIN码...")
            pin = pin_extractor.get_euserv_pin(EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD)
            submit_pin_and_confirm(s, pin, pin_page_response)
        else:
            print("流程结束。")

if __name__ == "__main__":
    main()
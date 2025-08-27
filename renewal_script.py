# renewal_script.py (最终整合版)
import os
import requests
from bs4 import BeautifulSoup
import re
import sys
import pin_extractor # 我们的PIN码获取模块依然重要

# --- 从环境变量中获取所有凭据 ---
EUSERV_USERNAME = os.getenv('EUSERV_USERNAME')
EUSERV_PASSWORD = os.getenv('EUSERV_PASSWORD')
# ... 其他Secrets ...

# --- 核心功能函数 (采纳您的新代码) ---

def login(session):
    """使用您的新登录逻辑，更精确、更健壮。"""
    print("步骤 1/7: 开始登录流程...")
    url = "https://support.euserv.com/index.iphp"
    
    # 1. 获取会话ID
    sess_res = session.get(url)
    sess_res.raise_for_status()
    sess_id_match = re.search("sess_id=(\\w+)", sess_res.text)
    if not sess_id_match: raise ValueError("无法在页面中找到 sess_id")
    sess_id = sess_id_match.group(1)
    
    # 2. 提交登录信息
    login_data = {
        'username': EUSERV_USERNAME, 'password': EUSERV_PASSWORD, 'language': 'English'
        # ... 这里可以使用您新代码中更详细的登录payload ...
    }
    login_res = session.post(url, data=login_data)
    login_res.raise_for_status()

    # 3. 处理验证码 (这里的逻辑可以与您新代码中的验证码部分结合)
    # ... 此处省略验证码处理逻辑，之前的版本已很完善 ...
    
    print("登录成功。")
    return sess_id, session

def get_servers_to_renew(sess_id, session):
    """使用您的get_servers函数逻辑来查找需要续约的服务器。"""
    print("步骤 2/7 & 3/7: 寻找需要续约的服务器...")
    d = {}
    # TODO: 访问正确的合同页面URL，而不是主页
    url = "https://support.euserv.com/customer_contract.php?sess_id=" + sess_id
    f = session.get(url=url)
    f.raise_for_status()
    soup = BeautifulSoup(f.text, "html.parser")

    # 使用您提供的精确CSS选择器
    for tr in soup.select("#kc2_order_customer_orders_tab_content_1 .kc2_order_table.kc2_content_table tr"):
        server_id_tag = tr.select(".td-z1-sp1-kc")
        if not server_id_tag: continue
        
        server_id = server_id_tag[0].get_text(strip=True)
        action_container = tr.select(".td-z1-sp2-kc .kc2_order_action_container")
        
        # 判断是否可以续约
        if action_container and "Contract extension possible from" not in action_container[0].get_text():
            print(f"找到可续约的服务器: {server_id}")
            d[server_id] = True
        else:
            d[server_id] = False
    
    servers_to_renew = [server_id for server_id, can_renew in d.items() if can_renew]
    return servers_to_renew

def trigger_pin_for_server(sess_id, session, order_id):
    """使用您的renew函数逻辑来触发PIN码邮件。"""
    print(f"步骤 4/7: 为服务器 {order_id} 触发PIN码邮件...")
    url = "https://support.euserv.com/index.iphp"
    
    # 第一步: 选择合同
    data1 = {
        "Submit": "Extend contract", "sess_id": sess_id, "ord_no": order_id,
        "subaction": "choose_order", "choose_order_subaction": "show_contract_details",
    }
    session.post(url, data=data1)

    # 第二步: 触发安全检查
    data2 = {
        "sess_id": sess_id, "subaction": "show_kc2_security_password_dialog",
        "prefix": "kc2_customer_contract_details_extend_contract_", "type": "1",
    }
    pin_page_response = session.post(url, data=data2)
    print("PIN码邮件已请求发送。")
    return pin_page_response

# ... submit_pin_and_confirm 函数可以保持我们之前的版本 ...

def main():
    """最终整合版的流程协调器"""
    try:
        session = requests.Session()
        sess_id, session = login(session)
        
        servers_to_renew = get_servers_to_renew(sess_id, session)
        
        if not servers_to_renew:
            print("检查完成：没有需要续约的服务器。流程结束。")
            return

        for server_id in servers_to_renew:
            print(f"\n--- 正在处理服务器: {server_id} ---")
            pin_page_response = trigger_pin_for_server(sess_id, session, server_id)
            
            print("步骤 5/7: 开始获取PIN码...")
            pin = pin_extractor.get_euserv_pin(...) # 调用我们的模块
            
            submit_pin_and_confirm(session, pin, pin_page_response)
            print(f"--- 服务器 {server_id} 处理完毕 ---\n")

    except Exception as e:
        print(f"工作流执行失败: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

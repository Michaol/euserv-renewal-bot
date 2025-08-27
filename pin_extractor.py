# pin_extractor.py
import imaplib
import email
import re
import time
from datetime import date

def get_euserv_pin(email_host, email_username, email_password):
    """
    连接到邮箱，搜索并提取Euserv VPS续约邮件中的PIN码。
    此函数只搜索当天的邮件。
    """
    print("正在连接邮箱以获取PIN码（仅限今天）...")

    today_str = date.today().strftime('%d-%b-%Y')
    print(f"搜索日期限制: {today_str} 之后")
    
    for i in range(3): # 尝试三次，每次间隔30秒
        try:
            with imaplib.IMAP4_SSL(email_host) as mail:
                mail.login(email_username, email_password)
                mail.select('inbox')

                search_criteria = f'(SINCE "{today_str}" FROM "no-reply@euserv.com" SUBJECT "EUserv - PIN for the Confirmation of a Security Check")'
                status, messages = mail.search(None, search_criteria)
                
                if status == 'OK' and messages[0]:
                    latest_email_id = messages[0].split()[-1]
                    
                    status, data = mail.fetch(latest_email_id, '(RFC822)')
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
                        print("PIN码已成功获取。")
                        return pin
                    else:
                        raise ValueError("在邮件中未找到有效的PIN码格式。")
                
                print(f"第{i+1}次尝试：未找到今天的邮件，等待30秒后重试...")
                time.sleep(30)
        
        except Exception as e:
            print(f"获取PIN码时发生错误: {e}")
            raise

    raise Exception("多次尝试后仍无法获取当天的PIN码邮件。")
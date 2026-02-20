import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from bs4 import BeautifulSoup

TARGET_URL = "https://lowendtalk.com/profile/discussions/DartNode"
STATE_FILE = "last_discussion.txt"

# 获取通知配置
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

# 获取论坛登录配置
LET_USERNAME = os.environ.get("LET_USERNAME")
LET_PASSWORD = os.environ.get("LET_PASSWORD")

def get_latest_discussion():
    with sync_playwright() as p:
        # 添加防检测启动参数
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-popup-blocking',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.new_page()
        
        # 注入隐身脚本，抹除自动化特征
        stealth_sync(page)
        
        try:
            print("正在访问目标页面...")
            page.goto(TARGET_URL, wait_until="networkidle", timeout=45000)
            
            # 如果遇到 Cloudflare 盾，给予一定的 JS 自动演算和验证时间
            if "Performing security verification" in page.content() or "Just a moment" in page.title():
                print("遇到 Cloudflare 质询盾，正在等待其自动解析...")
                time.sleep(10)  # 等待10秒看是否能自动通过
            
            # 检测是否被重定向到 signin 页面
            if "signin" in page.url.lower():
                print("检测到游客访问限制，正在执行模拟登录...")
                if not LET_USERNAME or not LET_PASSWORD:
                    print("未配置论坛登录凭据 (LET_USERNAME / LET_PASSWORD)，退出抓取。")
                    page.screenshot(path="debug_error.png", full_page=True)
                    browser.close()
                    return None

                # 依据 Vanilla Forums 的标准 DOM 结构填写表单
                page.fill('input[name="Email"]', LET_USERNAME)
                page.fill('input[name="Password"]', LET_PASSWORD)
                
                # 点击 "Sign In" 按钮
                page.click('input[type="submit"], input[value="Sign In"], #Form_SignIn')
                
                print("登录表单已提交，等待重定向回目标页面...")
                page.wait_for_url("**/profile/discussions/DartNode**", timeout=45000)
                page.wait_for_load_state("networkidle")
                print("登录成功，已进入目标页面。")

            # 无论是否经过登录，都在此时截取目标页面的快照以便排错
            print("正在截取页面快照...")
            page.screenshot(path="debug.png", full_page=True)
            html_content = page.content()
            
        except Exception as e:
            print(f"页面加载或登录失败: {e}")
            page.screenshot(path="debug_error.png", full_page=True)
            browser.close()
            return None
            
        browser.close()

    soup = BeautifulSoup(html_content, 'html.parser')
    title_div = soup.find('div', class_='Title')
    
    if title_div:
        a_tag = title_div.find('a')
        if a_tag:
            title = a_tag.get_text(strip=True)
            link = a_tag['href']
            if link.startswith('/'):
                link = "https://lowendtalk.com" + link
            return {"title": title, "link": link}
    return None

def send_email(title, link):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("未配置邮件环境变量，跳过发送。")
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[LET 提醒] DartNode 发布了新主题"
    
    body = f"检测到目标用户发布了新的 Discussion：\n\n标题: {title}\n链接: {link}"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("邮件通知已成功发送。")
    except Exception as e:
        print(f"邮件发送失败: {e}")

def main():
    latest = get_latest_discussion()
    if not latest:
        print("未提取到任何讨论。")
        return
        
    current_link = latest['link']
    
    last_link = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            last_link = f.read().strip()
            
    if current_link != last_link:
        print(f"发现新帖: {latest['title']}")
        send_email(latest['title'], current_link)
        
        with open(STATE_FILE, 'w') as f:
            f.write(current_link)
    else:
        print("状态未变更，没有新帖子。")

if __name__ == "__main__":
    main()

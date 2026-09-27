import os
import re
import urllib.request
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

# ==========================================
# 【注視機種の設定】（対象の機種名を指定）
# ==========================================
TARGET_PACHINKO = [
    "牙狼12",
]
TARGET_SLOT = [
    "ソードアート",
]
# ==========================================

def extract_data(html_content, target_keywords):
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 【最重要：サイト側の画像偽装を突破する処理】
    for img in soup.find_all("img"):
        src = img.get("src", "").lower()
        alt = img.get("alt", "")
        
        if alt and re.match(r'^[\d,]$', alt):
            img.replace_with(alt)
            continue
            
        filename = src.split("/")[-1]
        m = re.match(r'^.*?(\d)\.gif$', filename)
        if m:
            img.replace_with(m.group(1))
        elif "c.gif" in filename or "comma" in filename:
            img.replace_with(",")

    rows = soup.find_all("tr")
    parsed_data = []
    
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue
            
        cell_texts = [c.get_text(strip=True) for c in cells]
        
        rank_str = cell_texts[0]
        rank_match = re.match(r'^(\d+)', rank_str)
        if not rank_match:
            continue
        rank = rank_match.group(1)
            
        machine_name = cell_texts[2]
        if not machine_name or machine_name == "機種名":
            continue

        price_candidates = []
        diff_str = "±0円"
        diff_val = 0
        
        for i in range(3, len(cell_texts)):
            raw_text = cell_texts[i]
            
            if any(sign in raw_text for sign in ["+", "-", "＋", "－", "±"]):
                diff_str = raw_text
                if not diff_str.endswith("円"):
                    diff_str += "円"
                num_part = re.sub(r'[^\d+-]', '', diff_str.replace("＋", "+").replace("－", "-"))
                try: diff_val = int(num_part)
                except: diff_val = 0
            
            else:
                if "/" in raw_text or "導入" in raw_text:
                    continue
                m = re.search(r'[\d,]+', raw_text)
                if m:
                    extracted = m.group(0)
                    clean_num = extracted.replace(",", "")
                    if clean_num.isdigit():
                        price_candidates.append((extracted, int(clean_num)))

        price_str = "0円"
        price_val = 0
        if price_candidates:
            best_price = max(price_candidates, key=lambda x: x[1])
            price_str = best_price[0]
            if not price_str.endswith("円"):
                price_str += "円"
            price_val = best_price[1]

        parsed_data.append({
            "rank": rank,
            "name": machine_name,
            "price": price_str,
            "price_num": price_val,
            "diff": diff_str,
            "diff_num": diff_val
        })

    report_lines = []
    
    report_lines.append("【相場 上位3位】")
    for i in range(min(3, len(parsed_data))):
        d = parsed_data[i]
        report_lines.append(f" {d['rank']}位 {d['name']}：{d['price']}（前日比 {d['diff']}）")
    if not parsed_data:
        report_lines.append(" （データが見つかりませんでした）")

    report_lines.append("\n【注視機種相場】")
    for keyword in target_keywords:
        found = False
        for d in parsed_data:
            if keyword in d["name"]:
                report_lines.append(f" ・{d['name']}：{d['price']}（前日比 {d['diff']}）")
                found = True
                break
        if not found:
            report_lines.append(f" ・{keyword}：（ランキング内に見つかりませんでした）")

    report_lines.append("\n【前日比 急上昇TOP3】")
    up_data = [d for d in parsed_data if d["diff_num"] > 0]
    up_data.sort(key=lambda x: x["diff_num"], reverse=True)
    for i in range(min(3, len(up_data))):
        d = up_data[i]
        report_lines.append(f" {i+1}位 {d['name']}：{d['price']}（前日比 🔴 +{d['diff_num']:,}円）")
    if not up_data:
        report_lines.append(" （値上がり機種なし）")

    report_lines.append("\n【前日比 急降下TOP3】")
    down_data = [d for d in parsed_data if d["diff_num"] < 0]
    down_data.sort(key=lambda x: x["diff_num"])
    for i in range(min(3, len(down_data))):
        d = down_data[i]
        report_lines.append(f" {i+1}位 {d['name']}：{d['price']}（前日比 🔵 {d['diff_num']:,}円）")
    if not down_data:
        report_lines.append(" （値下がり機種なし）")

    report_lines.append("\n\n--- 以下、全取得データ ---")
    for d in parsed_data:
        report_lines.append(f"{d['rank']}位\t{d['name']}\t{d['price']}\t{d['diff']}")

    return "\n".join(report_lines)

def send_to_drive(report_text):
    req = urllib.request.Request(
        GAS_URL,
        data=report_text.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print("Googleドライブ送信完了:", resp.read().decode("utf-8"))
    except Exception as e:
        print("ドライブ送信エラー:", e)

def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")

    if not username or not password:
        raise ValueError("中古機相場のログイン情報が設定されていません。")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        )
        page = context.new_page()

        print("ログイン中...")
        page.goto("http://www.p-souba.com/index.php")
        time.sleep(3)
        pass_input = page.locator('input[type="password"]').first
        form = pass_input.locator("xpath=./ancestor::form")
        form.locator('input[type="text"]').first.fill(username)
        pass_input.fill(password)
        time.sleep(1)
        
        submit_btn = form.locator('input[type="submit"], input[type="image"], button')
        if submit_btn.count() > 0:
            submit_btn.first.click()
        else:
            pass_input.press("Enter")
        time.sleep(3)

        print("パチンコ相場データを取得中...")
        page.goto("http://www.p-souba.com/krank_1.htm")
        time.sleep(3)
        pachinko_html = "\n".join([f.content() for f in page.frames]) if page.frames else page.content()
        pachinko_report = extract_data(pachinko_html, TARGET_PACHINKO)

        print("パチスロ相場データを取得中...")
        page.goto("http://www.p-souba.com/krank_2.htm")
        time.sleep(3)
        pachislot_html = "\n".join([f.content() for f in page.frames]) if page.frames else page.content()
        pachislot_report = extract_data(pachislot_html, TARGET_SLOT)

        browser.close()

    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    full_report = f"【{now_str}】\n\n■ パチンコ相場\n{pachinko_report}\n\n========================\n\n■ パチスロ相場\n{pachislot_report}\n"

    print("レポートをGoogleドライブへ送信中...")
    send_to_drive(full_report)
    print("全処理が完了しました。")

if __name__ == "__main__":
    run()

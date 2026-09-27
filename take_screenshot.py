import os
import re
import urllib.request
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

# ==========================================
# 【注視機種の設定】（ここに対象の機種名・キーワードを入れます）
# ==========================================
TARGET_PACHINKO = [
    "牙狼12",
    # "大海物語5",
]

TARGET_SLOT = [
    "ソードアート",
    # "からくりサーカス",
]
# ==========================================


def extract_data(html_content, target_keywords):
    """HTMLから柔軟に表データを抽出し、レポートを作成する"""
    soup = BeautifulSoup(html_content, "html.parser")
    rows = soup.find_all("tr")
    
    parsed_data = []
    
    for row in rows:
        row_str = row.get_text(separator=" ", strip=True)
        
        # 相場データ行には必ず「円」が含まれる
        if "円" not in row_str:
            continue
            
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
            
        cell_texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
        if len(cell_texts) < 2:
            continue

        # 1. 機種名の特定: リンク（<a>タグ）があればそれを採用、なければ最長の文字列
        machine_name = ""
        a_tag = row.find("a")
        if a_tag and len(a_tag.get_text(strip=True)) > 1:
            machine_name = a_tag.get_text(strip=True)
        else:
            candidates = [t for t in cell_texts if "円" not in t and not re.match(r'^\d+$', t)]
            if candidates:
                machine_name = max(candidates, key=len)
                
        if not machine_name:
            continue

        # 2. 金額・前日比の特定（「〇〇円」のパターンをすべて抽出）
        money_matches = re.findall(r'([+\-＋－±]?\s*[\d,]+円)', row_str)
        if not money_matches:
            continue
            
        price_str = ""
        price_val = 0
        diff_str = "±0円"
        diff_val = 0
        
        for m in money_matches:
            clean_m = m.replace(" ", "").replace("＋", "+").replace("－", "-")
            # 符号（+、-、±）がある場合は「前日比」と判断
            if any(sign in clean_m for sign in ["+", "-", "±"]):
                diff_str = clean_m
                num_part = re.sub(r'[^\d+-]', '', clean_m)
                try:
                    diff_val = int(num_part)
                except ValueError:
                    diff_val = 0
            else:
                # 符号がないものは「相場価格」と判断
                if not price_str:
                    price_str = clean_m
                    num_part = re.sub(r'[^\d]', '', clean_m)
                    try:
                        price_val = int(num_part)
                    except ValueError:
                        price_val = 0

        # もし本体価格が空なら先頭の金額を採用
        if not price_str and money_matches:
            price_str = money_matches[0]
            num_part = re.sub(r'[^\d]', '', price_str)
            price_val = int(num_part) if num_part else 0

        # 3. 順位の特定（数字または「〇位」）
        rank = ""
        for t in cell_texts:
            m = re.match(r'^(\d+)(位)?$', t)
            if m:
                rank = m.group(1)
                break

        parsed_data.append({
            "rank": rank,
            "name": machine_name,
            "price": price_str if price_str else "0円",
            "price_num": price_val,
            "diff": diff_str,
            "diff_num": diff_val
        })
        
    # 順位が画像アイコン等で空だった場合は、上から順に連番（1, 2, 3...）を補完
    for idx, d in enumerate(parsed_data, 1):
        if not d["rank"]:
            d["rank"] = str(idx)

    # --- レポート生成 ---
    report_lines = []
    
    # 1. 上位3位
    report_lines.append("【相場 上位3位】")
    for i in range(min(3, len(parsed_data))):
        d = parsed_data[i]
        report_lines.append(f" {d['rank']}位 {d['name']}：{d['price']}（前日比 {d['diff']}）")
    if not parsed_data:
        report_lines.append(" （データが見つかりませんでした）")

    # 2. 注視機種
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

    # 3. 急上昇TOP3
    report_lines.append("\n【前日比 急上昇TOP3】")
    up_data = [d for d in parsed_data if d["diff_num"] > 0]
    up_data.sort(key=lambda x: x["diff_num"], reverse=True)
    for i in range(min(3, len(up_data))):
        d = up_data[i]
        report_lines.append(f" {i+1}位 {d['name']}：{d['price']}（前日比 🔴 +{d['diff_num']:,}円）")
    if not up_data:
        report_lines.append(" （値上がり機種なし）")

    # 4. 急降下TOP3
    report_lines.append("\n【前日比 急降下TOP3】")
    down_data = [d for d in parsed_data if d["diff_num"] < 0]
    down_data.sort(key=lambda x: x["diff_num"])
    for i in range(min(3, len(down_data))):
        d = down_data[i]
        report_lines.append(f" {i+1}位 {d['name']}：{d['price']}（前日比 🔵 {d['diff_num']:,}円）")
    if not down_data:
        report_lines.append(" （値下がり機種なし）")

    # 5. 全機種データ（Gemini参照用）
    report_lines.append("\n\n--- 以下、全取得データ ---")
    for d in parsed_data:
        report_lines.append(f"{d['rank']}位\t{d['name']}\t{d['price']}\t{d['diff']}")

    return "\n".join(report_lines)


def send_to_drive(report_text):
    """Googleドライブへレポートテキストを送信する"""
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        )
        page = context.new_page()

        # 1. ログイン
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

        # 2. パチンコ相場データ取得（フレーム構造にも完全対応）
        print("パチンコ相場データを取得中...")
        page.goto("http://www.p-souba.com/krank_1.htm")
        time.sleep(3)
        pachinko_html = "\n".join([f.content() for f in page.frames])
        pachinko_report = extract_data(pachinko_html, TARGET_PACHINKO)

        # 3. パチスロ相場データ取得（フレーム構造にも完全対応）
        print("パチスロ相場データを取得中...")
        page.goto("http://www.p-souba.com/krank_2.htm")
        time.sleep(3)
        pachislot_html = "\n".join([f.content() for f in page.frames])
        pachislot_report = extract_data(pachislot_html, TARGET_SLOT)

        browser.close()

    # 4. レポート作成 & Googleドライブへ送信
    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    
    full_report = f"【{now_str}】\n\n■ パチンコ相場\n{pachinko_report}\n\n========================\n\n■ パチスロ相場\n{pachislot_report}\n"

    print("レポートをGoogleドライブへ送信中...")
    send_to_drive(full_report)
    print("全処理が完了しました。")


if __name__ == "__main__":
    run()

import os
import urllib.request
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

# ==========================================
# 【注視機種の設定】（ここを書き換えるだけで抽出対象が変わります）
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
    """HTMLから表を解析してデータを抽出する"""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 順位表の行（tr要素）をすべて取得（サイトの構造に応じて調整が必要な場合があります。ここでは一般的なtable行を想定）
    rows = soup.find_all("tr")
    
    parsed_data = []
    
    for row in rows:
        cols = row.find_all(["td", "th"])
        if len(cols) < 5: # データ行として十分な列がない場合はスキップ
            continue
            
        row_text = [col.get_text(strip=True) for col in cols]
        
        # 順位、機種名、平均価格、前日比がどの列にあるか（実際のサイトに合わせて微調整が必要な可能性があります。仮の列番号をセット）
        # 例: 0=順位, 1=機種名, 2=メーカー, 3=平均価格, 4=前日比... と仮定
        try:
            rank = row_text[0]
            machine_name = row_text[1]
            price_str = row_text[3] # 「平均価格」の列
            diff_str = row_text[4] # 「前日比」の列
            
            # 数値に変換できそうな場合は変換（不要な文字を削除）
            price = int(price_str.replace("円", "").replace(",", "")) if "円" in price_str else 0
            
            # 前日比の判定
            diff_val = 0
            if "円" in diff_str and diff_str != "±0円":
                 # +や-の記号も考慮して数値化
                 clean_diff = diff_str.replace("円", "").replace(",", "").replace("＋", "+").replace("－", "-")
                 try:
                     diff_val = int(clean_diff)
                 except ValueError:
                     pass

            parsed_data.append({
                "rank": rank,
                "name": machine_name,
                "price": price_str,
                "price_num": price,
                "diff": diff_str,
                "diff_num": diff_val
            })
        except IndexError:
            continue
        except Exception:
            continue
            
    # 見出し行などを除外するためのフィルタリング（数値が入っているものだけ残す）
    valid_data = [d for d in parsed_data if d["rank"].isdigit()]
    
    # --- レポート用のテキストを作成 ---
    report_lines = []
    
    # 1. 上位3位
    report_lines.append("【相場 上位3位】")
    for i in range(min(3, len(valid_data))):
        d = valid_data[i]
        report_lines.append(f" {d['rank']}位 {d['name']}：{d['price']}（前日比 {d['diff']}）")
        
    # 2. 注視機種
    report_lines.append("\n【注視機種相場】")
    for keyword in target_keywords:
        found = False
        for d in valid_data:
            if keyword in d["name"]:
                report_lines.append(f" ・{d['name']}：{d['price']}（前日比 {d['diff']}）")
                found = True
                break
        if not found:
            report_lines.append(f" ・{keyword}：（ランキング100位以内に見つかりませんでした）")

    # 3. 前日比 急上昇TOP3
    report_lines.append("\n【前日比 急上昇TOP3】")
    up_data = [d for d in valid_data if d["diff_num"] > 0]
    up_data.sort(key=lambda x: x["diff_num"], reverse=True)
    for i in range(min(3, len(up_data))):
        d = up_data[i]
        report_lines.append(f" {i+1}位 {d['name']}：{d['price']}（前日比 🔴 +{d['diff_num']:,}円）")
    if not up_data:
        report_lines.append(" （値上がり機種なし）")

    # 4. 前日比 急降下TOP3
    report_lines.append("\n【前日比 急降下TOP3】")
    down_data = [d for d in valid_data if d["diff_num"] < 0]
    down_data.sort(key=lambda x: x["diff_num"]) # マイナス幅が大きい順（小さい順）
    for i in range(min(3, len(down_data))):
        d = down_data[i]
        report_lines.append(f" {i+1}位 {d['name']}：{d['price']}（前日比 🔵 {d['diff_num']:,}円）")
    if not down_data:
        report_lines.append(" （値下がり機種なし）")

    # 5. 全機種データ（Geminiに読ませるための生データ）
    report_lines.append("\n\n--- 以下、Gemini解析用 全データ（1〜100位） ---")
    for d in valid_data:
        report_lines.append(f"{d['rank']},{d['name']},{d['price']},{d['diff']}")

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

        # 2. パチンコ相場データ取得
        print("パチンコ相場データを取得中...")
        page.goto("http://www.p-souba.com/krank_1.htm")
        time.sleep(3)
        pachinko_html = page.content()
        pachinko_report = extract_data(pachinko_html, TARGET_PACHINKO)

        # 3. パチスロ相場データ取得
        print("パチスロ相場データを取得中...")
        page.goto("http://www.p-souba.com/krank_2.htm")
        time.sleep(3)
        pachislot_html = page.content()
        pachislot_report = extract_data(pachislot_html, TARGET_SLOT)

        browser.close()

    # 4. レポート作成 & Googleドライブへ送信
    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    
    full_report = f"【{now_str}】\n\n■ パチンコ相場\n{pachinko_report}\n\n========================\n\n■ パチスロ相場\n{pachislot_report}\n"

    print("レポートをGoogleドライブへ送信中...")
    send_to_drive(full_report)
    print("処理が完了しました。")

if __name__ == "__main__":
    run()

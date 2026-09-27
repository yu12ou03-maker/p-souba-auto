import os
import re
import urllib.request
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup, NavigableString
from playwright.sync_api import sync_playwright

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

# ==========================================
# 【注視機種の設定】
# ==========================================
TARGET_PACHINKO = ["牙狼12"]
TARGET_SLOT = ["ソードアート"]
# ==========================================

def parse_number_and_sign(cell):
    """指定されたセル内の文字と画像をすべて結合して数字を抽出する"""
    result = ""
    for elem in cell.descendants:
        if isinstance(elem, NavigableString):
            result += str(elem).strip()
        elif elem.name == "img":
            src = elem.get("src", "").lower()
            alt = elem.get("alt", "").strip()
            # alt属性に数字があれば優先
            if alt and re.match(r'^[\d,\+\-]+$', alt):
                result += alt
            else:
                # 画像ファイル名から数字（7.gifなど）を抽出
                m = re.search(r'(\d)\.(?:gif|png|jpg)', src)
                if m:
                    result += m.group(1)
                elif "minus" in src or "m." in src:
                    result += "-"
                elif "plus" in src or "p." in src:
                    result += "+"
    
    # マイナス記号の判定
    is_minus = "-" in result or "－" in result or "▼" in result
    
    # 数字だけを抽出
    clean_num_str = re.sub(r'[^\d]', '', result)
    num = int(clean_num_str) if clean_num_str else 0
    
    if is_minus:
        num = -abs(num)
    return num

def extract_data(html_content, target_keywords):
    soup = BeautifulSoup(html_content, "html.parser")
    rows = soup.find_all("tr")
    parsed_data = []

    # 基本の列番号（0:順位, 2:機種名, 5:平均価格, 6:前日差額）
    name_idx, price_idx, diff_idx = 2, 5, 6
    
    # 見出し行から「平均価格」の正確な列番号を動的に探す（ズレ防止）
    for row in rows[:10]:
        header_texts = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
        if "平均価格" in header_texts:
            if "機種名" in header_texts: name_idx = header_texts.index("機種名")
            price_idx = header_texts.index("平均価格")
            if "前日差額" in header_texts: diff_idx = header_texts.index("前日差額")
            break

    for row in rows:
        cells = row.find_all(["td", "th"])
        # 列数が足りない行（ヘッダーの区切りなど）はスキップ
        if len(cells) <= max(name_idx, price_idx, diff_idx):
            continue
            
        # 1. 順位の確認
        rank_text = cells[0].get_text(strip=True)
        m_rank = re.match(r'^(\d+)', rank_text)
        if not m_rank:
            continue
        rank = m_rank.group(1)
            
        # 2. 機種名の取得
        machine_name = cells[name_idx].get_text(strip=True)
        if not machine_name or machine_name == "機種名":
            continue

        # 3. 平均価格の取得（指定した列だけを画像含めてピンポイントで解析）
        price_num = parse_number_and_sign(cells[price_idx])
        price_str = f"{price_num:,}円" if price_num > 0 else "0円"

        # 4. 前日差額の取得（指定した列だけを解析）
        diff_num = parse_number_and_sign(cells[diff_idx])
        if diff_num > 0:
            diff_str = f"+{diff_num:,}円"
        elif diff_num < 0:
            diff_str = f"{diff_num:,}円"
        else:
            diff_str = "±0円"

        parsed_data.append({
            "rank": rank,
            "name": machine_name,
            "price": price_str,
            "price_num": price_num,
            "diff": diff_str,
            "diff_num": diff_num
        })

    # --- レポート生成 ---
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

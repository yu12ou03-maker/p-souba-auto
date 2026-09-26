import os
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

TARGET_PACHINKO = ["牙狼12"]
TARGET_SLOT = ["ソードアート"]

def normalize_text(text):
    return unicodedata.normalize("NFKC", text).lower().replace(" ", "").replace(" ", "")

def parse_change_val(val_str):
    clean_str = val_str.replace(",", "").replace("円", "").replace(" ", "").strip()
    if clean_str in ["-", "±0", "0", ""]:
        return 0
    match = re.search(r"([+-]?\d+)", clean_str)
    return int(match.group(1)) if match else 0

def format_change_text(change_val):
    if change_val > 0:
        return f"🔴 +{change_val:,}円"
    elif change_val < 0:
        return f"🔵 {change_val:,}円"
    return "±0円"

def analyze_ranking_table(page, category_name, target_keywords):
    rows = page.locator("table tr").all()
    all_data = []

    for row in rows:
        cells = [c.strip() for c in row.locator("th, td").all_inner_texts()]
        if not cells:
            continue

        rank_raw = cells[0].replace("位", "").strip()
        if rank_raw.isdigit():
            # 行全体の全文字を生データとして保存して確かめる
            raw_row_string = " | ".join(cells)
            
            m_name = cells[2] if len(cells) > 2 else ""
            
            # 価格と差額の判定
            m_price = ""
            c_str = ""
            for c in cells:
                c_clean = c.strip()
                if "円" in c_clean:
                    if any(c_clean.startswith(s) for s in ["+", "-", "±"]) or c_clean == "0円":
                        c_str = c_clean
                    else:
                        m_price = c_clean

            c_val = parse_change_val(c_str)

            all_data.append({
                "rank": int(rank_raw),
                "name": m_name,
                "price": m_price if m_price else "【未取得】",
                "change_val": c_val,
                "change_text": format_change_text(c_val),
                "raw_debug": raw_row_string # 実際の生データ
            })

    report_lines = [f"■ {category_name}"]

    # 注視機種の出力（生データも一緒に表示）
    report_lines.append("【注視機種相場】")
    for kw in target_keywords:
        norm_kw = normalize_text(kw)
        for item in all_data:
            if norm_kw in normalize_text(item["name"]):
                report_lines.append(f" ・{item['name']}：{item['price']}（前日比 {item['change_text']}）")
                report_lines.append(f"  [実際の生データ] {item['raw_debug']}")
                break

    return "\n".join(report_lines)

def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # ログイン
        page.goto("http://www.p-souba.com/index.php", wait_until="domcontentloaded")
        time.sleep(3)
        pass_input = page.locator('input[type="password"]').first
        form = pass_input.locator("xpath=./ancestor::form")
        form.locator('input[type="text"]').first.fill(username)
        pass_input.fill(password)
        time.sleep(1)
        pass_input.press("Enter")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # パチンコ
        page.goto("http://www.p-souba.com/krank_1.htm", wait_until="domcontentloaded")
        time.sleep(3)
        pachinko_text = analyze_ranking_table(page, "パチンコ", TARGET_PACHINKO)

        browser.close()

    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    full_report = f"【{now_str}】\n\n{pachinko_text}\n"

    with open("latest_report.txt", "w", encoding="utf-8") as f:
        f.write(full_report)

if __name__ == "__main__":
    run()

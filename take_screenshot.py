import os
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ==========================================
# 【注視機種の設定】（毎月ここを書き換えてください）
# ==========================================
TARGET_PACHINKO = [
    "牙狼12",
]

TARGET_SLOT = [
    "ソードアート",
]
# ==========================================


def normalize_text(text):
    """全角半角のゆれを吸収して比較しやすくする"""
    return unicodedata.normalize("NFKC", text).lower().replace(" ", "").replace(" ", "")


def parse_change_val(val_str):
    """前日差額の文字列を数値（整数）に変換する"""
    clean_str = val_str.replace(",", "").replace("円", "").replace(" ", "").strip()
    if clean_str in ["-", "±0", "0", ""]:
        return 0
    match = re.search(r"([+-]?\d+)", clean_str)
    if match:
        return int(match.group(1))
    return 0


def format_change_text(change_val):
    """変動額を色付きアイコンに整形する"""
    if change_val > 0:
        return f"🔴 +{change_val:,}円"
    elif change_val < 0:
        return f"🔵 {change_val:,}円"
    else:
        return "±0円"


def analyze_ranking_table(page, category_name, target_keywords):
    """ランキングページから指定機種と前日差額の急変動機種を抽出する"""
    rows = page.locator("table tr").all()
    all_data = []

    col_name = 2
    col_price = 5
    col_change = 6

    header_found = False
    for row in rows:
        cells = [c.strip() for c in row.locator("th, td").all_inner_texts()]
        if not cells:
            continue

        # ヘッダー列の自動判定（「前日」が含まれる列を探す）
        if not header_found and any("前日" in c for c in cells):
            for idx, c in enumerate(cells):
                if "機種" in c:
                    col_name = idx
                elif "価格" in c or "相場" in c:
                    col_price = idx
                elif "前日" in c:
                    col_change = idx
            header_found = True
            continue

        # データ行の解析
        if len(cells) > max(col_name, col_price, col_change):
            rank_str = cells[0].replace("位", "").strip() # 「位」を取り除いて数字だけにする
            if rank_str.isdigit():
                m_name = cells[col_name]
                m_price = cells[col_price]
                c_str = cells[col_change]
                c_val = parse_change_val(c_str)

                all_data.append({
                    "rank": int(rank_str),
                    "name": m_name,
                    "price": m_price,
                    "change_val": c_val,
                    "change_text": format_change_text(c_val)
                })

    report_lines = [f"■ {category_name}"]

    # 1. 注視機種の抽出
    report_lines.append("【注視機種相場】")
    matched_any = False
    for kw in target_keywords:
        norm_kw = normalize_text(kw)
        for item in all_data:
            if norm_kw in normalize_text(item["name"]):
                report_lines.append(f" ・{item['name']}：{item['price']}（前日比 {item['change_text']}）")
                matched_any = True
                break
    if not matched_any:
        report_lines.append(" （該当機種がランキング内に見つかりませんでした）")

    # 2. 急上昇（前日比プラスの上位3機種）
    report_lines.append("\n【前日比 急上昇TOP3】")
    up_items = [d for d in all_data if d["change_val"] > 0]
    up_items.sort(key=lambda x: x["change_val"], reverse=True)
    if up_items:
        for idx, item in enumerate(up_items[:3], 1):
            report_lines.append(f" {idx}位 {item['name']}：{item['price']}（前日比 {item['change_text']}）")
    else:
        report_lines.append(" （値上がり機種なし）")

    # 3. 急降下（前日比マイナスの上位3機種）
    report_lines.append("\n【前日比 急降下TOP3】")
    down_items = [d for d in all_data if d["change_val"] < 0]
    down_items.sort(key=lambda x: x["change_val"])  # マイナスが大きい順
    if down_items:
        for idx, item in enumerate(down_items[:3], 1):
            report_lines.append(f" {idx}位 {item['name']}：{item['price']}（前日比 {item['change_text']}）")
    else:
        report_lines.append(" （値下がり機種なし）")

    return "\n".join(report_lines)


def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")

    if not username or not password:
        raise ValueError("中古機相場のログイン情報が設定されていません。")

    os.makedirs("screenshots", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1080}
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        # 1. ログイン
        print("トップページへアクセス中...")
        page.goto("http://www.p-souba.com/index.php", wait_until="domcontentloaded")
        time.sleep(3)

        print("自動ログインを実行中...")
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
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # 2. パチンコ相場解析
        print("パチンコ相場データを解析中...")
        page.goto("http://www.p-souba.com/krank_1.htm", wait_until="domcontentloaded")
        time.sleep(3)
        pachinko_text = analyze_ranking_table(page, "パチンコ", TARGET_PACHINKO)

        # 3. パチスロ相場解析
        print("パチスロ相場データを解析中...")
        page.goto("http://www.p-souba.com/krank_2.htm", wait_until="domcontentloaded")
        time.sleep(3)
        pachislot_text = analyze_ranking_table(page, "パチスロ", TARGET_SLOT)

        browser.close()

    # 4. レポート書き出し
    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    full_report = f"【{now_str}】\n\n{pachinko_text}\n\n{pachislot_text}\n"

    with open("latest_report.txt", "w", encoding="utf-8") as f:
        f.write(full_report)

    print("レポート生成完了（latest_report.txt に保存しました）")


if __name__ == "__main__":
    run()

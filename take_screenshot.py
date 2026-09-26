import os
import time
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone, timedelta

def extract_ranking_data(page, category_name):
    """ページから直接TOP5のテキストデータを抽出する"""
    ranking_text = []
    ranking_text.append(f"{category_name}中古機相場TOP5")
    
    # テーブル行（trタグ）をすべて取得
    rows = page.locator("table tr").all()
    
    count = 0
    for row in rows:
        # ランキングの数字（1〜5）が入っている行を探す
        cells = row.locator("td").all_inner_texts()
        if len(cells) >= 6:
            rank_str = cells[0].strip()
            if rank_str in ["1", "2", "3", "4", "5"]:
                machine_name = cells[2].strip()
                price = cells[3].strip()
                change_val = cells[5].strip()
                
                # 変動額の表記をルール通りに変換
                if change_val == "0":
                    change_text = "±0円"
                elif change_val.startswith("-"):
                    change_text = f"🔵 {change_val}円"
                else:
                    change_text = f"🔴 +{change_val}円"
                
                # 価格の表記を整える
                if price == "-":
                    price_text = "価格データなし"
                else:
                    price_text = f"約{price}万円"
                
                ranking_text.append(f" {rank_str}位 {machine_name}：{price_text}（前週比 {change_text}）")
                count += 1
                
        if count >= 5:
            break
            
    if count == 0:
        return f"{category_name}中古機相場TOP5\n （データが取得できませんでした）"
        
    return "\n".join(ranking_text)

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

        # 2. パチンコ相場データ抽出とスクショ撮影
        p_path = "screenshots/pachinko_ranking.png"
        print("パチンコ相場ランキングを抽出中...")
        page.goto("http://www.p-souba.com/krank_1.htm", wait_until="domcontentloaded")
        time.sleep(3)
        pachinko_text = extract_ranking_data(page, "パチンコ")
        page.screenshot(path=p_path, full_page=True)

        # 3. パチスロ相場データ抽出とスクショ撮影
        s_path = "screenshots/pachislot_ranking.png"
        print("パチスロ相場ランキングを抽出中...")
        page.goto("http://www.p-souba.com/krank_2.htm", wait_until="domcontentloaded")
        time.sleep(3)
        pachislot_text = extract_ranking_data(page, "パチスロ")
        page.screenshot(path=s_path, full_page=True)

        browser.close()

    # 4. レポート作成（Gemini APIを使わず直接テキストを保存）
    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')

    full_report = f"【{now_str}】\n\n{pachinko_text}\n\n{pachislot_text}\n"

    with open("latest_report.txt", "w", encoding="utf-8") as f:
        f.write(full_report)
    print("レポート生成完了（latest_report.txt に保存しました）")

if __name__ == "__main__":
    run()

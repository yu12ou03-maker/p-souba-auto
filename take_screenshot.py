import os
import time
from playwright.sync_api import sync_playwright

def run():
    # 画像の保存フォルダを作成
    os.makedirs("screenshots", exist_ok=True)

    with sync_playwright() as p:
        # クラウド上のブラウザを起動
        browser = p.chromium.launch(headless=True)
        # 上位ランキングがしっかり収まる画面サイズを設定
        page = browser.new_page(viewport={"width": 1280, "height": 1800})

        # 1. パチンコ相場ランキングのスクショ撮影
        print("パチンコ相場ランキングを撮影中...")
        page.goto("https://www.p-souba.com/ranking_p.php", wait_until="networkidle")
        time.sleep(2)
        page.screenshot(path="screenshots/pachinko_ranking.png")

        # 2. パチスロ相場ランキングのスクショ撮影
        print("パチスロ相場ランキングを撮影中...")
        page.goto("https://www.p-souba.com/ranking_s.php", wait_until="networkidle")
        time.sleep(2)
        page.screenshot(path="screenshots/pachislot_ranking.png")

        browser.close()
        print("スクショの撮影・保存が完了しました。")

if __name__ == "__main__":
    run()

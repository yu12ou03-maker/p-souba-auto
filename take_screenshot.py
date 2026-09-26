import os
import time
from playwright.sync_api import sync_playwright

def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")

    if not username or not password:
        raise ValueError("ログイン情報（ユーザー名/パスワード）が設定されていません。")

    os.makedirs("screenshots", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1800}
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        # 1. トップページへアクセスしてログイン（http接続）
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

        # 2. パチンコ相場ランキングのスクショ撮影（http接続）
        print("パチンコ相場ランキングを撮影中...")
        page.goto("http://www.p-souba.com/ranking_p.php", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path="screenshots/pachinko_ranking.png")

        # 3. パチスロ相場ランキングのスクショ撮影（http接続）
        print("パチスロ相場ランキングを撮影中...")
        page.goto("http://www.p-souba.com/ranking_s.php", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path="screenshots/pachislot_ranking.png")

        browser.close()
        print("ログインおよびスクショ撮影が完了しました。")

if __name__ == "__main__":
    run()

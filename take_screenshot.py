import os
import json
import base64
import time
import urllib.request
from playwright.sync_api import sync_playwright

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

def send_to_drive(image_path, filename):
    """撮影した画像をGoogleドライブへ送信する"""
    print(f"{filename} をGoogleドライブへ転送中...")
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    payload = json.dumps({"filename": filename, "base64": img_b64}).encode("utf-8")
    req = urllib.request.Request(
        GAS_URL,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"転送完了: {resp.read().decode('utf-8')}")
    except Exception as e:
        print(f"転送エラー: {e}")

def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")

    if not username or not password:
        raise ValueError("中古機相場のログイン情報が設定されていません。")

    os.makedirs("screenshots", exist_ok=True)
    pachinko_img = "screenshots/pachinko_ranking.png"
    pachislot_img = "screenshots/pachislot_ranking.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 10000}
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        # 1. ログイン
        print("ログイン中...")
        page.goto("http://www.p-souba.com/index.php", wait_until="domcontentloaded")
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
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # 2. パチンコ相場撮影 & ドライブ送信
        print("パチンコ相場を撮影中...")
        page.goto("http://www.p-souba.com/krank_1.htm", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path=pachinko_img, full_page=True)
        send_to_drive(pachinko_img, "pachinko_ranking.png")

        # 3. パチスロ相場撮影 & ドライブ送信
        print("パチスロ相場を撮影中...")
        page.goto("http://www.p-souba.com/krank_2.htm", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path=pachislot_img, full_page=True)
        send_to_drive(pachislot_img, "pachislot_ranking.png")

        browser.close()

    print("すべての処理が完了しました。")

if __name__ == "__main__":
    run()

import os
import time
import urllib.request
import google.generativeai as genai
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from google.generativeai.types import HarmCategory, HarmBlockThreshold

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

def setup_gemini(api_key):
    genai.configure(api_key=api_key)
    # お客様ご契約の3.6を指定
    return genai.GenerativeModel('gemini-3.6-flash')

def analyze_image_with_gemini(model, image_path, category_name):
    print(f"{category_name}の画像をAIで解析中...")
    
    from PIL import Image
    try:
        img = Image.open(image_path)
    except Exception as e:
        return f"■ {category_name}相場\n（画像読み込みエラー: {e}）"

    # AIへの指示：特定の機種を探すのではなく、全部をそのまま書き出させる
    prompt = f"""
あなたはデータ入力の専門家です。
添付された中古機相場の表画像に写っている【すべての機種データ】を、一切省略せずに1位から順番に全て書き出してください。
途中で「...」などで省略することは絶対に許可しません。写っている全件を出力してください。

【出力フォーマット】
（以下のタブ区切り形式で出力してください）
[順位]位\t[機種名]\t[平均価格]\t[前日差額]
"""

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    try:
        response = model.generate_content(
            [prompt, img],
            safety_settings=safety_settings,
            generation_config={"temperature": 0.0}
        )
        return f"■ {category_name}相場 (全取得データ)\n" + response.text.strip()
    except Exception as e:
        print(f"Gemini APIエラー: {e}")
        return f"■ {category_name}相場\n（AI解析エラーが発生しました。詳細: {e}）"

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

def capture_table(page, url, output_path):
    page.goto(url)
    time.sleep(4)
    
    target_locator = None
    if page.locator('table', has_text='平均価格').count() > 0:
        target_locator = page.locator('table', has_text='平均価格').first
    else:
        for f in page.frames:
            if f.locator('table', has_text='平均価格').count() > 0:
                target_locator = f.locator('table', has_text='平均価格').first
                break
                
    if target_locator:
        target_locator.screenshot(path=output_path)
    else:
        page.screenshot(path=output_path, full_page=True)

def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not username or not password or not gemini_key:
        raise ValueError("環境変数が設定されていません。")

    os.makedirs("screenshots", exist_ok=True)
    model = setup_gemini(gemini_key)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            viewport={"width": 1920, "height": 1080}
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

        print("パチンコ相場を撮影中...")
        capture_table(page, "http://www.p-souba.com/krank_1.htm", "screenshots/pachinko.png")

        print("パチスロ相場を撮影中...")
        capture_table(page, "http://www.p-souba.com/krank_2.htm", "screenshots/slot.png")

        browser.close()

    # パチンコ解析
    pachinko_report = analyze_image_with_gemini(model, "screenshots/pachinko.png", "パチンコ")
    
    # APIの連続呼び出し制限（429エラー）を回避するため30秒待機
    print("API制限回避のため30秒待機中...")
    time.sleep(30)
    
    # パチスロ解析
    slot_report = analyze_image_with_gemini(model, "screenshots/slot.png", "パチスロ")

    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    full_report = f"【{now_str}】\n\n{pachinko_report}\n\n========================\n\n{slot_report}\n"

    print("レポートをGoogleドライブへ送信中...")
    send_to_drive(full_report)
    print("完了しました。")

if __name__ == "__main__":
    run()

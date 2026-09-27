import os
import time
import urllib.request
import google.generativeai as genai
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from google.generativeai.types import HarmCategory, HarmBlockThreshold

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

# ==========================================
# 【注視機種の設定】
# ==========================================
TARGET_PACHINKO = ["牙狼12"]
TARGET_SLOT = ["ソードアート"]
# ==========================================

def setup_gemini(api_key):
    genai.configure(api_key=api_key)
    # 【最重要修正】廃止された「1.5」ではなく、現在稼働している最新モデル「gemini-2.5-flash」を指定します
    return genai.GenerativeModel('gemini-2.5-flash')

def analyze_image_with_gemini(model, image_path, category_name, target_keywords):
    print(f"{category_name}の画像をAIで解析中...")
    
    from PIL import Image
    try:
        img = Image.open(image_path)
    except Exception as e:
        return f"■ {category_name}相場\n（画像読み込みエラー: {e}）"

    keywords_str = "、".join(target_keywords)

    prompt = f"""
あなたは中古機相場表の画像解析エキスパートです。
添付された表の画像から、正確な「機種名」「平均価格」「前日差額」を読み取ってください。

【抽出ルール】
1. 相場 上位3位（ランキング1位〜3位）
2. 注視機種（対象: {keywords_str}）※見つからなければ「見つかりませんでした」
3. 前日比 急上昇TOP3（プラスの中で額が大きい順）
4. 前日比 急降下TOP3（マイナスの中で額が大きい順）

【出力フォーマット】
【相場 上位3位】
 1位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 2位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 3位 [機種名]：[平均価格]（前日比 [変動記号と額]）

【注視機種相場】
 ・[機種名]：[平均価格]（前日比 [変動記号と額]）

【前日比 急上昇TOP3】
 1位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 2位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 3位 [機種名]：[平均価格]（前日比 [変動記号と額]）

【前日比 急降下TOP3】
 1位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 2位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 3位 [機種名]：[平均価格]（前日比 [変動記号と額]）
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
        return f"■ {category_name}相場\n" + response.text.strip()
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

    pachinko_report = analyze_image_with_gemini(model, "screenshots/pachinko.png", "パチンコ", TARGET_PACHINKO)
    time.sleep(3)
    slot_report = analyze_image_with_gemini(model, "screenshots/slot.png", "パチスロ", TARGET_SLOT)

    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    full_report = f"【{now_str}】\n\n{pachinko_report}\n\n========================\n\n{slot_report}\n"

    print("レポートをGoogleドライブへ送信中...")
    send_to_drive(full_report)
    print("完了しました。")

if __name__ == "__main__":
    run()

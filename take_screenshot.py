import os
import time
import urllib.request
import google.generativeai as genai
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

GAS_URL = "https://script.google.com/macros/s/AKfycbw0wiiyJpbwjVX0I1UcwXd_I55xvlCRnkNdmKagIrVApi1V-ygCbvossbYpajmqNXkX/exec"

# ==========================================
# 【注視機種の設定】
# ==========================================
TARGET_PACHINKO = [
    "牙狼12",
]
TARGET_SLOT = [
    "ソードアート",
]
# ==========================================

def setup_gemini(api_key):
    genai.configure(api_key=api_key)
    # 文字認識に強い最新のFlashモデルを使用
    return genai.GenerativeModel('gemini-1.5-flash-latest')

def analyze_images_with_gemini(model, image_paths, category_name, target_keywords):
    """複数枚の分割スクショをGeminiに渡し、テキストを抽出する"""
    print(f"{category_name}の画像をAIで解析中...")
    
    # 画像ファイルの読み込み
    image_parts = []
    from PIL import Image
    for path in image_paths:
        img = Image.open(path)
        image_parts.append(img)
        
    keywords_str = "、".join(target_keywords)

    prompt = f"""
あなたはパチンコ・スロットの中古機相場表の画像解析エキスパートです。
添付された{len(image_parts)}枚の画像（表の上部と下部）を繋げて読み取り、正確な数字と機種名を抽出してください。
「出品台数（稼働週など）」の小さな数字ではなく、表内の「平均価格（最も大きな金額）」を読み取ってください。

【抽出ルール】
1. 相場 上位3位（ランキング1位〜3位）
   - 機種名、平均価格、前日差額を抜き出してください。

2. 注視機種（対象: {keywords_str}）
   - 画像内から探し、機種名、平均価格、前日差額を抜き出してください。見つからなければ「見つかりませんでした」と記載。

3. 前日比 急上昇TOP3
   - 前日差額がプラスの機種のうち、上昇額が大きい上位3機種。

4. 前日比 急降下TOP3
   - 前日差額がマイナスの機種のうち、下落額が大きい上位3機種。

【出力フォーマット】
■ {category_name}相場
【相場 上位3位】
 1位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 2位 [機種名]：[平均価格]（前日比 [変動記号と額]）
 3位 [機種名]：[平均価格]（前日比 [変動記号と額]）

【注視機種相場】
 ・[機種名]：[平均価格]（前日比 [変動記号と額]）

【前日比 急上昇TOP3】
 1位 [機種名]：[平均価格]（前日比 [変動記号と額]）

【前日比 急降下TOP3】
 1位 [機種名]：[平均価格]（前日比 [変動記号と額]）
"""

    contents = [prompt] + image_parts
    
    try:
        response = model.generate_content(contents, generation_config={"temperature": 0.0})
        return response.text.strip()
    except Exception as e:
        print(f"Gemini APIエラー: {e}")
        return f"■ {category_name}相場\n（AI解析エラーが発生しました）"


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
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not username or not password or not gemini_key:
        raise ValueError("環境変数（ログイン情報またはAPIキー）が設定されていません。")

    os.makedirs("screenshots", exist_ok=True)
    model = setup_gemini(gemini_key)

    with sync_playwright() as p:
        # 解像度を高めにする
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            viewport={"width": 1400, "height": 900} 
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

        # パチンコ撮影（分割）
        print("パチンコ相場を撮影中...")
        page.goto("http://www.p-souba.com/krank_1.htm")
        time.sleep(3)
        page.screenshot(path="screenshots/pachinko_1.png") # 上部
        page.mouse.wheel(0, 800) # スクロール
        time.sleep(1)
        page.screenshot(path="screenshots/pachinko_2.png") # 下部

        # パチスロ撮影（分割）
        print("パチスロ相場を撮影中...")
        page.goto("http://www.p-souba.com/krank_2.htm")
        time.sleep(3)
        page.screenshot(path="screenshots/slot_1.png")
        page.mouse.wheel(0, 800)
        time.sleep(1)
        page.screenshot(path="screenshots/slot_2.png")

        browser.close()

    # 画像をGeminiに渡してテキスト化
    pachinko_imgs = ["screenshots/pachinko_1.png", "screenshots/pachinko_2.png"]
    pachinko_report = analyze_images_with_gemini(model, pachinko_imgs, "パチンコ", TARGET_PACHINKO)

    time.sleep(3) # API制限対策
    
    slot_imgs = ["screenshots/slot_1.png", "screenshots/slot_2.png"]
    slot_report = analyze_images_with_gemini(model, slot_imgs, "パチスロ", TARGET_SLOT)

    # レポート結合と送信
    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    full_report = f"【{now_str}】\n\n{pachinko_report}\n\n========================\n\n{slot_report}\n"

    print("レポートをGoogleドライブへ送信中...")
    send_to_drive(full_report)
    print("完了しました。")

if __name__ == "__main__":
    run()

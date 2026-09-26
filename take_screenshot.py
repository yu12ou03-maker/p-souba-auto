import os
import time
import base64
import json
import urllib.request
from playwright.sync_api import sync_playwright

def analyze_image_with_gemini(image_path, category_name, api_key):
    """撮影したスクショをGeminiに読ませて指定フォーマットのテキストを生成する"""
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    prompt = f"""
この画像はパチンコ・パチスロの中古機相場ランキングのスクリーンショットです。
以下の【出力ルール】を厳格に守り、【{category_name}中古機相場TOP5】のテキストを作成してください。

【出力ルール】
1. 1位から5位までの機種を抽出すること。
2. 変動額の表記ルール：
   - プラス（値上がり）の場合は「🔴 +〇〇円」
   - マイナス（値下がり）の場合は「🔵 -〇〇円」
   - 変動なしの場合は「±0円」
3. レイアウト・インデント：
   - タイトルの次の行から、行頭に全角スペース（ ）を1つ入れて各順位を記載すること。
   - 余計な解説、情報元URL、「jpg」などの画像ファイル名、前置きやまとめの挨拶は一切出力しないこと。

【出力フォーマット例】
{category_name}中古機相場TOP5
 1位 機種名：約〇〇万円（前週比 🔴 +〇〇円）
 2位 機種名：約〇〇万円（前週比 🔵 -〇〇円）
 3位 機種名：約〇〇万円（前週比 🔴 +〇〇円）
 4位 機種名：約〇〇万円（前週比 🔵 -〇〇円）
 5位 機種名：約〇〇万円（前週比 ±0円）
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": image_data
                    }
                }
            ]
        }]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req) as res:
            result = json.loads(res.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini解析エラー ({category_name}): {e}")
        return f"{category_name}中古機相場TOP5\n（取得エラーが発生しました）"


def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if not username or not password:
        raise ValueError("中古機相場のログイン情報が設定されていません。")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。")

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

        # 2. パチンコ相場スクショ撮影
        p_path = "screenshots/pachinko_ranking.png"
        print("パチンコ相場ランキングを撮影中...")
        page.goto("http://www.p-souba.com/krank_1.htm", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path=p_path, full_page=True)

        # 3. パチスロ相場スクショ撮影
        s_path = "screenshots/pachislot_ranking.png"
        print("パチスロ相場ランキングを撮影中...")
        page.goto("http://www.p-souba.com/krank_2.htm", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path=s_path, full_page=True)

        browser.close()

    # 4. Geminiによる自動解析・テキスト作成
    print("Geminiによる相場データ自動作成中...")
    pachinko_text = analyze_image_with_gemini(p_path, "パチンコ", gemini_key)
    pachislot_text = analyze_image_with_gemini(s_path, "パチスロ", gemini_key)

    full_report = f"{pachinko_text}\n\n{pachislot_text}\n"

    # レポートファイルとして保存
    with open("latest_report.txt", "w", encoding="utf-8") as f:
        f.write(full_report)

    print("レポート生成完了（latest_report.txt に保存しました）")

if __name__ == "__main__":
    run()

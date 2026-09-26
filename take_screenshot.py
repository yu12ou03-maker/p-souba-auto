import os
import json
import base64
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ==========================================
# 【注視機種の設定】（毎月ここを書き換えてください）
# ==========================================
TARGET_PACHINKO = "牙狼12"
TARGET_SLOT = "ソードアート"
# ==========================================

def call_gemini_vision(api_key, image_path, category_name, target_keyword):
    """Gemini 1.5 Flashにスクリーンショットを渡し、視覚的にデータを抽出する"""
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = f"""
あなたはパチンコ・スロットの中古機相場表の画像解析エキスパートです。
添付された画像（中古機相場のランキング表）から、正確な数字と機種名を読み取ってください。
※平均価格は表の「平均価格」列にある金額（例：302,203円）を目視で正確に読み取ってください。

【抽出ルール】
1. 注視機種（キーワード: 「{target_keyword}」）
   - 表内から「{target_keyword}」に該当する機種を探し、その機種名、平均価格、前日差額（前日比）を抜き出してください。
   - 前日差額がプラスの場合は「🔴 +〇〇円」、マイナスの場合は「🔵 -〇〇円」、変動なしは「±0円」と記載してください。
   - 見つからない場合は「（該当機種がランキング内に見つかりませんでした）」としてください。

2. 前日比 急上昇TOP3
   - 前日差額がプラスになっている機種のうち、上昇額が大きい上位3機種を抜き出してください。
   - なければ「（値上がり機種なし）」としてください。

3. 前日比 急降下TOP3
   - 前日差額がマイナスになっている機種のうち、下落額が大きい上位3機種を抜き出してください。
   - なければ「（値下がり機種なし）」としてください。

【出力フォーマット】以下の形式のみを出力してください（余計な挨拶やコードブロックは不要です）：
■ {category_name}
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

    # ここを 1.5-flash に変更し、確実に動作させる
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": image_b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"■ {category_name}\n（AI解析エラー: {e}）"


def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")
    # 万が一見えない改行や空白が入っていても `.strip()` で綺麗に取り除く安全設計
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not username or not password:
        raise ValueError("中古機相場のログイン情報が設定されていません。")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。GitHubのSecretsを確認してください。")

    os.makedirs("screenshots", exist_ok=True)
    pachinko_img = "screenshots/pachinko_ranking.png"
    pachislot_img = "screenshots/pachislot_ranking.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 表の全体が広く写るように高さを大きめに確保
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 2000}
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

        # 2. パチンコ相場撮影
        print("パチンコ相場を撮影中...")
        page.goto("http://www.p-souba.com/krank_1.htm", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path=pachinko_img, full_page=False)

        # 3. パチスロ相場撮影
        print("パチスロ相場を撮影中...")
        page.goto("http://www.p-souba.com/krank_2.htm", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path=pachislot_img, full_page=False)

        browser.close()

    # 4. Geminiによる画像解析
    print("Geminiによる相場画像解析を実行中...")
    pachinko_report = call_gemini_vision(gemini_key, pachinko_img, "パチンコ", TARGET_PACHINKO)
    pachislot_report = call_gemini_vision(gemini_key, pachislot_img, "パチスロ", TARGET_SLOT)

    # 5. レポート書き出し
    jst = timezone(timedelta(hours=+9), 'JST')
    now_str = datetime.now(jst).strftime('%Y/%m/%d %H:%M 更新')
    full_report = f"【{now_str}】\n\n{pachinko_report}\n\n{pachislot_report}\n"

    with open("latest_report.txt", "w", encoding="utf-8") as f:
        f.write(full_report)

    print("レポート生成完了（latest_report.txt に保存しました）")


if __name__ == "__main__":
    run()

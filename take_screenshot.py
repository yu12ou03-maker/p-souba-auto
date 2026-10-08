import os
import time
import urllib.request
import google.generativeai as genai

from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from google.generativeai.types import HarmCategory, HarmBlockThreshold


# ==========================================
# 設定
# ==========================================

# ★ここには現在使用しているGAS_URLをそのまま入れてください
GAS_URL = "https://script.google.com/macros/s/AKfycbx_6T-pyI7s7Ft5dMS843_G33U7jEZrBZub88CFtKa9c7o78yzWvIaTSzuMDf7hEyZa/exec"


# ==========================================
# Gemini設定
# ==========================================

def setup_gemini(api_key):
    genai.configure(api_key=api_key)

    return genai.GenerativeModel(
        "gemini-3.6-flash"
    )


# ==========================================
# パチンコ＋パチスロを1回で解析
# ==========================================

def analyze_both_images_with_gemini(
    model,
    pachinko_path,
    slot_path
):
    print(
        "パチンコ・パチスロの画像を"
        "まとめてAIで解析中..."
    )

    from PIL import Image

    try:
        pachinko_img = Image.open(pachinko_path)
        slot_img = Image.open(slot_path)

    except Exception as e:
        print("画像読み込みエラー:", e)

        return (
            "AI解析エラー\n"
            f"画像読み込みに失敗しました: {e}"
        )

    prompt = """
あなたはパチンコ・パチスロ中古機相場データの専門家です。

添付画像は2枚あります。

1枚目：
パチンコ中古機相場

2枚目：
パチスロ中古機相場

それぞれの画像に写っている
「すべての機種データ」を読み取ってください。

1位から順番に、
画像に写っている最後の順位まで
一切省略せず出力してください。

途中を「...」などで
省略することは禁止です。

数字を推測しないでください。
画像で確認できない文字や数字は
「判読不能」と記載してください。

パチンコとパチスロを
必ず分けて出力してください。

【出力形式】

■ パチンコ相場 (全取得データ)

[順位] [機種名] [平均価格] [前日差額]


========================


■ パチスロ相場 (全取得データ)

[順位] [機種名] [平均価格] [前日差額]

"""

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT:
            HarmBlockThreshold.BLOCK_NONE,

        HarmCategory.HARM_CATEGORY_HATE_SPEECH:
            HarmBlockThreshold.BLOCK_NONE,

        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT:
            HarmBlockThreshold.BLOCK_NONE,

        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT:
            HarmBlockThreshold.BLOCK_NONE,
    }

    try:
        response = model.generate_content(
            [
                prompt,
                pachinko_img,
                slot_img
            ],
            safety_settings=safety_settings,
            generation_config={
                "temperature": 0.0
            }
        )

        return response.text.strip()

    except Exception as e:
        print(
            "Gemini APIエラー:",
            e
        )

        return (
            "AI解析エラーが発生しました。\n"
            f"詳細: {e}"
        )


# ==========================================
# Google Driveへ送信
# ==========================================

def send_to_drive(report_text):

    req = urllib.request.Request(
        GAS_URL,
        data=report_text.encode("utf-8"),
        headers={
            "Content-Type":
                "text/plain; charset=utf-8"
        }
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=60
        ) as resp:

            result = (
                resp
                .read()
                .decode("utf-8")
            )

            print(
                "Googleドライブ送信完了:",
                result
            )

            if not result.startswith("OK"):
                raise RuntimeError(
                    "Google Drive側で"
                    "エラーが発生しました: "
                    + result
                )

    except Exception as e:
        print(
            "ドライブ送信エラー:",
            e
        )

        raise


# ==========================================
# 相場表スクリーンショット
# ==========================================

def capture_table(page, url, output_path):

    page.goto(
        url,
        wait_until="networkidle",
        timeout=60000
    )

    # 表が完全に表示されるまで待つ
    time.sleep(5)

    print("相場ページ全体を撮影します...")

    page.screenshot(
        path=output_path,
        full_page=True
    )

# ==========================================
# メイン処理
# ==========================================

def run():

    username = os.environ.get(
        "P_SOUBA_USER"
    )

    password = os.environ.get(
        "P_SOUBA_PASS"
    )

    gemini_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if (
        not username
        or not password
        or not gemini_key
    ):

        raise ValueError(
            "必要な環境変数が"
            "設定されていません。"
        )

    os.makedirs(
        "screenshots",
        exist_ok=True
    )

    model = setup_gemini(
        gemini_key
    )

    # ======================================
    # 中古機相場.comへログイン
    # ======================================

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(

            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "Chrome/120.0.0.0"
            ),

            viewport={
                "width": 1920,
                "height": 1080
            }
        )

        page = context.new_page()

        print("ログイン中...")

        page.goto(
            "http://www.p-souba.com/index.php",
            wait_until="domcontentloaded",
            timeout=60000
        )

        time.sleep(3)

        pass_input = page.locator(
            'input[type="password"]'
        ).first

        form = pass_input.locator(
            "xpath=./ancestor::form"
        )

        form.locator(
            'input[type="text"]'
        ).first.fill(
            username
        )

        pass_input.fill(
            password
        )

        time.sleep(1)

        submit_btn = form.locator(
            'input[type="submit"], '
            'input[type="image"], '
            'button'
        )

        if submit_btn.count() > 0:

            submit_btn.first.click()

        else:

            pass_input.press(
                "Enter"
            )

        time.sleep(3)

        # ==================================
        # パチンコ撮影
        # ==================================

        print(
            "パチンコ相場を撮影中..."
        )

        capture_table(
            page,
            "http://www.p-souba.com/crank_1.htm",
            "screenshots/pachinko.png"
        )

        # ==================================
        # パチスロ撮影
        # ==================================

        print(
            "パチスロ相場を撮影中..."
        )

        capture_table(
            page,
            "http://www.p-souba.com/crank_2.htm",
            "screenshots/slot.png"
        )

        browser.close()

    # ======================================
    # Gemini解析
    # ★API呼び出しはここで1回だけ
    # ======================================

    report = analyze_both_images_with_gemini(
        model,
        "screenshots/pachinko_ranking.png",
        "screenshots/pachislot_ranking.png"
    )
    if (
        not report
        or "AI解析エラー" in report
        or "Deadline expired" in report
        or "504" in report
    ):
        raise RuntimeError(
            "AI解析に失敗したため、Google Driveへの保存を中止しました"
        )
    # ======================================
    # 日時追加
    # ======================================

    jst = timezone(
        timedelta(hours=9),
        "JST"
    )

    now_str = datetime.now(
        jst
    ).strftime(
        "%Y/%m/%d %H:%M 更新"
    )

    full_report = (
        f"【{now_str}】\n\n"
        f"{report}\n"
    )

    # ======================================
    # Google Driveへ送信
    # ======================================

    print(
        "レポートをGoogleドライブへ送信中..."
    )

    send_to_drive(
        full_report
    )

    print(
        "完了しました。"
    )


if __name__ == "__main__":
    run()

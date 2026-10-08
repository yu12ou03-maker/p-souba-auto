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

それぞれの画像に実際に表示されている機種データだけを読み取ってください。

【最重要：誤認識防止】
・画像に存在しない機種名を絶対に追加しない。
・知識や過去の機種名から推測・補完しない。
・機種名を一文字でも確実に判読できない場合は「判読不能」と記載する。
・価格や前日差額を推測して埋めない。
・順位と機種名と数値は、必ず同じ行から読み取る。
・読めない項目は「判読不能」とし、架空の情報を作らない。
・画像に確認できた順位だけを、上から順番に出力する。
・パチンコとパチスロは必ず分ける。

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
        print("Gemini APIへの送信を開始します（アプリ側の呼び出し：1回）", flush=True)

        response = model.generate_content(
            [
                prompt,
                pachinko_img,
                slot_img
            ],
            safety_settings=safety_settings,
            generation_config={
                "temperature": 0.0
            },
            request_options={
                "retry": None,
                "timeout": 120
            }
        )

        report_text = response.text.strip()
        if not report_text:
            raise RuntimeError("Geminiの応答が空です")

        print("Gemini APIの解析が完了しました", flush=True)
        return report_text

    except Exception as e:
        print(
            f"Gemini API解析失敗: {type(e).__name__}: {e}",
            flush=True
        )
        raise RuntimeError(
            "Gemini API解析失敗。Google Driveへの保存を中止します"
        ) from e

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

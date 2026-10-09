import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from playwright.sync_api import sync_playwright
from PIL import Image

GAS_URL = os.environ.get(
    "GAS_URL",
    "https://script.google.com/macros/s/AKfycbx_6T-pyI7s7Ft5dMS843_G33U7jEZrBZub88CFtKa9c7o78yzWvIaTSzuMDf7hEyZa/exec",
)
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def setup_gemini(api_key):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL_NAME)


def analyze_both_images_with_gemini(model, pachinko_path, slot_path):
    print("パチンコ・パチスロ画像をGeminiで解析中...", flush=True)
    prompt = """あなたはパチンコ・パチスロ中古機相場データの専門家です。
添付画像は1枚目がパチンコ中古機相場、2枚目がパチスロ中古機相場です。
画像に実際に表示されている機種データだけを読み取ってください。
【最重要】
・画像に存在しない機種名、順位、価格、前日差額を追加しない。
・知識や過去の機種名から推測・補完しない。
・機種名や数値が読めない場合は「判読不能」と記載する。
・順位、機種名、平均価格、前日差額は必ず同じ行から読む。
・確認できた順位だけを画像の順に出力し、パチンコとパチスロを分ける。
【出力形式】
■ パチンコ相場 (全取得データ)
[順位] [機種名] [平均価格] [前日差額]

========================

■ パチスロ相場 (全取得データ)
[順位] [機種名] [平均価格] [前日差額]
"""
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    with Image.open(pachinko_path) as src:
        pachinko_img = src.convert("RGB")
    with Image.open(slot_path) as src:
        slot_img = src.convert("RGB")

    for attempt in range(1, 4):
        try:
            print(f"Gemini API解析 {attempt}/3 回目", flush=True)
            response = model.generate_content(
                [prompt, pachinko_img, slot_img],
                safety_settings=safety_settings,
                generation_config={"temperature": 0.0},
                request_options={"timeout": 120},
            )
            report = response.text.strip()
            if not report:
                raise RuntimeError("Geminiの応答が空です")
            return report
        except Exception as exc:
            message = str(exc)
            print(f"Gemini解析エラー: {type(exc).__name__}: {message}", flush=True)
            if any(code in message.lower() for code in (
                "429", "resource_exhausted", "quota", "permission_denied", "403", "401",
                "api key", "invalid model", "not found", "404",
            )):
                raise RuntimeError("Geminiの利用制限・設定エラー。Driveへの保存を中止します") from exc
            if attempt == 3:
                raise RuntimeError("Gemini解析が3回失敗。Driveへの保存を中止します") from exc
            time.sleep(15 * attempt)
    raise RuntimeError("Gemini解析に失敗しました")


def validate_report(report):
    if not report or any(term in report.lower() for term in (
        "ai解析エラー", "deadline expired", "resource_exhausted",
        "quota exceeded", "internal server error", "traceback", "504",
    )):
        raise RuntimeError("解析結果がエラー内容のためDriveへの保存を中止します")
    if "■ パチンコ相場" not in report or "■ パチスロ相場" not in report:
        raise RuntimeError("パチンコ・パチスロ両方の相場表がありません。保存中止")
    p, s = report.split("■ パチスロ相場", 1)
    if not any(line.strip()[:1].isdigit() for line in p.splitlines()):
        raise RuntimeError("パチンコの順位データがありません。保存中止")
    if not any(line.strip()[:1].isdigit() for line in s.splitlines()):
        raise RuntimeError("パチスロの順位データがありません。保存中止")


def send_to_drive(report_text):
    if not GAS_URL.startswith("https://script.google.com/macros/s/"):
        raise RuntimeError("GAS_URLが正しくありません")
    req = urllib.request.Request(
        GAS_URL,
        data=report_text.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = resp.read().decode("utf-8")
        print("Google Drive送信応答:", result[:500], flush=True)
        if not result.startswith("OK"):
            raise RuntimeError("Google Drive側でエラー: " + result[:500])


def capture_table(page, url, output_path):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    if page.locator('input[type="password"]').count() > 0:
        raise RuntimeError(f"ログイン画面が表示されたままです: {url}")
    page.screenshot(path=output_path, full_page=True)
    if os.path.getsize(output_path) < 10_000:
        raise RuntimeError(f"画像ファイルが小さすぎます: {output_path}")
    print(f"撮影完了: {output_path}", flush=True)


def run():
    username = os.environ.get("P_SOUBA_USER")
    password = os.environ.get("P_SOUBA_PASS")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not all((username, password, gemini_key)):
        raise ValueError("P_SOUBA_USER、P_SOUBA_PASS、GEMINI_API_KEYが必要です")

    os.makedirs("screenshots", exist_ok=True)
    model = setup_gemini(gemini_key)
    pachinko_path = "screenshots/pachinko.png"
    slot_path = "screenshots/slot.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            print("ログイン中...", flush=True)
            page.goto("http://www.p-souba.com/index.php", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            pass_input = page.locator('input[type="password"]').first
            form = pass_input.locator("xpath=./ancestor::form")
            form.locator('input[type="text"]').first.fill(username)
            pass_input.fill(password)
            submit_btn = form.locator('input[type="submit"], input[type="image"], button')
            if submit_btn.count() > 0:
                submit_btn.first.click()
            else:
                pass_input.press("Enter")
            page.wait_for_timeout(3000)
            capture_table(page, "http://www.p-souba.com/crank_1.htm", pachinko_path)
            capture_table(page, "http://www.p-souba.com/crank_2.htm", slot_path)
        finally:
            browser.close()

    report = analyze_both_images_with_gemini(model, pachinko_path, slot_path)
    validate_report(report)
    jst = timezone(timedelta(hours=9), "JST")
    now_str = datetime.now(jst).strftime("%Y/%m/%d %H:%M 更新")
    full_report = f"【{now_str}】\n\n{report}\n"
    print("検証済みの解析結果をGoogle Driveへ送信中...", flush=True)
    send_to_drive(full_report)
    print("完了しました。", flush=True)


if __name__ == "__main__":
    run()

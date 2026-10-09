"""p-souba.com 最新相場取得 → Gemini解析 → GASへ正常時のみ送信。"""
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import google.generativeai as genai
from PIL import Image, ImageStat, ImageEnhance
from playwright.sync_api import sync_playwright

GAS_URL = os.getenv(
    "GAS_URL",
    "https://script.google.com/macros/s/AKfycbx_6T-pyI7s7Ft5dMS843_G33U7jEZrBZub88CFtKa9c7o78yzWvIaTSzuMDf7hEyZa/exec",
)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
SCREENSHOT_DIR = Path("screenshots")
DIAG_DIR = Path("diagnostics")

PROMPT = """あなたは中古遊技機相場表の画像読み取り担当です。
画像1枚目はパチンコ、2枚目はパチスロの最新ランキング表です。
表示されている行だけを読み、順位・機種名・平均価格・前日差額を同じ行から転記してください。
判読不能は「判読不能」とし、推測・補完・架空の機種名や数値を絶対に書かないでください。
必ず次の2つの見出しをそのまま出力してください。
■ パチンコ相場 (全取得データ)
[順位] [機種名] [平均価格] [前日差額]
（画像から読めたデータ行をここに記載）
■ パチスロ相場 (全取得データ)
[順位] [機種名] [平均価格] [前日差額]
（画像から読めたデータ行をここに記載）
読み取れる順位行が無い場合は、その区分に「判読不能」と記載してください。
画像以外の情報は使用しないでください。"""


def check_image(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 5_000:
        raise RuntimeError(f"画像が存在しない、または小さすぎます: {path}")
    with Image.open(path) as image:
        image.load()
        print(f"画像確認: {path} / {image.width}x{image.height} / {path.stat().st_size} bytes", flush=True)
        if image.width < 700 or image.height < 400:
            raise RuntimeError(f"画像サイズが小さすぎます: {path}")
        sample = image.convert("L")
        sample.thumbnail((500, 500))
        if ImageStat.Stat(sample).stddev[0] < 5:
            raise RuntimeError(f"画像がほぼ単色です: {path}")


def capture_table(page, url: str, output: Path) -> None:
    response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    if response is None or response.status >= 400:
        raise RuntimeError(f"相場ページを取得できません: {url} / HTTP {getattr(response, 'status', 'unknown')}")
    page.wait_for_timeout(5_000)
    if page.locator('input[type="password"]').count() > 0:
        raise RuntimeError(f"ログイン画面が表示されています: {url}")
    title = page.title()
    body_text = page.locator("body").inner_text(timeout=10_000)
    print(f"撮影ページ: {url} / title={title!r} / 本文文字数={len(body_text)}", flush=True)
    if len(body_text.strip()) < 50:
        raise RuntimeError(f"相場ページの本文が短すぎます: {url}")
    # 現在のページを撮影。表が iframe に入っている場合も診断できるよう記録。
    frames = page.frames
    print(f"フレーム数: {len(frames)}", flush=True)
    for index, frame in enumerate(frames[:10]):
        try:
            text = frame.locator("body").inner_text(timeout=3000)
            print(f"frame[{index}]: url={frame.url[:180]} / 文字数={len(text)} / 冒頭={text[:180]!r}", flush=True)
        except Exception as exc:
            print(f"frame[{index}] 確認不可: {type(exc).__name__}", flush=True)
    print(f"表要素数: {page.locator('table').count()} / 画像要素数: {page.locator('img').count()}", flush=True)
    page.screenshot(path=str(output), full_page=True)
    check_image(output)
    print(f"撮影完了: {output}", flush=True)


def analyze_images(pachinko_path: Path, slot_path: Path) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(MODEL_NAME)
    for attempt in range(1, 4):
        try:
            print(f"Gemini API解析 {attempt}/3 回目", flush=True)
            with Image.open(pachinko_path) as p, Image.open(slot_path) as s:
                response = model.generate_content(
                    [PROMPT, p.copy(), s.copy()],
                    generation_config={"temperature": 0.0},
                    request_options={"timeout": 120},
                )
            report = (response.text or "").strip()
            print("===== Gemini解析結果（診断用・最大5000文字） =====", flush=True)
            print(report[:5000], flush=True)
            print("===== 解析結果ここまで =====", flush=True)
            if not report:
                raise RuntimeError("Gemini応答が空です")
            return report
        except Exception as exc:
            detail = str(exc)
            print(f"Gemini失敗 {attempt}/3: {type(exc).__name__}: {detail[:500]}", flush=True)
            if any(x in detail.lower() for x in ("429", "resource_exhausted", "quota", "rate limit")):
                raise RuntimeError("Geminiの利用上限です。再試行・Drive保存を中止します") from exc
            if attempt == 3:
                raise RuntimeError("Gemini解析に3回失敗しました。Drive保存を中止します") from exc
            time.sleep(15 * attempt)
    raise RuntimeError("解析失敗")


def validate_report(report: str) -> None:
    if any(x in report.lower() for x in ("ai解析エラー", "deadline expired", "resource_exhausted", "traceback")):
        raise RuntimeError("Gemini解析結果にエラー文があります。保存中止")
    # 見出しの空白・表記揺れは許容。両区分に実際の順位行が必要。
    pachinko = re.search(r"パチンコ相場", report)
    slot = re.search(r"パチスロ相場", report)
    if not pachinko or not slot or slot.start() <= pachinko.start():
        raise RuntimeError("パチンコ・パチスロ両方の見出しを確認できません。保存中止")
    sections = (report[pachinko.end():slot.start()], report[slot.end():])
    for label, section in zip(("パチンコ", "パチスロ"), sections):
        rows = [line.strip() for line in section.splitlines() if line.strip()]
        rows = [line for line in rows if not ("順位" in line and "機種名" in line)]
        # 順位は 1 / 1位 / [1] / １ 等を許容。単なる説明文は採用しない。
        ranking = [line for line in rows if re.match(r"^(?:\[\s*)?[0-9０-９]{1,3}(?:\s*\]|\s*位|[.．、\s　|｜:：-])", line)]
        if not ranking:
            raise RuntimeError(f"{label}の順位データがありません。保存中止")
        print(f"{label}: 順位行 {len(ranking)} 件を検出", flush=True)


def send_to_drive(text: str) -> None:
    if not GAS_URL.startswith("https://script.google.com/macros/s/"):
        raise RuntimeError("GAS_URLの設定が不正です")
    req = urllib.request.Request(
        GAS_URL,
        data=text.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        result = response.read().decode("utf-8", errors="replace").strip()
    print(f"GAS応答: {result[:300]}", flush=True)
    if not result.startswith("OK"):
        raise RuntimeError(f"GAS保存が確認できません: {result[:300]}")


def run() -> None:
    for key in ("P_SOUBA_USER", "P_SOUBA_PASS", "GEMINI_API_KEY"):
        if not os.getenv(key):
            raise RuntimeError(f"GitHub Secretsの {key} が未設定です")
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    pachinko = SCREENSHOT_DIR / "pachinko.png"
    slot = SCREENSHOT_DIR / "slot.png"
    # 前回実行の画像は使用しない。
    for path in (pachinko, slot):
        path.unlink(missing_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            print("ログイン中...", flush=True)
            page.goto("http://www.p-souba.com/index.php", wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3_000)
            password = page.locator('input[type="password"]').first
            form = password.locator("xpath=./ancestor::form")
            form.locator('input[type="text"]').first.fill(os.environ["P_SOUBA_USER"])
            password.fill(os.environ["P_SOUBA_PASS"])
            submit = form.locator('input[type="submit"], input[type="image"], button')
            if submit.count():
                submit.first.click()
            else:
                password.press("Enter")
            page.wait_for_timeout(3_000)
            capture_table(page, "http://www.p-souba.com/crank_1.htm", pachinko)
            capture_table(page, "http://www.p-souba.com/crank_2.htm", slot)
        finally:
            browser.close()

    try:
        report = analyze_images(pachinko, slot)
        validate_report(report)
    except Exception:
        # エラー時だけ、今回撮影した画像を診断用に一時配置。
        # GitHub Actions の artifact に保存する設定をした場合のみダウンロード可能。
        DIAG_DIR.mkdir(exist_ok=True)
        import shutil
        for source in (pachinko, slot):
            if source.exists():
                shutil.copy2(source, DIAG_DIR / source.name)
        print("診断画像を diagnostics/ に用意しました。Driveには送信しません。", flush=True)
        raise
    timestamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d %H:%M 更新")
    full_report = f"【{timestamp}】\n\n{report}\n"
    print("検証成功。Google Driveへ最新データを送信します", flush=True)
    send_to_drive(full_report)
    print("正常終了しました", flush=True)


if __name__ == "__main__":
    run()

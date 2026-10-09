"""中古機相場.com ランキング撮影 → Gemini解析 → 正常時のみGASへ送信。"""
import os
import re
import shutil
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import google.generativeai as genai
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright

BASE = "https://www.p-souba.com/"
PACHINKO_URL = urljoin(BASE, "modules/newbb9/kakaku_ranking.php?forum_id=1?mode=krank")
GAS_URL = os.getenv("GAS_URL", "https://script.google.com/macros/s/AKfycbx_6T-pyI7s7Ft5dMS843_G33U7jEZrBZub88CFtKa9c7o78yzWvIaTSzuMDf7hEyZa/exec")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
SCREENSHOT_DIR = Path("screenshots")
DIAG_DIR = Path("diagnostics")
PROMPT = """画像1はパチンコ価格ランキング、画像2はパチスロ価格ランキングです。
画像内で実際に表示されている行のみから、順位・機種名・平均価格・前日差額を転記してください。
推測・補完は禁止です。見えない値は判読不能と記載してください。
出力形式：
■ パチンコ相場 (全取得データ)
[順位] [機種名] [平均価格] [前日差額]
1位 機種名 123,456円 +1,234円
■ パチスロ相場 (全取得データ)
[順位] [機種名] [平均価格] [前日差額]
1位 機種名 123,456円 -1,234円
例の数値を出力してはいけません。画像以外の情報は使用しないでください。"""


def check_image(path):
    if not path.is_file() or path.stat().st_size < 5000:
        raise RuntimeError(f"画像が存在しないか小さすぎます: {path}")
    with Image.open(path) as image:
        image.load()
        print(f"画像確認: {path} / {image.width}x{image.height} / {path.stat().st_size} bytes", flush=True)
        if image.width < 700 or image.height < 400:
            raise RuntimeError(f"画像サイズが小さすぎます: {path}")
        sample = image.convert("L")
        sample.thumbnail((500, 500))
        if ImageStat.Stat(sample).stddev[0] < 5:
            raise RuntimeError(f"画像がほぼ単色です: {path}")


def diagnostic_copy():
    DIAG_DIR.mkdir(exist_ok=True)
    for name in ("pachinko.png", "slot.png"):
        src = SCREENSHOT_DIR / name
        if src.exists():
            shutil.copy2(src, DIAG_DIR / name)
    print("失敗時の診断画像を diagnostics/ に保存しました。Driveには送信しません。", flush=True)


def open_ranking(page):
    response = page.goto(PACHINKO_URL, wait_until="domcontentloaded", timeout=60000)
    if response is None or response.status >= 400:
        raise RuntimeError(f"ランキングページのHTTPエラー: {getattr(response, 'status', 'unknown')}")
    page.wait_for_timeout(3500)
    print(f"ランキングURL: {page.url}", flush=True)
    print(f"ページ見出し: {page.locator('body').inner_text(timeout=10000)[:350]!r}", flush=True)
    if page.locator('input[type="password"]').count():
        raise RuntimeError("ランキング画面がログイン画面に戻っています")


def ranking_ready(page, label):
    # ページが描画済みかを、ランキング特有の文字列と実データ行で確認する。
    body = page.locator("body").inner_text(timeout=15000)
    print(f"{label}: URL={page.url} / 本文文字数={len(body)} / table={page.locator('table').count()}", flush=True)
    if "価格ランキング" not in body or "平均価格" not in body or "前日差額" not in body:
        raise RuntimeError(f"{label}: 価格ランキング表の見出しが見つかりません")
    # 1位などの順位表示と円表記の存在を確認する。
    if not re.search(r"(?:^|\s)[1１]\s*位", body) or not re.search(r"[\d,，]+\s*円", body):
        raise RuntimeError(f"{label}: ランキングの実データが表示されていません")
    return body


def capture(page, label, output):
    page.wait_for_timeout(1500)
    ranking_ready(page, label)
    # 縦長のランキング全体を撮影。大きすぎる画像はGeminiで縮小されるため、
    # 画像が非常に長い場合は先頭部分に限定して読み取り品質を優先する。
    page.screenshot(path=str(output), full_page=True, animations="disabled")
    check_image(output)
    print(f"{label}: 撮影完了 {output}", flush=True)


def find_slot_link(page):
    # 実際のランキング画面のリンクを使う。forum_idを推測して固定しない。
    candidates = page.locator('a:has-text("スロット価格ランキング"), a:has-text("スロット価格ランキングＴＯＰ"), a:has-text("スロット価格ランキングTOP")')
    for i in range(candidates.count()):
        href = candidates.nth(i).get_attribute("href")
        if href and "kakaku_ranking" in href:
            return urljoin(page.url, href)
    # 表上部の「スロット」リンクから探す。
    for anchor in page.locator("a").all():
        try:
            text = anchor.inner_text(timeout=1000).strip()
            href = anchor.get_attribute("href") or ""
            if "スロット" in text and "kakaku_ranking" in href:
                return urljoin(page.url, href)
        except Exception:
            continue
    raise RuntimeError("スロット価格ランキングへのリンクが見つかりません。推測URLでは撮影しません")


def analyze_images(pachinko, slot):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(MODEL_NAME)
    for attempt in range(1, 4):
        try:
            print(f"Gemini解析 {attempt}/3", flush=True)
            with Image.open(pachinko) as p, Image.open(slot) as s:
                response = model.generate_content(
                    [PROMPT, p.copy(), s.copy()],
                    generation_config={"temperature": 0},
                    request_options={"timeout": 120},
                )
            result = (response.text or "").strip()
            print(f"Gemini応答（冒頭3000字）:\n{result[:3000]}", flush=True)
            if not result:
                raise RuntimeError("Geminiの応答が空です")
            return result
        except Exception as exc:
            detail = str(exc).lower()
            print(f"Gemini失敗: {type(exc).__name__}: {str(exc)[:400]}", flush=True)
            if any(term in detail for term in ("429", "resource_exhausted", "quota", "rate limit")):
                raise RuntimeError("Gemini利用上限のため保存中止") from exc
            if attempt == 3:
                raise
            time.sleep(attempt * 15)
    raise RuntimeError("Gemini解析失敗")


def validate_report(report):
    if any(term in report.lower() for term in ("ai解析エラー", "deadline expired", "resource_exhausted", "traceback")):
        raise RuntimeError("Gemini結果にエラー文があります")
    p = re.search("パチンコ相場", report)
    s = re.search("パチスロ相場", report)
    if not p or not s or s.start() <= p.start():
        raise RuntimeError("両方の相場見出しが揃っていません")
    for label, section in (("パチンコ", report[p.end():s.start()]), ("パチスロ", report[s.end():])):
        lines = [x.strip() for x in section.splitlines()]
        valid = [x for x in lines if re.match(r"^(?:\[\s*)?[0-9０-９]{1,3}(?:\s*\]|\s*位|[.．、\s　|｜:：-])", x) and re.search(r"\d[\d,，]*\s*円", x)]
        if not valid:
            raise RuntimeError(f"{label}の順位・価格データがありません。保存中止")
        print(f"{label}: 順位・価格行 {len(valid)} 件", flush=True)


def send_to_drive(text):
    if not GAS_URL.startswith("https://script.google.com/macros/s/"):
        raise RuntimeError("GAS_URLが不正です")
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
        raise RuntimeError(f"GAS保存未確認: {result[:300]}")


def run():
    for key in ("P_SOUBA_USER", "P_SOUBA_PASS", "GEMINI_API_KEY"):
        if not os.getenv(key):
            raise RuntimeError(f"GitHub Secrets未設定: {key}")
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    for name in ("pachinko.png", "slot.png"):
        (SCREENSHOT_DIR / name).unlink(missing_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
                page = context.new_page()
                print("ログイン画面へ移動", flush=True)
                page.goto(urljoin(BASE, "index.php"), wait_until="domcontentloaded", timeout=60000)
                password = page.locator('input[type="password"]').first
                form = password.locator("xpath=./ancestor::form")
                form.locator('input[type="text"]').first.fill(os.environ["P_SOUBA_USER"])
                password.fill(os.environ["P_SOUBA_PASS"])
                submit = form.locator('input[type="submit"], input[type="image"], button')
                if submit.count():
                    submit.first.click()
                else:
                    password.press("Enter")
                page.wait_for_timeout(2500)
                open_ranking(page)
                capture(page, "パチンコ", SCREENSHOT_DIR / "pachinko.png")
                slot_url = find_slot_link(page)
                print(f"スロットランキングURL: {slot_url}", flush=True)
                response = page.goto(slot_url, wait_until="domcontentloaded", timeout=60000)
                if response is None or response.status >= 400:
                    raise RuntimeError("スロットランキングページの取得に失敗")
                capture(page, "パチスロ", SCREENSHOT_DIR / "slot.png")
            finally:
                browser.close()
        report = analyze_images(SCREENSHOT_DIR / "pachinko.png", SCREENSHOT_DIR / "slot.png")
        validate_report(report)
        timestamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d %H:%M 更新")
        send_to_drive(f"【{timestamp}】\n\n{report}\n")
        print("正常終了", flush=True)
    except Exception:
        diagnostic_copy()
        raise


if __name__ == "__main__":
    run()

name: 毎朝スクショ自動撮影

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:

jobs:
  take-screenshot:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: リポジトリをチェックアウト
        uses: actions/checkout@v4

      - name: Pythonのセットアップ
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 必要なライブラリのインストール
        run: |
          pip install playwright beautifulsoup4
          playwright install --with-deps chromium

      - name: スクリーンショット撮影とレポート生成を実行
        env:
          P_SOUBA_USER: ${{ secrets.P_SOUBA_USER }}
          P_SOUBA_PASS: ${{ secrets.P_SOUBA_PASS }}
        run: |
          python take_screenshot.py

      - name: 成果物を保存してコミット
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add .
          git diff --quiet && git diff --staged --quiet || (git commit -m "毎朝のスクショとレポート自動更新" && git push)

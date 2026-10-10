# 中古機相場：ローカルOCRでランキングを取得

毎朝9時JST（UTC 00:00）のGitHub Actionsで、パチンコ・パチスロ各100件を検証後、既存GASへ送信します。修復ブランチはまだmainへ反映していません。

## 取得方法

ログイン後、`krank_1.htm`・`krank_2.htm`の順位・機種名・前日差額をDOMから取得します。平均価格はサイトのJavaScriptが挿入する数字画像なので、表示完了を待ち、既に表示されている画像をCanvasで連結してローカルのTesseractで文字認識します。画像のファイル名から価格を推測しません。追加の画像AIサービスを呼ばず、Gemini APIキー・日次枠は不要です。

価格は拡大グレースケール画像と拡大二値化画像の2通りを異なる分割モードで読み、両方の信頼度60以上、数字画像数と認識桁数の一致、金額の一致を要求します。全区分各100件の順位・件数・機種名・価格・符号を検証します。空・読めない・低信頼度・不一致・取得失敗ではGASへ送信しません。同じOCRによる共通の誤読の可能性は残るため、実サイトの画像と検証済みレポートの照合が必要です。

## 実行

必要なGitHub Secretsは`P_SOUBA_USER`と`P_SOUBA_PASS`です。`GAS_URL`は任意で、未設定なら元のURLを使用します。

```sh
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
python -m pip install -r requirements.txt
python -m playwright install --with-deps chromium
python -m unittest discover -s tests -v
python take_screenshot.py --capture-only
python take_screenshot.py --dry-run
# 正常データを送信する通常実行
python take_screenshot.py
```

修復ブランチのpushはローカルOCRのdry-runで、Drive更新なしです。手動Actionsはcapture_only=trueが既定で撮影だけを行います。capture_only=false、dry_run=trueでローカルOCRまで検証します。定期実行は正常検証後だけ送信します。Geminiコードは比較用に残っていますが、通常実行・Actionsでは使いません。明示的な`--engine gemini`のみAPIキーが必要です。

サイトのHTTPログインはユーザーが明示的に許可済みです。HTTPでは認証情報は暗号化されません。Gemini・GASのTLS検証は維持し、サイトへの認証情報を他サイトへの遷移で送信しません。403/429の制限を回避しません。

ページの一時的な失敗は最大3回再試行します。OCRの失敗は推測で補完せず停止します。GASのPOSTは結果不明なタイムアウトでも再送しません。`OK`応答のみ送信確認とします。GAS側のコードはこのリポジトリにないため、Driveの実ファイルの更新とサーバー側の検証は別途確認が必要です。

診断はランキング表・価格画像・安全なエラー情報だけを保存し、Cookie・ログインHTML・認証情報を記録しません。アーティファクト保持期間は3日間です。定期実行はGitHubの混雑等で遅れる場合があります。

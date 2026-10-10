# 中古機相場：数字画像の完全一致照合でランキングを取得

毎朝9時JST（UTC 00:00）のGitHub Actionsで、パチンコ・パチスロ各100件を検証後、既存GASへ送信します。毎朝の通常処理はGeminiを使用しません。

## 取得方法

ログイン後、`krank_1.htm`・`krank_2.htm`の順位・機種名・前日差額をDOMから取得します。平均価格はサイトのJavaScriptが挿入する数字画像なので、表示完了を待ち、既に表示されている画像をCanvasで連結して確認済みの0〜9の字形辞書と照合します。画像のファイル名から価格を推測しません。追加の画像AIサービスを呼ばず、Gemini APIキー・日次枠は不要です。

価格画像を閾値160・180の2通りで二値化し、各数字が対応する字形辞書に完全一致すること、数字画像数と認識桁数の一致、金額の一致を要求します。未知の字形・画像の変更・ノイズは近似で補わず停止します。全区分各100件の順位・件数・機種名・価格・符号を検証します。空・読めない・不一致・取得失敗ではGASへ送信しません。辞書は実サイトの価格画像を目視確認して作成しました。サイトの数字画像が変わった場合は、辞書を再確認する必要があります。汎用Tesseractの比較用テストも残していますが、通常の金額判定には使いません。

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

修復ブランチのpushは数字画像照合のdry-runで、Drive更新なしです。手動Actionsはcapture_only=trueが既定で撮影だけを行います。capture_only=false、dry_run=trueで数字画像照合まで検証します。定期実行は正常検証後だけ送信します。Geminiコードは比較用に残っていますが、通常実行・Actionsでは使いません。明示的な`--engine gemini`のみAPIキーが必要です。

サイトのHTTPログインはユーザーが明示的に許可済みです。HTTPでは認証情報は暗号化されません。Gemini・GASのTLS検証は維持し、サイトへの認証情報を他サイトへの遷移で送信しません。403/429の制限を回避しません。

ページの一時的な失敗は最大3回再試行します。OCRの失敗は推測で補完せず停止します。GASのPOSTは結果不明なタイムアウトでも再送しません。`OK`応答のみ送信確認とします。GAS側のコードはこのリポジトリにないため、Driveの実ファイルの更新とサーバー側の検証は別途確認が必要です。

診断はランキング表・価格画像・安全なエラー情報だけを保存し、Cookie・ログインHTML・認証情報を記録しません。アーティファクト保持期間は3日間です。定期実行はGitHubの混雑等で遅れる場合があります。

字形辞書は2026年10月10日の診断画像（パチンコ1〜4位と11位の平均価格）から、目視確認した数字を登録しています。価格のファイル名を復号したり、サイトの制限を回避したりしません。

2026年10月10日の実サイト検証ではパチンコ100件・パチスロ100件をGemini呼び出し0回で取得しました。テスト39件が成功し、通常実行でGASのOK応答を確認しました。Driveの実ファイル内容と次回の定期実行はまだ直接確認していません。

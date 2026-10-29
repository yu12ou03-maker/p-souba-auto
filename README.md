# 中古機相場：通常・臨時サイトの手動切替

設定は `site_config.json` の `site_mode` 1か所です。自動切替はありません。

| 設定 | 取得先・解析方法 |
|---|---|
| `temporary` | `https://sub.p-souba.com/pachinko/ranking` と `/slot/ranking`。Playwrightで撮影し、Geminiで金額を各画像1回解析 |
| `normal` | 従来の通常サイト `krank_1.htm`・`krank_2.htm`。既存の数字画像完全一致照合処理 |

復旧時は `site_mode` を `normal` に戻すだけです。通常サイト用コード・字形辞書・Gemini解析コードを維持しています。

## 50位ずつ撮影・通常4回の解析

各ランキングの1〜50位と51〜100位を別画像にします。パチンコ2枚・スロット2枚、計4枚の金額画像をGeminiへ各1回送るため、通常の画像解析は合計4リクエストです。2回読み取りの照合は行いません。モデル一覧取得は別です。画像は各1回のみ送信し、HTTPエラー・タイムアウト・不正応答でも再送やモデル切替をせず停止します。

順位・機種名はDOMから取得してGeminiの結果と照合します。平均価格・前日差額は撮影画像から取得し、整数・金額範囲・順位連続性・機種名重複・各区分100件を検証します。判読不能・欠落・不正値は推測で補わず送信を停止します。1回解析のため、独立した読み直しによる金額の一致確認はありません。

臨時サイトの基準日はページの「M/D時点」をそのまま記録し、年は補完しません。機種名付き画像と金額用画像の両方を診断アーティファクトに保存します。

## 実行・保存

必要なGitHub Secretsは `P_SOUBA_USER`・`P_SOUBA_PASS`、Gemini使用時は `GEMINI_API_KEY` です。`GAS_URL` は任意で、未設定なら既存URLを使用します。

```sh
python -m pip install -r requirements.txt
python -m playwright install --with-deps chromium
python -m unittest discover -s tests -v
python take_screenshot.py --capture-only
python take_screenshot.py --dry-run
python take_screenshot.py
```

毎朝9時JSTの定期実行と、正常検証後の既存GAS経由Google Drive保存を維持します。通常モードの既定はローカル画像照合、臨時モードの既定はGeminiです。通常モードでも `--engine gemini` で明示的にGeminiを選択できます。

ブランチへのpushは全テスト後に実サイトの撮影のみを検証し、Gemini・Driveには送信しません。手動Actionsは `capture_only=true` が既定です。実APIの画像解析を検証するときは `capture_only=false / dry_run=true`、保存する場合は両方falseです。

## エラー・診断

429では制限名・上限値・再試行待ち時間を許可リストで取り出し、停止します。429や認証エラーをモデル切替で回避しません。503・その他HTTPエラー・タイムアウトでも追加送信はありません。最大4回の画像解析で停止します。

GASへのPOSTは結果不明でも再送せず、OK応答だけを保存確認とします。GAS側コードはこのリポジトリにないため、Driveの実ファイル更新は別途確認が必要です。

Cookie・ログインHTML・APIキー・生のエラー本文は記録しません。診断アーティファクトの保持期間は3日です。通常サイトの既存HTTPログインと、Gemini・GASのTLS検証を維持します。

## 2026/10/29 復旧調査

mainの直近定期実行（40633830051）は通常サイトの転送先検証で停止。PR #2は未統合で、mainに臨時サイト設定がありません。10/29 09:58 JST時点の取得履歴には10/29の定期実行はありません。

10/28 23:18:07 JSTのPR実行（40700273903）は無料枠の日次20リクエスト上限で429。応答のretry_delayは60113秒で、再試行可能時刻の目安は10/29 16:00 JSTです。上限解除の保証や残量表示ではありません。追加課金・課金設定変更は行いません。

Driveのlatest_report.txtは実読込で10/21 09:31更新のままと確認。200件の実解析検証が完了するまではmain統合・保存を実施しません。

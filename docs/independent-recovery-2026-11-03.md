# 11月3日起動復旧：本番反映の承認対象

## 原因の切り分け
- 11/3 12:23のmain手動実行41571910097：12:24:38に100+100件検証、12:24:40にGAS OK。Gemini要求0。Drive ID 1P6z_-199FTeLissxpK6ZREnf7C8MfQik は12:24更新を直接読み戻し済み。
- 11/3朝のschedule実行履歴は取得時点でなし。11/2 schedule作成05:01:32Z=14:01:32 JST、11/1は05:00:08Z=14:00:08 JST。run作成と開始は同時刻であり、観測できる遅延はrunner実行処理以前にある。GitHub内部の配信遅延・欠落の具体的原因はログがなく未特定。
- mainのPR #4はe80afc510f34625163d7e54ccbed7cca3adfac50でマージ済み。cron5回とも同じGitHub schedule基盤。公式資料もscheduleの遅延・欠落の可能性を記載しており、起動回数増加のみでは独立対策にならない。
- 既存guardはscheduleのみ対象。手動/外部dispatchと同一run再試行が二重送信の対象外となる不備を確認。

## 差分と影響
1. schedule_guard.py：scheduleとworkflow_dispatchの全試行の実際の取得step日時を照合。同一runの以前のattemptも照合。取得開始以降は失敗・cancel・POST不明でも当日再取得・再送しない。履歴API失敗は停止。main以外の本番取得を拒否。dry-run/capture-only dispatchも保守的に当日の開始扱い（自動的に再取得しない）。
2. workflow：concurrencyをリポジトリ共通souba-productionに統一。cron5回、Secrets、権限、OCR、GAS送信は維持。pushは起動安全テストだけにし、相場の実取得/送信を行わない。schedule/dispatchの取得処理は既存を使用。
3. independent-trigger/：**既存収集GASとは別の新規GAS**。5分間隔のGoogle時計トリガーでJST8:55〜9:30だけ監視。GitHubから取得開始を確認できなければmainへcapture_only=false/dry_run=falseのworkflow_dispatchを1回。送信前に日次予約を保存し、タイムアウト等で結果不明でも自動再送しない。GitHubのscheduleに依存しないが、GitHub APIとActions runnerは共通依存であり定刻保証ではない。
4. GASはレビュー済みmainのguard/workflow blob SHAを照合し、不一致なら起動しない。将来この2ファイルを変更する場合はGASのSHA更新も承認が必要。停止保護の一部。
5. 新規GASだけでPropertiesとトリガーを追加。既存GAS・既存トリガー・Sheets・X・Driveの設定は変更しない。Driveの書込みは従来のGAS送信だけ。

## 承認が必要な本番操作
- 本PRをmainへマージ。反映直前に旧コードのqueued/in_progress/waiting runがないことを再確認する。旧concurrencyのrunがあれば反映を停止し、勝手にキャンセルしない。
- 新規独立GASを作成・ソース配置・5分時計トリガーを登録しSOUBA_ENABLED=trueを設定。
- 専用fine-grained GitHub tokenを対象リポジトリ1件、Actions read/write（Metadata readは付随）だけで作成し、新規GASのSOUBA_GITHUB_TOKENに保存。トークンをチャット/ソース/ログに表示しない。既存GitHub Appの権限は拡大しない。
- 新規GASのOAuthはexternal_requestとscript.scriptappだけ。Drive/Sheets/メール権限なし。課金サービス契約なし。
- 本日の取得成功を新guardで照合してから、独立経路による起動を1回検証。取得stepがskip、GAS送信なし、Drive更新日時不変を確認。POST不明の予約は勝手に消さない。

## 実施済みと残件
- Python安全テスト5件、GASロジックのモック9シナリオ成功。外部ネットワーク/相場取得/送信なし。
- 本日の200件、GAS OK、Drive読戻しは既存成功runを利用。取得プログラムの再試験なし。
- 9:45タスクの現promptは当日100+100件のDrive読取りと⑤掲載、未取得時継続を設定済み。本日9:45は取得前のため⑤未取得。将来9:45の実反映はまだ実証していない。
- **独立GAS設置、権限承認、本番マージ、独立起動の実通信、翌朝9:45の実反映は未完了**。コード作成/モック成功だけで復旧完了とはしない。

公式資料：
- https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
- https://developers.google.com/apps-script/guides/triggers/installable

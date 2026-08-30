# Server Change Notice

notice_id: 20260830-RECIPESEARCHAPI-001

app: recipe-search

source_branch: main

source_commit: 未確定

impact_level: L1

status: ready_for_review

created_by: Codex

## 変更概要

recipe-search のアプリログと uvicorn lifecycle ログを、stderr へ出力する共通ログ規約 v1 の1行 JSON 形式へ統一する。query 文字列を含み得る uvicorn アクセスログと httpx/httpcore の INFO ログは抑止する。

## 変更理由

journald 側が共通方式でログを収集・判定できるよう、必須フィールド、固定イベント名、level 表記を統一し、外部サイト失敗を禁止情報なしで記録するため。

## server_impact判定

server_impact: notify

判定理由: ログ形式と監視候補イベントを変更するため通知対象。アプリ独自ファイルの追加・廃止、収集基盤の変更、大幅なログ量増加はなく、L1 と判断した。

## 現在と変更後

| 項目 | 現在 | 変更後 |
|---|---|---|
| アプリログ形式 | 起動バナーとサイト失敗をプレーンテキストで出力 | 共通ログ規約 v1 の1行 JSON |
| 必須フィールド | なし | `ts` / `app` / `level` / `event` |
| 外部サイト失敗 | 例外メッセージを含むプレーンテキスト | `external_call_failed`、固定サイト識別子、分類、例外クラスのみ |
| uvicorn lifecycle | プレーンテキスト | 同一 JSON フォーマッタ |
| uvicorn access | query 文字列付き URL を含み得る | 無効化 |
| httpx/httpcore INFO | request URL を含み得る | WARNING 未満を抑止 |

## 影響対象

- service/container: recipe-search の既存 systemd service（設定自体は変更しない）
- URL/port/health: 変更なし
- cron/timer/worker: 変更なし
- dependency: 外部レシピサイト、内部 API、Python package の契約変更なし
- data/DB/volume: 変更なし
- log/monitoring: journald へ入るログが1行 JSON になり、`startup` / `shutdown` / `external_call_failed` が監視候補になる

## production変更

- 必要性: 本タスクではなし。production 反映には別途承認済み deploy が必要
- 想定作業: 本タスクでは実施しない。source deploy は既存 blocker により禁止中
- downtime: 本タスクではなし
- maintenance window: 不要

## 利用者への影響

- user_maintenance_impact: none
- 対象利用者・機能: API contract、応答内容、可用性の変更なし
- 通知方法: 利用者向け通知は不要

## env・secret contract

- 変更: なし
- 変数名・secret種類のみ: 追加・削除・変更なし
- provisioning/rotation: 変更なし

secret値は記載しない。

## Data・migration・backup

- schema/format変更: なし
- migration: なし
- backup対象: 変更なし
- restore確認: 本変更では不要
- backward compatibility: API と永続データに変更なし

## Deploy・rollback

- deploy前提: canonical source 確定、VPS管理側 review、production変更の明示承認
- deploy手順の変更: なし。本タスクでは deploy しない
- rollback方法: 将来の承認済み deploy 時は直前の canonical application source へ戻す
- rollback不能条件: なし（data migration・設定変更なし）

## Health・テスト

- health contract変更: なし
- 実施テスト: 固定依存環境での import、実 uvicorn 起動・正常停止、JSON 全行パース、必須フィールド・level・flush、アクセスログと httpx INFO の抑止、モック外部失敗、モックスクレイパーによるルートと主要 POST 応答、port 8002 解放
- 結果: 11ログ行を全件 JSON としてパースし、`startup` / `shutdown` / `external_call_failed` を確認。ルートと `POST /api/recipes/search` は200、停止後に port 8002 の解放を確認した
- 未実施テストと理由: production接続・deploy、外部レシピサイトへの実接続は本タスクで禁止または不要のため実施しない

## Log・監視

- log量/形式/保存先変更: stderr の1行 JSON。実測では1回の起動・正常停止で uvicorn lifecycle 8行とアプリ2行の計10行。サイト失敗は従来の1失敗1行を1 warnへ置換し、アクセスログ停止分は減少するため大幅増加なし
- 新しいalert条件: `external_call_failed` の継続発生、`startup` 後の `shutdown` 欠落を監視候補とする
- secret/個人情報対策: 生のログメッセージ、例外メッセージ、利用者入力、query 文字列付き URL、外部レスポンス本文を出力せず、安全な許可フィールドだけを JSON 化する

## 未解決事項

- VPS管理側で共通ログ collector と監視条件への組み込み時期を確認する。
- source deploy の既存 blocker は本変更と独立して継続する。

## 希望時期

VPS管理側 review 後。production 反映時期は別途承認で決定する。

## Approval

- app owner: 実装 task 承認済み
- VPS management review: 未実施
- production approval: 未承認
- related task_id: 20260830-006

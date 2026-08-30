# Server Change Notice

notice_id: 20260830-RECIPESEARCHAPI-001

app: recipe-search

source_branch: main

source_commit: 5602a24

impact_level: L1

status: applied

created_by: Codex

## 変更概要

recipe-search のアプリログと uvicorn lifecycle ログを、stderr へ出力する共通ログ規約 v1 の1行 JSON 形式へ統一する。query 文字列を含み得る uvicorn アクセスログと httpx/httpcore の INFO ログは抑止する。

**加えて、ログ対応と同一コミットに、以前からローカルにのみ存在し未deployだった `simple_mode`（シンプルレシピ優先モード）機能が含まれる。** 2026-08-30のVPS/Git source照合（`OPS-P1-02`解消）で判明した差分で、ログ対応とは無関係に以前から存在していた未反映機能。deployはapp.py全体の反映のため、このnoticeでは両方を対象として扱う。詳細は「simple_mode機能の影響評価」を参照。

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
| `POST /api/recipes/search` の `simple_mode` パラメータ | 受理するがサーバー実装なし（VPS側は旧source） | 受理して実装どおり処理（詳細ページ取得による並べ替え） |

## simple_mode機能の影響評価（2026-08-30、VPS管理側review時に追加）

- 内容: `simple_mode: true` を指定すると、検索結果の上位60件について詳細ページを並列取得（`asyncio.Semaphore(10)`で同時接続10に制限）し、材料数・手順数・調理時間からシンプルさスコアを算出して並べ替える。追加応答時間は目安5-6秒（アプリ側 `CLAUDE.md` 記載）。
- **フロントエンド（`app/meal-planner-app/src/api/index.ts:56`）は本パラメータを常に `simple_mode: false` で送信しており、UIから有効化する導線（設定・スイッチ等）は存在しない。** 従って本deployによるUI経由の挙動変化・応答時間変化はない。
- 残存リスク: `simple_mode` はAPIパラメータとして外部から指定可能になる。`POST /api/recipes/search` に直接 `simple_mode: true` を送信された場合のみ、上記の詳細ページ取得経路（外部レシピサイトへのアクセス増）が有効化される。8002は `127.0.0.1` bindでHTTPS入口（`recipe-search.homehub-tools.dedyn.io`）経由のみ到達可能なため、無差別な第三者アクセスは想定しにくいが、ゼロではない。
- 対応方針: 現時点では追加の制限（rate limit等）を設けず、オプトインの既存実装のまま反映する。将来UIが有効化する場合は、別途利用者への応答時間増の周知を検討する。

## 影響対象

- service/container: recipe-search の既存 systemd service（設定自体は変更しない）
- URL/port/health: 変更なし
- cron/timer/worker: 変更なし
- dependency: 外部レシピサイト、内部 API、Python package の契約変更なし。**`simple_mode: true` 指定時のみ、詳細ページ取得で外部レシピサイトへのアクセスが増える（上記参照）**
- data/DB/volume: 変更なし
- log/monitoring: journald へ入るログが1行 JSON になり、`startup` / `shutdown` / `external_call_failed` が監視候補になる

## production変更

- 必要性: あり（本通知のreviewと別途承認後のアプリ配置・再起動）
- 想定作業: legacy route（`deploy-recipe-search.bat` → `/opt/apps/deploy.sh recipe-search`）。venv使用ありのため `pip install -r requirements.txt` を実行する
- downtime: `systemctl restart` によるbrief-restart。recipe-generator / coop-api deploy実績では数秒
- maintenance window: 不要（brief-restartのため）

## 利用者への影響

- user_maintenance_impact: none
- 対象利用者・機能: API contract、既定の応答内容・応答時間、可用性に変更なし（`simple_mode`はデフォルト`false`でUIからは常に`false`。上記「simple_mode機能の影響評価」参照）
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

- deploy前提: VPS管理側reviewとproduction変更の明示承認（**canonical source確定は`OPS-P1-02`解消により満たされた。2026-08-30、ローカルGitがcanonicalと確定**）
- deploy手順: legacy route。転送前にVPS側現物（`app.py`）のsha256を取得・保全してから `deploy-recipe-search.bat` 相当（scp転送 → ハッシュ一致確認 → `/opt/apps/deploy.sh recipe-search`）を実行する（recipe-generator / coop-api deployと同じ手順）
- rollback方法: 保全したVPS側現物（`app.py`。simple_mode機能追加前の1301行版）をそのまま `/opt/apps/recipe-search/` へ書き戻し、`sudo systemctl restart recipe-search`
- rollback不能条件: なし（data migrationなし）

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
- `simple_mode`が将来UI側で有効化される場合、応答時間増の利用者周知を別途検討する。
- 監視登録と稼働確認が済むまで受理台帳を `closed` にしない（[監視組み込みフロー](app_onboarding_flow.md) §2.1）。

## Deploy結果（2026-08-30）

- 手順: VPS側現物（`app.py`）のsha256保全 → scp転送（`app.py` / `requirements.txt`） → ハッシュ一致確認 → `/opt/apps/deploy.sh recipe-search` 実行。
- deploy中の `pip install -r requirements.txt` はVPS側venvの既存版と一致のためno-op。
- 検証: health `HTTP 200` / bind `127.0.0.1:8002` 維持 / runtime user `recipe-search` 維持 / journaldで `startup` の1行JSON実出力を確認（`{"ts":"2026-08-30T22:16:17.465+09:00","app":"recipe-search","level":"info","event":"startup"}`）。
- 機能確認: UIと同じ呼び方（`simple_mode:false`）で `POST /api/recipes/search` を実行し、HTTP 200・レシピ取得成功を確認。既定動作に変化なし。
- downtime: `systemctl restart` のみ、事前想定どおり数秒。
- rollback用の現物（deploy前sha256 `b9efcb00...`）はローカルscratchpadに保全済み。

## 希望時期

VPS管理側 review 後。production 反映時期は別途承認で決定する。

## Approval

- app owner: 実装 task 承認済み
- VPS management review: **accepted（2026-08-30）**。受入判定7項目（`application_change_notification_policy.md` §9）を照合し、`source_commit`未確定と「production作業とapp code変更の境界が不明確（`simple_mode`未記載）」の2点を本notice更新で是正、他5項目は充足を確認した。`simple_mode`はUIから常に`false`送信のため実害なしと評価。**`accepted`はdeploy承認ではない。**
- production approval: **承認済み（2026-08-30、ユーザー）**。想定downtime（brief-restart数秒）・事前告知なしの方針、`simple_mode`実害なし評価を含めて承認された
- related task_id: 20260830-006

# Server Change Notice

record_type: server_change

template_type: full

policy_bundle_version: 2026-09-04.1

notice_id: 20260916-RECIPESEARCHAPI-008

app: recipe-search

source_branch: main

source_commit: 未確定（859712fe9a050363cf226fbd1cf86cc76096daf3 を基点とする未コミット変更）

production_baseline_commit: 5602a243759b9542b94e5607d33c819e4ec6c3a0

release_commits: 859712fe9a050363cf226fbd1cf86cc76096daf3、および task 20260916-008 の未コミット差分

impact_level: L2

status: draft

created_by: Codex

production_change: required

vps_management_handoff: required

deployment_status: not_started

## 変更概要

登録済み10サイトを固定キーワードで逐次確認する `canary_check.py` を追加し、`deploy-files.txt` の配布対象へ追加する。実行時はサイトごとの件数・判定・所要時間と、jobの開始・終了を1行JSONで標準エラーへ出力する。

## 変更理由

外部サイトのHTML構造変更によりスクレイパーが例外なしで0件を返す silent failure を能動的に検知できるようにするため。

## server_impact判定

server_impact: notify

判定理由: deploy対象fileとログeventを追加し、将来のproduction配置および監視・定期実行設計に運用reviewが必要なため。現在のservice設定やproduction環境は変更していない。

## 現在と変更後

| 項目 | 現在 | 変更後 |
|---|---|---|
| silent failureの能動確認 | なし | 10サイトを逐次確認する手動実行可能なカナリアを追加 |
| deploy対象 | `app.py`、`requirements.txt` | 上記に `canary_check.py` を追加 |
| カナリアログ | なし | `job_start`、`canary_site_result`、`job_end` を1実行12行出力 |
| 定期実行 | なし | 変更なし（cron/timerは本変更の対象外） |

## 影響対象

- service/container: 既存service設定は変更しない。カナリアは独立スクリプトとして追加する。
- URL/port/health: 変更なし。
- cron/timer/worker: 変更なし。定期実行の追加は別のVPS管理task・承認が必要。
- dependency: 追加なし。既存スクレイパーと既存Python依存を使用する。
- data/DB/volume: 変更なし。
- log/monitoring: カナリア実行1回につき通常12行の構造化ログを追加する。新規eventは `canary_site_result`。実行されない限りログは増えない。

## production変更

- 必要性: あり（将来 `canary_check.py` をVPSへ配置する場合）。本taskでは実施しない。
- 想定作業: source deployは現在BLOCKEDのため未確定。canonical source確定後、VPS管理側で配置範囲と手順を決定する。
- downtime: 未確定。ファイル配置自体はservice再起動を必要としない設計だが、実際のdeploy手順はVPS管理側で確認する。
- maintenance window: 現時点では不要。手順確定時に再判定する。

## 利用者への影響

- user_maintenance_impact: none
- 対象利用者・機能: API contract、既存endpoint、実行中serviceの挙動は変更しない。カナリアは自動実行されない。
- 通知方法: 利用者向け通知は不要。

## env・secret contract

- 変更: なし
- 変数名・secret種類のみ: 追加・削除・変更なし
- provisioning/rotation: 変更なし

## Data・migration・backup

- schema/format変更: なし
- migration: なし
- backup対象: 変更なし
- restore確認: 該当なし
- backward compatibility: API・永続データとも変更なし

## Deploy・rollback

- deploy前提: source deploy blockerの解消、source commitの確定、VPS管理review、production個別承認。
- deploy手順の変更: `deploy-files.txt` の対象へ `canary_check.py` が増える。実手順はsource deploy blocker解消後にVPS管理側で決定する。
- rollback方法: 配置した `canary_check.py` をdeploy artifactから除外する。service設定・data変更はない。
- rollback不能条件: なし。

## Health・テスト

- health contract変更: なし
- 実施テスト: `.venv-codex` のPython 3.12.14で構文compile、`app` import、カナリアimportと10サイト登録確認、全10サイトを偽関数へ差し替えた失敗系・全成功系の主処理検証。
- 結果: 全テスト成功。各サイト1回、0件=`zero`、例外=`error`、1件=`ok`を確認。失敗系は終了コード1・`job_end.status=failure`、全成功系は終了コード0・`job_end.status=success`。各ケース12行を全件JSON parseし、URL、query文字列、例外messageが含まれないことを確認。
- 未実施テストと理由: 外部レシピサイトへの実接続は必須でなく負荷回避のため未実施。production接続・deployは未承認かつ禁止のため未実施。

## Log・監視

- log量/形式/保存先変更: カナリア実行時のみstderrへ1行JSONを12行出力。アプリ独自log fileは作らない。
- 新しいalert条件: `canary_site_result.status` が `zero` または `error`、および `job_end.status=failure`。未実行・異常終了は同一 `run_id` の `job_start` / `job_end` の不一致で判定可能。
- secret/個人情報対策: 固定keyword、site key、件数、status、所要時間のみを出力し、URL、query文字列、例外message、外部response本文を出力しない。

## 提出前セルフチェック

正本: VPS管理repositoryの `docs/templates/server_change_notice_pre_submission_checklist.md`

- [x] production baselineを正本で確認し、baselineから現在HEADまでのcommitを確認した
- [ ] full source commitとremote push（未コミットであり、本taskにcommit・pushの明示指示がない）
- [x] data、secret/auth、network、runtime、dependency、backup、client contractに変更がないことを確認した
- [x] job/log変更のためfull templateとL2を選択した
- [x] cron/timerは追加せず、カナリアが同一 `run_id` の `job_start` / `job_end` を出すことを確認した
- [x] secret、個人情報、URL、query文字列、raw response/errorをログ・差分へ含めないことを確認した
- [x] `deployment_status: not_started`を確認した
- [ ] tracked working tree clean（本taskの未コミット変更があるため未達）

未確認・該当なしの理由: production artifact、deploy前後health、rollback実行手順はsource deploy blocker解消後にVPS管理側で確定する。DB/data、client配信は変更なしのため該当しない。

## 未解決事項

- source commitの確定とremote push。
- source deploy blockerの解消、およびproduction配置手順のVPS管理review・個別承認。
- cron/timerによる定期実行、監視条件、timeout・retry方針は本変更に含めず、別taskとして設計・承認する。

## 希望時期

source deploy blocker解消後。production反映時期はVPS管理側reviewと個別承認で決定する。

## VPS管理チャットへの引き継ぎ

- 引き継ぎ要否: 必要
- ユーザーへの案内: この無人実行経路では未実施
- VPS管理チャットへ渡すpath: `ops/server-change-notices/20260916-RECIPESEARCHAPI-008-summary.md`

## Approval

- app owner: task 20260916-008 のローカル実装を承認済み
- VPS management review: 未実施
- production approval: なし
- related task_id: 20260916-008

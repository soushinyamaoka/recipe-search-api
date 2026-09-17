# Server Change Notice

record_type: server_change

template_type: full

policy_bundle_version: 2026-09-04.1

notice_id: 20260916-RECIPESEARCHAPI-008

app: recipe-search

source_branch: main

source_commit: cf248c4534576f35c685caed604ee05700142e0e

production_baseline_commit: 5602a243759b9542b94e5607d33c819e4ec6c3a0

release_commits: production baseline `5602a24` から deploy対象source `cf248c4` までは次の2commit。`859712fe9a050363cf226fbd1cf86cc76096daf3`（旧notice `20260830-RECIPESEARCHAPI-001` の文書更新のみ。runtime code変更なし）、`cf248c4534576f35c685caed604ee05700142e0e`（本変更の実装。`canary_check.py` 追加・`deploy-files.txt` 追記・本notice追加）。source以降の文書commitとして `ded621ba653e43e95963d651c57fd1831b957346`（`CLAUDE.md` の canonical-source blocker 旧表記の修正のみ）があり、これはdeploy対象sourceに含まれない。

impact_level: L2

status: ready_for_review

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

- 必要性: あり（`canary_check.py` をVPSへ配置する場合）。本taskでは実施しない。
- canonical source: **2026-08-30に解消済み**。read-only照合によりcanonical sourceはローカルGitと確定し（VPS管理側 `OPS-P1-02`）、当時の唯一の差分（`simple_mode`）も同日production反映済みである。本noticeのdeploy対象source `cf248c4` から production baseline `5602a24` までの範囲で、`app.py` と `requirements.txt` に差分はない（既存API runtime codeと依存は変更されない）。したがって「canonical source未確定によるsource deploy blocker」は本変更の前提条件としては存在しない。
- 想定作業: 下記「Deploy・rollback」に2経路を記載する。**どちらの経路もproduction個別承認が必要**であり、本noticeの`accepted`はproduction承認ではない。
- downtime: 推奨経路（単一file配置）では発生しない。既存legacy wrapper経路を選ぶ場合はbrief restartが発生する。詳細は「Deploy・rollback」を参照。
- maintenance window: 推奨経路では不要。legacy wrapper経路を選ぶ場合は再判定する。

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

- deploy前提: source commit `cf248c4` の確定とremote push（本notice最終化で実施）、VPS管理review、production個別承認。

### 既存legacy wrapper経路との差異（重要）

初版noticeは「ファイル配置自体はservice再起動を必要としない」と記載していたが、**既存のshared Windows wrapperをそのまま使う場合、これは成り立たない**。

`deploy-recipe-search.bat` → 共通 `deploy.bat` は、`deploy-files.txt` に記載された**全file**（本変更後は `app.py`・`canary_check.py`・`requirements.txt` の3file）を転送したうえで、VPS上の `/opt/apps/deploy.sh recipe-search` を呼ぶ。同scriptは `pip install` と `recipe-search.service` の再起動を必ず実施する。したがって既存wrapper経由では、無停止の単一file配置にはならない。

### 推奨経路（単一file・無停止・service再起動なし）

1. 固定source commit `cf248c4` と production baseline `5602a24` の間で、`app.py` と `requirements.txt` に差分がないことを再確認する。
2. `canary_check.py` **のみ**を、退避とhash確認付きで一時pathへ転送し、同一filesystem上でatomicに配置する。
3. source/venv、owner/group/mode、service状態、内部health・public healthを、配置の前後で確認する。
4. serviceは**再起動しない**。import確認を行い、手動カナリアの1回実行は**承認範囲に含める場合のみ**実施する。
5. rollback: 追加した `canary_check.py` を除去し、配置前の状態とhealthを確認する。既存fileを書き換えないため、rollback不能条件はない。

### legacy wrapper経路を選ぶ場合

brief restart、3file全転送、依存install、health確認、rollbackを含む**別の実施計画として再評価が必要**である。本noticeは推奨経路を前提に記載している。

### 共通

- どちらの経路も**production個別承認が必要**。
- service設定・永続data・依存の変更はない。`canary_check.py` は追加されるだけで、自動実行はされない。

## Health・テスト

- health contract変更: なし
- 実施テスト: `.venv-codex` のPython 3.12.14で構文compile、`app` import、カナリアimportと10サイト登録確認、全10サイトを偽関数へ差し替えた失敗系・全成功系の主処理検証。**2026-09-17のnotice最終化時に同一手順で再実行し、同結果を確認済み**。
- 結果: 全テスト成功。各サイト1回、0件=`zero`、例外=`error`、1件=`ok`を確認。失敗系は終了コード1・`job_end.status=failure`、全成功系は終了コード0・`job_end.status=success`。各ケース12行を全件JSON parseし、1実行内で`run_id`が一致すること、URL、query文字列、例外messageが含まれないことを確認。
- 未実施テストと理由: 外部レシピサイトへの実接続は必須でなく負荷回避のため未実施。production接続・deployは未承認かつ禁止のため未実施。

## Log・監視

- log量/形式/保存先変更: カナリア実行時のみstderrへ1行JSONを12行出力。アプリ独自log fileは作らない。
- 新しいalert条件: `canary_site_result.status` が `zero` または `error`、および `job_end.status=failure`。未実行・異常終了は同一 `run_id` の `job_start` / `job_end` の不一致で判定可能。
- secret/個人情報対策: 固定keyword、site key、件数、status、所要時間のみを出力し、URL、query文字列、例外message、外部response本文を出力しない。

## 提出前セルフチェック

正本: VPS管理repositoryの `docs/templates/server_change_notice_pre_submission_checklist.md`

- [x] production baselineを正本で確認し、baselineからsource commitまでのcommit列を確認した（`859712f` → `cf248c4`。source以降の文書commit `ded621b` とは区別して記録した）
- [x] full source commitの確定とremote push（source `cf248c4`、notice最終commitとともに `main` へpush済み。force push・履歴改変なし）
- [x] data、secret/auth、network、runtime、dependency、backup、client contractに変更がないことを確認した（baseline..source で `app.py`・`requirements.txt` に差分なし）
- [x] job/log変更のためfull templateとL2を選択した
- [x] cron/timerは追加せず、カナリアが同一 `run_id` の `job_start` / `job_end` を出すことを確認した
- [x] secret、個人情報、URL、query文字列、raw response/errorをログ・差分へ含めないことを確認した
- [x] `deployment_status: not_started`を確認した
- [x] tracked working tree clean

未確認・該当なしの理由: production artifact、deploy前後health、rollback実行手順は、上記「Deploy・rollback」の推奨経路を前提にproduction個別承認時へ確定する。DB/data、client配信は変更なしのため該当しない。

## 未解決事項

- production配置経路の選択（推奨経路 / legacy wrapper経路）と、production個別承認。
- cron/timerによる定期実行、監視条件、timeout・retry方針は本変更に含めず、別taskとして設計・承認する。
- 自動化前に、固定keywordで全10サイト1件以上を必須とする判定が恒常的failureにならないか、制御された初回実行でsite別baselineを取得して閾値を確定する必要がある（VPS管理レビュー §5 の継続事項）。
- `run_id` は実行時刻（`%Y%m%dT%H%M%S%f%z`）由来のため、同一clock tick内に複数回実行すると同じ値になり得る。定期実行の間隔では実用上問題にならないが、未実行検知・突合の設計時に留意する。

## 希望時期

VPS管理側の再レビューで`accepted`となった後、production個別承認を得た時点。時期はVPS管理側で決定する。

## VPS管理チャットへの引き継ぎ

- 引き継ぎ要否: 必要
- ユーザーへの案内: 実施済み（2026-09-16）
- VPS管理チャットへ渡すpath: `ops/server-change-notices/20260916-RECIPESEARCHAPI-008-summary.md`

## Approval

- app owner: task 20260916-008 のローカル実装を承認済み。notice最終化（source commit固定・remote push・`B01`/`B02`反映）も2026-09-17に承認済み
- VPS management review: 2026-09-17に1回目実施、`blocked` 判定（`RECIPESEARCH-008-B01` / `B02`）。本版で両blockerへ対応し再レビューを依頼する。review正本: VPS管理repositoryの `docs/operations/recipe_search_canary_review_20260917.md`
- production approval: なし（production task未割当、production未反映）
- related task_id: 20260916-008

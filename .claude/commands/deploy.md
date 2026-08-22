レシピ検索APIをさくらVPSへデプロイしてください。
サーバー情報は server-config.md を参照すること。

> ## ⛔ 現在 source deploy は BLOCKED（VPS安全化後 production contract）
> - ローカル source と VPS source に**既知の差異**があり、**canonical source 確定前に source deploy を実行しないこと**。**ローカル版で VPS を上書きしない。**
> - 実行前に canonical source の確定状況をユーザーに確認する。
> - あわせて現行 contract を遵守: bind `127.0.0.1:8002` 維持（外部は 22/80/443 のみ・HTTPS入口経由）、runtime user `recipe-search`（systemd を deploy へ戻さない）、`/opt/apps/deploy.sh` は legacy route。

## デプロイ手順

### 1. デプロイ前確認
- `git status` で未コミットの変更がないか確認する
- `git log --oneline -5` で最新のコミット内容を確認する
- deploy-files.txt を読み、デプロイ対象ファイルを把握する

### 2. ローカルで動作確認
- `python app.py` でサーバーを起動し、エラーがないか確認する
- `curl -s http://localhost:8002/` でルートエンドポイントが応答するか確認する
- 確認後、ローカルサーバーを停止する

### 3. デプロイバッチ実行
- 以下のデプロイバッチを実行する。このバッチが deploy-files.txt を読み取り、SCP転送とサービス再起動を一括で行う

```bash
"C:\work\PRG\Sakura\deploy\recipe-api\deploy-recipe-search.bat"
```

### 4. デプロイ後確認
- server-config.md に記載のVPS IPアドレスを使い、APIが応答するか確認する
- ルートエンドポイントとアプリ連携エンドポイントの両方を確認する

### 5. 完了報告
- デプロイ結果（成功/失敗）をユーザーに報告する
- 失敗した場合は server-config.md のログ確認コマンドを参照する

## 注意事項
- ポート8002はWebレシピ検索API専用。同一VPSの他サービスには触れないこと
- デプロイバッチは pause で入力待ちになるため、バッチ実行後は完了を待つこと
- デプロイ前に必ずユーザーの確認を取ること

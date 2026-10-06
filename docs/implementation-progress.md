# MVP実装 進捗

このファイルは実装の再開ポイントです。作業が中断しても、次の回はここを読んで「次にやること」から続けます。
作業ブランチ: `claude/mvp-implementation-tnk3jq`

## マイルストーン

| # | 内容 | 状態 |
|---|---|---|
| M0 | 進捗ファイル・リポジトリ構成・開発環境 | 完了 |
| M1 | サーバー基盤（Flask app factory、DBモデル、エラー形式）と認証（ID/パスワード、token更新・失効、再認証、me、削除、Google、Apple、復旧メール・再設定） | 完了 |
| M2 | trip・context（PostGIS候補・ランキング・cooldown・黙る判定・決定ログ）・history・track・feedback・preferences/interests | 完了 |
| M3 | LLM Adapter（Claude）による選択・語り＋検証・フォールバック、実行時知識生成ワーカー（Wikipedia/Wikidata/OSM）、curated seed、TripMemorySummary | 未着手 |
| M4 | 音声（VoiceProvider、/voices、/guides/{id}/speech、/speech-assets、キャッシュ） | 未着手 |
| M5 | Flutterアプリ（認証・Home・Guide・Map・History・Preferences・Account、GPS・移動推定・ローカル記録/再送、通知、音声） | 未着手 |
| M6 | P1（一時指示commands、temporary state、participants） | 未着手 |

## 次にやること

- M3 を開始する: `server/localvoice/services/llm.py`（現在はスタブで常にNone→ルールへフォールバック）にClaude Adapterを実装し、`knowledge_gen.py`（enqueue_for_position と生成ワーカー）と curated seed を作る。

## 判断した内容

- 通知頻度は quiet/normal/talkative/chatty（cooldown 900/360/180/90秒、1時間上限 3/6/12/20）。値は `services/prefs.py`。
- 「この話はもういい」(enough_topic) は当該カテゴリのboostを終了し、2時間の負のboostを入れる（長期趣向は変えない）。
- 再送・遅着の過去点（最新でない点、または3分より古い点）は履歴保存のみで判定しない（`stale_event`）。

- 作業ブランチが1本に指定されているため、マイルストーンごとの別PRではなく1本のPRにマイルストーン単位でコミットを積む。
- DBスキーマはMVPではSQLAlchemyモデルの `create_all`（`flask --app localvoice init-db`）で作成する。Alembic移行はPoC後に導入する。
- 外部サービス（Claude API、Google/Apple、TTS、Wikipedia等）は Adapter 経由にし、キー未設定時はテスト用/無効実装へ自動で切り替える。テストは外部通信なしで通る。

## 開発環境セットアップ（コンテナ再作成時）

```bash
apt-get update && apt-get install -y postgresql-16-postgis-3
PGBIN=/usr/lib/postgresql/16/bin
mkdir -p /var/lib/lvpg && chown postgres /var/lib/lvpg
su postgres -c "$PGBIN/initdb -D /var/lib/lvpg/data -A trust -U postgres && $PGBIN/pg_ctl -D /var/lib/lvpg/data -l /var/lib/lvpg/log -o '-p 5432 -k /tmp' start"
for d in localvoice localvoice_test; do psql -h localhost -U postgres -c "create database $d"; psql -h localhost -U postgres -d $d -c "create extension postgis"; done
pip install --ignore-installed blinker -r server/requirements.txt
# Flutter: https://storage.googleapis.com/flutter_infra_release/releases/releases_linux.json の stable を /opt/flutter へ展開
```

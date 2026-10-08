# MVP実装 進捗

このファイルは実装の再開ポイントです。作業が中断しても、次の回はここを読んで「次にやること」から続けます。
作業ブランチ: `claude/mvp-implementation-tnk3jq`

## マイルストーン

| # | 内容 | 状態 |
|---|---|---|
| M0 | 進捗ファイル・リポジトリ構成・開発環境 | 完了 |
| M1 | サーバー基盤（Flask app factory、DBモデル、エラー形式）と認証（ID/パスワード、token更新・失効、再認証、me、削除、Google、Apple、復旧メール・再設定） | 完了 |
| M2 | trip・context（PostGIS候補・ランキング・cooldown・黙る判定・決定ログ）・history・track・feedback・preferences/interests | 完了 |
| M3 | LLM Adapter（Claude）による選択・語り＋検証・フォールバック、実行時知識生成ワーカー（Wikipedia/Wikidata/OSM）、curated seed、TripMemorySummary | 完了 |
| M4 | 音声（VoiceProvider、/voices、/guides/{id}/speech、/speech-assets、キャッシュ） | 完了 |
| M5 | Flutterアプリ（認証・Home・Guide・Map・History・Preferences・Account、GPS・移動推定・ローカル記録/再送、通知、音声） | 未着手 |
| M6 | P1（一時指示commands、temporary state、participants） | 完了 |

## 次にやること

- MVPの対象機能は実装済み。残りは人の作業: curated seed の出典・読みの確認（review_status を reviewed へ）、APIキー・Google/Apple・TTS の設定、実機（Android/iOS）での動作確認。
- 実機確認で見つかった不具合の修正、PoC後に Alembic 移行の導入。

## 判断した内容

- 一時指示（P1）: `POST /trips/{id}/commands` は Claude（構造化出力、検証あり）で解釈し、使えない時はキーワード解釈。分からない指示は 422 で保存しない。曖昧（確信度<0.6）は15分だけ反映し `needs_confirmation`。同じカテゴリ・状態の新しい指示は古いものを置き換える。「降りるまで」等の測れない終了条件は文字で保持するだけで、自動終了はしない（チップの×で解除）。
- 一時状態: quiet 30分（自動案内停止）、hungry 60分（食を優先）、toilet 20分（実用を優先）、tired（間隔2倍）、bored（間隔半分）、no_time（短い文）。UIの「30分静かに」は `POST /trips/{id}/states`。
- 同行者（participants）はホストのtrip内だけのプロフィールで、興味カテゴリを話題選びに加える。最大8人。

- Flutter: 状態管理は provider。ローカルDBはユーザーごとに別ファイル（`lv_<user_id>.db`）、ログアウト/切替時は GPS・音声・通知を止めてから閉じる。
- 位置送信は 30m移動 / 60秒 / 移動区分の変化で間引き、サーバーの `next_check_after_sec` 中は大きく動いた時だけ送る。オフライン中は端末に保存し、回復後に再送（サーバー側は履歴保存のみ）。
- Androidは位置のフォアグラウンドサービス（常時位置権限は求めない）、iOSは `location`/`audio` バックグラウンドモード。
- 音声は世代番号で管理し、古い・停止後・ログアウト後の音声は自動再生しない。サーバー音声を最大5秒待ち、端末TTSは利用者が許可した時だけ。
- Android の Apple ログインは sign_in_with_apple のWebフロー。サーバー `apple/start` が client_id と redirect_uri を返し、コールバックは `intent://callback?...;scheme=signinwithapple` でアプリへ戻す（handoff code を `apple/complete` へ）。

- 音声: `TTS_PROVIDER=none` が既定（端末TTSへ代替）。`google`（Chirp 3 HD）と開発用 `silent` を実装。声は `services/voice.py` の許可リスト。採用声は試聴後に差し替える。個人化（LLMが書いた）原稿は private、保存済み原稿は shared。

- LLMは `services/llm.py` の ClaudeLLM（`claude-opus-5-5`、構造化出力、選択はeffort low・4秒、生成はmedium、`fallbacks: "default"`、systemにcache_control）。キー未設定時は無効でルールにフォールバック。
- OpenAIも選べる（`LLM_PROVIDER=openai` または `OPENAI_API_KEY` のみ設定）。`OpenAILLM` が Responses API の構造化出力（strict json_schema）と web_search で同じプロンプト・スキーマ・検証を使う。モデルは用途で分ける: `LLM_REALTIME_MODEL`（選択・語り、自然文指示。既定 `gpt-6-luna`、実測約2秒で4秒タイムアウトに収まる）と `LLM_BACKGROUND_MODEL`（知識生成・web調査・旅の要約。既定 `gpt-6.1-sol`。実測で調査約36秒・生成約65秒、1セルあたり約0.08ドル）。2026-10-08からは、調べた素材から話を書く処理だけ `LLM_GENERATE_MODEL`（既定 `gpt-6-luna`）で動かす。費用を下げるためで、調査は `LLM_BACKGROUND_MODEL` のまま。`gpt-6.1-sol` は選択だと約8秒かかりルールにフォールバックするため realtime には使わない。料金は `config.MODEL_PRICES`（`LLM_PRICES` で追加・上書き）。api_usage_logs の provider は `openai`。
- LLM出力の検証: 候補内のID、候補のclaim ID、視界表現の禁止、方位不確かな時の左右禁止、素材にない数字の禁止。失敗理由は guide_decisions.fallback_reason。
- 実行時生成では、セル内の町名を Nominatim で取り、新しい町ごとに1回だけ町名の由来と郷土史をweb検索する（`local_history_research`、プロンプト `local-history-v1`、生成は `generate-v2`）。同じ町は `COVERAGE_TTL_DAYS` の間は調べ直さない。
- 実行時生成の確度はルールで medium/low のみ（highは自動付与しない）。沿革・実用のみ・関係の薄い過去ニュースは auto_eligible=false。
- 実証地域の curated seed（宮島・広島・尾道・奈良 18話）は**下書き**。旅行前に人が出典と読みを確認し、review_status を reviewed にする必要がある。

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

# サブスクのAIで話を作る（外部生成）

ChatGPT（Codex）・Claude（Claude Code）・Gemini（Antigravity）・Cursor など、オーナー自身のサブスクの枠で話を作り、本番サーバーに取り込む仕組みです。

## 仕組み

- どのセルを作るか、どの調査テーマを調べるか、プロンプト、ラウンドの繰り返し、品質チェック、重複除外は、**サーバーのいつもの生成処理（`knowledge_gen._generate`）がそのまま行います**。
- AIに頼むのは、その処理の中の2種類の作業だけです。
  - Web調査: サーバーと同じ調査プロンプトで検索し、事実を出典URL付きで返す。
  - 話の執筆: サーバーと同じ指示（`GENERATE_SYSTEM`）・入力・JSONスキーマで話を書く。
- サーバーは答えを受け取るたびに、そのセルの処理を最初からやり直します（答え済みの作業は保存した答えを使う）。全部の作業に答えが揃った時点で、初めて話が保存されます。途中でやめても何も残りません。
- 出典URLのページが存在しない（404/410、存在しないホスト）事実は捨てます。
- 音声は、話が初めて再生されたときに今まで通り作られます（Google TTS の無料枠はここで使われます）。

## どこから作るか

1. `server/localvoice/seed/hotspots.py` の観光地（旅行者が多い順）のセルを、1セルあたり `EXTERNAL_GEN_TARGET_PER_CELL`（既定30話）になるまで作ります。
2. 全観光地が目標に達するか、調査テーマを使い切ったら、各観光地の周り1周目のセル、2周目、と広げます（`EXTERNAL_GEN_MAX_RING`、既定3周）。
3. 1回の作業（1セル）では、今の生成と同じく、調査テーマを4つずつ進めます。テーマが残っていて目標に届いていないセルは、次の回にまた選ばれます。

アプリ利用者の移動で動くサーバーのワーカーとは、同じセルを同時に作らないようにしています。

## サーバー側の準備（初回のみ）

1. トークンを作る: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. `/srv/app/localvoice/.env` に `EXTERNAL_GEN_TOKEN=<トークン>` を追加する。
3. コードを更新して `flask --app localvoice init-db`（新しい表 `external_gen_tasks` を作る）を実行し、`localvoice` と `localvoice-worker` を再起動する。

設定がないと、この仕組みのAPIは存在しない扱い（404）になります。

## AIを動かすPC側の準備

1. このリポジトリを置き、Python 3 が動くようにする（追加のライブラリは不要）。
2. 環境変数 `LOCALVOICE_EXTERNAL_GEN_TOKEN` にトークンを設定する（または `.subgen/token` に書く）。サーバーは既定で `https://localvoice.ideaworks.tech`。
3. 枠のリセット時刻を `.subgen/schedule.json` に書く（形は `tools/subgen/schedule.json` と同じで、書いたAIだけ上書きされる）。例:

```json
{"agents": {"codex": {"weekly_reset": "thu 21:00"}, "claude": {"weekly_reset": "sat 08:00", "final_cells": 12}}}
```

週の枠のリセットまで `final_hours`（既定24時間）を切ると、1回で作るセル数が `cells`（既定1）から `final_cells`（既定8）に増えます。Cursor のように月単位の枠は `monthly_reset`（日にち）で指定します。

## 予約実行に登録するプロンプト

各製品の公式の予約実行（スケジュール）機能に、リポジトリのフォルダで次のプロンプトを登録します。`<名前>` は codex / claude / gemini / cursor など、`<モデル>` は使うモデル名です（話に記録されます）。

```
LocalVoice の話づくりを手伝ってください。このリポジトリのルートで作業します。

1. `python tools/subgen/subgen.py plan --agent <名前>` を実行し、CELLS= の数を確認してください。
2. その数のセルが終わるまで、次を繰り返してください。
   a. `python tools/subgen/subgen.py next --agent <名前> --model <モデル>` を実行する。
      NOTHING_TO_DO と出たら、そこで終わりです。
   b. 表示された手順（.subgen/<名前>/TODO.md）に従い、各ステップのファイルを読んで、答えを指定の answer ファイルに書く。
      - Web調査: Web検索をして、プロンプトの指示どおりに事実を集める。実際に読んだページのURLだけを付け、推測で埋めない。
      - 執筆: system の指示に従い、input だけを材料に、schema どおりのJSONを書く。
   c. `python tools/subgen/subgen.py submit --agent <名前>` を実行する。
      次の手順が表示されたら b に戻る。DONE と出たらそのセルは完了。
      エラーが出たら、内容を読んで answer ファイルを直し、もう一度 submit する。
3. 利用上限に達したら、そこで止めてかまいません（途中のセルは次回の next で続きから再開されます）。
```

週の枠が余りそうなときは、リセット前日に予約を1回増やすか、手動で同じプロンプトを実行します。

## 規約について

- 各社の公式アプリ・公式CLIを、オーナー本人が、公式の予約実行機能で使う形にしてください。自作のプログラムからサブスクのログイン情報を使ってAIを呼び出したり、画面を自動操作して結果を取り出したりはしないでください。
- `subgen.py` がするのは、ファイルの読み書きとLocalVoiceのサーバーとの通信だけです。
- Claude の Pro/Max の上限は「個人の通常の利用」を前提にしています。作る量はそれに見合う範囲にしてください。

## API

すべて `Authorization: Bearer <EXTERNAL_GEN_TOKEN>` が必要です。

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/v1/external-gen/tasks` | `{agent, model}`。次のセルを確保して、最初の作業を返す。作るものがなければ `status: nothing_to_do` |
| GET | `/api/v1/external-gen/tasks/{id}` | 待っている作業をもう一度返す |
| POST | `/api/v1/external-gen/tasks/{id}/answers` | `{answers: [{index, result}]}`。次の作業、または完了（`status: done`, `created`）を返す |
| POST | `/api/v1/external-gen/tasks/{id}/abandon` | セルを手放す |

作業（`calls`）は `{index, kind, instructions, ...}` です。`kind: web_research` は `prompt` を持ち、答えは `[{fact, url, title}]`。`kind: json` は `system`・`input`・`schema` を持ち、答えはスキーマどおりのJSONオブジェクトです。確保したセルは `EXTERNAL_GEN_LEASE_MIN`（既定180分）答えがないと手放されます。

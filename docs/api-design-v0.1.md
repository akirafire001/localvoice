# LocalVoice API設計 v0.1

Base: `/api/v1`

## 共通
JSON、UTF-8。日時はISO 8601 offset付き。IDはUUID。エラーは `{code,message,details}`。

## 認証（MVP必須）

認証方式はGoogleログインとLocalVoiceのID・パスワード。[認証設計](authentication-design-v0.1.md)を正本とする。IDはメールアドレスとは別のログインID。認証・復旧用の公開エンドポイント以外は `Authorization: Bearer <LocalVoice access token>` を必須とする。

| Method / Path | 内容・主要入力 |
| --- | --- |
| POST /auth/register | ID登録: login_id, password, recovery_email（任意） |
| POST /auth/login | IDログイン: login_id, password |
| POST /auth/google | Google ID token検証とログイン/初回登録: id_token |
| POST /auth/refresh | LocalVoice token更新: refresh_token |
| POST /auth/logout | 現在のログインセッション失効（access tokenまたは対応するrefresh tokenで本人確認） |
| POST /auth/reauthenticate | 直近の再認証を記録: passwordまたは新しいgoogle_id_token。必ず現在のuser_idに一致する方式を検証 |
| GET /users/me | 内部ID、表示名、利用可能なログイン方法、復旧用メールの確認状態 |
| POST /users/me/auth/google | 直近の再認証と検証済みid_tokenでGoogleを連携 |
| DELETE /users/me/auth/google | 直近の再認証後に解除。最後のログイン手段なら拒否 |
| PUT /users/me/auth/password | 直近の再認証後にID・パスワード追加/パスワード変更。login_id, password。既存IDの変更はMVP外 |
| POST /users/me/recovery-email | 直近の再認証後に任意メールの確認送信: email |
| POST /auth/email/verify | 期限付き・一回限りのtokenで復旧用メールを確認 |
| POST /auth/password/reset-request | login_id指定。確認済み復旧用メールにのみ送信 |
| POST /auth/password/reset | 一回限りのtoken, new_password。既存password資格情報だけを変更し、全セッションを失効 |
| DELETE /users/me | 直近の再認証後にアカウントと本人の履歴を削除 |

ログイン/Google/登録/refreshの成功応答:
```json
{
 "user":{"id":"uuid","display_name":"..."},
 "access_token":"opaque-random-token",
 "token_type":"Bearer",
 "expires_in":900,
 "refresh_token":"opaque-random-refresh-token"
}
```

access tokenは15分、refresh tokenはログインから30日の絶対期限を初期値とする。サーバーにはtokenのハッシュだけを保存する。refresh交換時は旧tokenを一回限りで消費し、再利用時はそのログインセッション全体を失効する。ログインセッションとtripセッションを区別する。

Google ID tokenの署名・issuer・audience・期限を検証し、subから内部user_idを確定する。メール一致で自動統合しない。既に別user_idへ紐づくGoogleを追加する場合は409。ログイン失敗はIDの存在を明かさない共通401、レート超過は429とする。reset-requestはID/メールの存在・未確認・Googleのみの場合も同じ202で返し、送信したかを明かさない。

PUT /users/me/auth/passwordの成功、パスワード再設定、アカウント削除では全ログインセッションを失効する。再ログイン後に新tokenを取得する。

trip/track/context/historyだけでなく、feedback・participants・一時指示の所有者も親tripから確認する。user_idを本文で指定して他人のデータを操作することはできない。

## POST /trips
旅行/散歩セッション開始。

Request:
```json
{"purpose":"travel","language":"ja","settings":{"notification_level":"normal","detail_mode":"auto","serendipity":"normal"}}
```
Response: `201 {"trip_id":"...","started_at":"..."}`

## PATCH /trips/{trip_id}
通知頻度、詳細度、手動移動モード等を更新。

## POST /trips/{trip_id}/finish
セッション終了。memory summary確定、PoC集計用summaryを返す。

## POST /trips/{trip_id}/context
中心API。位置/移動/状態を送信し、通知すべき場合だけguideを返す。

Request:
```json
{
 "client_event_id":"9e8629bf-9a1c-4b77-8b2e-563ec9a926f8",
 "observed_at":"2026-12-28T15:30:00+09:00",
 "location":{"lat":34.0,"lon":132.0,"accuracy_m":12},
 "motion":{"speed_mps":1.2,"course_deg":240,"transport_mode":"walking","confidence":0.83},
 "active_topics":["architecture"]
}
```

No notification:
```json
{"guide":null,"decision":{"reason":"cooldown","next_check_after_sec":60}}
```

Guide:
```json
{
 "guide":{
   "history_id":"uuid",
   "knowledge_id":"uuid",
   "title":"...",
   "text":"...",
   "detail_text":"...",
   "language":"ja",
   "confidence":{"level":"high","fact_type":"verified_fact"},
   "sources":[{"title":"...","publisher":"...","url":"..."}],
   "image":null,
   "speech":{"enabled":true,"text":"..."}
 },
 "decision":{"score":0.81,"reason":"selected"}
}
```

サーバーは毎回guideを返す義務を持たない。`guide:null` が正常系。

## GET /trips/{trip_id}/history
今日の通知履歴。

## GET /trips/{trip_id}/track
選択したセッションの地図用移動履歴。保存期間内であれば終了済みセッションも取得可能。サーバーが受信済みのcontext_snapshotsを返し、現在地の取得は端末で行う。

Query:
- `from` / `until`: 任意の観測時刻範囲（ISO 8601 offset付き、from以上・until未満）
- `limit`: 1〜1000、既定500
- `cursor`: 次ページ取得用の不透明カーソル。期間条件はページ間で維持する。

Response:
```json
{
 "trip_id":"uuid",
 "points":[
   {
     "client_event_id":"9e8629bf-9a1c-4b77-8b2e-563ec9a926f8",
     "observed_at":"2026-12-28T15:30:00+09:00",
     "location":{"lat":34.0,"lon":132.0,"accuracy_m":12}
   }
 ],
 "next_cursor":null
}
```

- 観測時刻と内部IDの昇順で安定したページングを行う。全ページ取得して時刻順に描画する。
- 記録なし/保存期間後の削除済み履歴は `points:[]`。存在しないセッションと取得権限のないセッションはエラーにする。
- ページングは一覧取得用。通信回復後は履歴を再取得し、遅れて受信された過去時刻の点を取り込む。
- 端末はclient_event_idでローカルの未送信点と重複排除する。時刻の長い欠損や異常点は地図側で線を分断し、補正済み道路経路として扱わない。
- trip_idだけで閲覧を許可せず、セッションの所有者を認証・認可する。

## POST /guides/{history_id}/feedback
Request:
```json
{"action":"more_related","participant_id":null}
```
Action:
- `more_detail`
- `more_related`
- `enough_topic`
- `like`
- `dislike`

`more_detail` は詳細文を返してよい。`more_related` はtopic boostを生成。`enough_topic` は当該topic boostを終了するが長期趣向を下げない。

## GET/PATCH /users/me/preferences
通知頻度、情報量、セレンディピティ、言語等。

## GET/PATCH /users/me/interests
カテゴリ別の明示趣向。

## POST /trips/{trip_id}/commands (P1)
自然言語指示。
```json
{"text":"この電車を降りるまで建築を多めに教えて"}
```
Responseは構造化されたoverrideとUI表示用ラベルを返す。曖昧なら勝手に永続化せず、短いTTLまたは確認を要求する。

## DELETE /trips/{trip_id}/overrides/{id} (P1)
一時指示解除。

## POST /trips/{trip_id}/participants (P1)
ホスト端末上の同行者プロフィール追加。

## セキュリティ
- 本番はHTTPS必須
- MVPからGoogle / ID・パスワード認証、LocalVoice token検証を必須とする。PoCでも共有ユーザーや認可省略で個人データを扱わない
- trip_id/history_idだけで他人のデータを参照・更新できないよう、全個人データAPIで認証済みuser_idと親tripの所有者を照合する
- APIログに精密位置、パスワード、Google ID token、Authorization header、refresh/reset tokenを無条件出力しない。エラー・分析ログでも認証情報をマスクする

## 冪等性/再送
モバイル通信断を想定し、contextの `client_event_id`（UUID）をMVPで必須にする。端末は間引いた記録点を送信前にローカル保存し、通信回復後も同じIDとobserved_atで再送する。サーバーは `(trip_session_id, client_event_id)` でcontext_snapshotsの重複を防ぎ、同一イベント再送でnotification_historyを二重生成・再通知しない。再送時はguideを返さず `guide:null`、decision.reason=`duplicate_event` とする。過去時刻の未処理点のうちガイド対象の鮮度閾値を超えた点は履歴保存のみ行い、現在のガイド選択・移動状態を巻き戻さない。鮮度閾値はPoCで調整する。同じIDで異なる内容を送った場合は競合エラーとする。セッション終了後も保持期間内の未送信点は履歴として受け付け、ガイドは生成しない。保持期限後の点は受け付けず、期限切れを返す。

## Rate control
端末はサーバー指定 `next_check_after_sec` を尊重する。移動状態が変化した場合は早期送信可能。サーバー側にもrate limitを置く。

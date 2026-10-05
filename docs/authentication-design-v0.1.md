# LocalVoice 認証設計 v0.1

更新日: 2026-10-06
状態: MVPの設計。実装・Google OAuth設定・実機検証は未実施。

## 1. MVPの認証方式

利用者は次のどちらかでログインできる。
- Googleアカウントでログイン。
- LocalVoiceのログインIDとパスワードでログイン。

IDはメールアドレスとは別の任意ログインIDとする。表示名や内部UUIDとも区別する。任意IDの使用可能文字・長さと、大文字小文字の正規化ルールは実装前に決定し、登録・ログイン・DBの一意制約で統一する。

本人の趣向、旅行セッション、通知履歴、移動履歴はLocalVoiceの内部user_idに紐づける。本人が連携した2方式は同じuser_idへ対応させる。旅行開始と個人データを扱うAPIではMVPから認証・所有者チェックを必須にする。

## 2. Googleログイン

Flutterのgoogle_sign_inでログインし、バックエンド向けGoogle ID tokenをHTTPSでFlaskへ渡す。Flaskはgoogle-auth等の公式ライブラリで署名・issuer・許可したaudience・有効期限を検証し、検証済みのsubでユーザーを特定する。端末から送られたメールアドレスや表示名だけで本人判定しない。

Google ID tokenはログイン時の検証にだけ利用し、LocalVoiceのAPIセッションは別途発行する。Googleのパスワードは扱わず、ID tokenやGoogle API access/refresh tokenを保存・ログ出力しない。MVPのログインではカレンダーやDrive等の追加権限は求めない。

Googleのみで新規登録した利用者には、LocalVoiceのID・パスワードを必須にしない。

根拠: [Googleサーバー側の本人確認](https://developers.google.com/identity/sign-in/web/backend-auth)、[Flutter google_sign_in](https://pub.dev/packages/google_sign_in)

## 3. ID・パスワード

- IDは一意。password_credentialsに保存した正規化IDで検索する。
- パスワードはArgon2idでソルト付きハッシュとして保存する。平文や復号可能な暗号で保存しない。
- 初期方針は15文字以上、少なくとも64文字まで入力可能とし、任意の記号・空白を許可する。貼り付け・パスワードマネージャーを妨げず、入力を勝手に短縮・正規化しない。上限は実装で明示する。
- よく使われる/漏洩済みのパスワードを拒否する。これを外部APIの利用必須にはせず、採用方法は実装時に決定する。
- ログイン試行はIDと送信元単位で回数制限し、IDの存在を漏らさない共通エラーを返す。
- 復旧用メールは任意入力。利用する場合はメール確認を行い、確認済みメールだけに再設定リンクを送る。Google連携も復旧用メールもない場合は、パスワードを忘れると自動復旧できないことを登録画面で伝える。

Argon2idの初期最低値はOWASP推奨のm=19 MiB、t=2、p=1以上とし、実環境の負荷に合わせて検証する。期限付き・一度だけ使える再設定tokenをハッシュ保存し、再設定後は全ログインセッションを失効する。

根拠: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)、[Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

## 4. 連携と本人確認

設定の「ログイン方法」から次を行う。
- ID・パスワード利用者が、直近のパスワード再認証とGoogleログインの両方を行ってGoogleを追加。
- Google利用者が、直近のGoogle再認証後に未使用IDとパスワードを設定。
- Googleを解除する場合は直近の再認証を求め、別の有効なログイン方法が残る場合だけ許可。

メールアドレスの一致だけで既存ユーザーを自動統合しない。Googleの識別子は(provider, subject)で一意にし、別user_idへ連携済みなら409を返す。既に別々に作成された2アカウントの履歴統合はMVP外。連携前後でuser_id・旅行履歴の所有者を変更しない。

直近の再認証は5分以内を初期値とする。LocalVoiceの通常token更新だけでは再認証扱いにしない。Googleの場合は保存済みtokenの再送ではなく、新たなGoogle認証イベントに基づきiat等の鮮度も検証する。

## 5. LocalVoiceのログインセッション

MVPはサーバーで失効を管理できるランダムなopaque tokenを利用する。初期値はaccess token 15分、refresh tokenはログインから30日の絶対期限とする。これらはGoogleのtokenではない。

- access tokenはAuthorization: Bearerで送る。サーバーは有効期限・失効状態・user_idを照合する。
- refresh tokenは端末のKeychain/Keystoreに基づく安全な保存領域へ保存し、access tokenは原則メモリに置く。
- サーバーはtokenのハッシュだけを保存する。
- refresh時に旧refresh tokenを一度だけ消費して新tokenへ交換する。消費済みtokenの再利用を検出したら該当ログインセッション全体を失効する。交換はトランザクションで処理し、アプリ側も同時refreshをまとめる。
- ログアウト時は当該セッションを失効し、端末のtokenを削除する。
- パスワード変更・再設定・アカウント削除では全セッションを失効する。

通信断中は既存ガイドセッションのローカル記録・キャッシュ表示を継続できる。認証切れではサーバー送信を保留し、通信回復時にtoken更新、必要なら再ログインする。旅行中に毎回Googleの画面を開かない。

ログアウト・アカウント切替時はGPSと音声を停止し、ローカル履歴・未送信点をuser_id単位で隔離する。別ユーザーのログイン後に、前ユーザーの履歴を表示・再送しない。

## 6. 所有者チェック

user_idはtokenから確定し、リクエスト本文のuser_idを信用しない。
- trips: trip_sessions.user_idが本人と一致すること。
- track/context/history/finish/commands/participants: 親tripの所有者を確認。
- guides/feedback: notification_historyの親tripから所有者を確認。
- preferences/interests/me: 認証済み本人に限定。

ゲスト同行者はホスト端末上のプロフィールであり、他人の履歴にアクセスするアカウント権限を付与しない。trip_idやhistory_idを知っているだけではアクセスできない。

## 7. アカウント削除と公開前確認

アプリの設定から、直近の再認証後にアカウント削除を開始できるようにする。全セッションを失効し、本人の旅行・精密位置履歴・認証情報を削除する。端末キャッシュにも反映し、バックアップを含む削除方針は公開前に定義する。

iOSでGoogleログインを提供してApp Storeへ公開する場合、審査ガイドライン4.8では条件を満たす同等のログイン方式も要求される。ID・パスワードがあるだけで充足すると断定せず、適用条件を確認し、必要に応じSign in with Appleを追加する。ユーザー指定の2方式はMVP要件として維持する。アカウント作成対応アプリのアプリ内削除要件にも対応する。

根拠: [Apple App Review Guidelines 4.8 / 5.1.1](https://developer.apple.com/app-store/review/guidelines/)

## 8. 実装時の確認

- 両方式で登録・ログインし、連携後に同じ趣向と履歴を参照できる。
- 改ざん・期限切れ・issuer/audience不一致のGoogle ID tokenを拒否する。
- ID重複、誤パスワード、token失効、refresh再利用を正しく処理する。
- メール一致では統合せず、別ユーザーに連携済みのGoogleアカウントを拒否する。
- user Aのtokenでuser Bのtrip/track/feedbackへアクセスできない。
- 通信断、token期限切れ、ログアウト、別アカウントへの切替で履歴が混ざらない。
- パスワード再設定tokenは期限付き・一回限り、再設定後は全セッションが失効する。
- アカウント削除後にサーバー履歴の取得と端末からの再送ができない。

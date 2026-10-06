# LocalVoice 認証設計 v0.1

更新日: 2026-10-06
状態: MVPの設計。実装・Google/Apple開発者設定・実機検証は未実施。

## 1. MVPの認証方式

利用者は次の3方式から選んでログインできる。
- Googleアカウントでログイン。
- Appleアカウントでログイン。
- LocalVoiceのログインIDとパスワードでログイン。

IDはメールアドレスとは別の任意ログインIDとする。表示名や内部UUIDとも区別する。任意IDの使用可能文字・長さと、大文字小文字の正規化ルールは実装前に決定し、登録・ログイン・DBの一意制約で統一する。

本人の趣向、旅行セッション、通知履歴、移動履歴はLocalVoiceの内部user_idに紐づける。本人が連携したログイン方法（最大3方式）は同じuser_idへ対応させる。旅行開始と個人データを扱うAPIではMVPから認証・所有者チェックを必須にする。

## 2. Googleログイン

Flutterのgoogle_sign_inでログインし、バックエンド向けGoogle ID tokenをHTTPSでFlaskへ渡す。Flaskはgoogle-auth等の公式ライブラリで署名・issuer・許可したaudience・有効期限を検証し、検証済みのsubでユーザーを特定する。端末から送られたメールアドレスや表示名だけで本人判定しない。

Google ID tokenはログイン時の検証にだけ利用し、LocalVoiceのAPIセッションは別途発行する。Googleのパスワードは扱わず、ID tokenやGoogle API access/refresh tokenを保存・ログ出力しない。MVPのログインではカレンダーやDrive等の追加権限は求めない。

Googleのみで新規登録した利用者には、LocalVoiceのID・パスワードを必須にしない。

根拠: [Googleサーバー側の本人確認](https://developers.google.com/identity/sign-in/web/backend-auth)、[Flutter google_sign_in](https://pub.dev/packages/google_sign_in)

### 2.1 Appleログイン（MVP必須）

Sign in with AppleをiOS/Androidの両方で提供する。Flutterのsign_in_with_appleを利用し、iOSはネイティブの認証画面、AndroidはServices IDを使ったブラウザー認証と登録済みHTTPSコールバックを利用する。Apple Developer側でApp ID、Services ID、Sign in with Apple用キー、許可する戻り先を設定する。iOSとAndroidのApp ID/Services IDは同じ利用者が同じ識別子へ対応するようApple側で関連付ける。

- 認証開始時にサーバーが短期限・一回限りのchallengeを発行し、処理目的（login/link/reauthenticate）、端末種別、許可audience、nonce、Webフローのstateを紐づける。連携・再認証の開始は認証済みuser_idにも紐づける。
- サーバーはAppleの公開鍵で署名を検証し、issuer=https://appleid.apple.com、許可audience、期限、nonceを照合する。Webコールバックはstateも確認する。audience/redirect_uriは端末の任意指定を信用せず、サーバー設定から選ぶ。
- 認可コードはサーバーでAppleのtoken endpointへ一度だけ交換し、返されたID tokenも検証する。native側のID tokenがある場合はsub・audience・nonceの整合を確認する。Apple用client_secretはサーバーで署名生成し、署名秘密鍵をアプリやGitへ入れない。
- 本人判定には(provider=apple, subject=検証済みsub)を利用する。メール非公開の中継アドレスでも利用でき、実メールの開示やLocalVoiceのパスワード設定を求めない。
- 名前は初回認証時しか取得できない場合があるため、検証成功後に任意の表示名として保存し、以後欠けてもログインを失敗させたり既存表示名を消したりしない。
- AndroidのコールバックからLocalVoiceのaccess/refresh tokenやApple tokenをURLで渡さない。短期限・一回限りのhandoff codeを使い、端末が開始時に保持したランダムなcode_verifierの証明（開始時はSHA-256のcode_challenge）をサーバーが確認してから完了する。この証明はLocalVoiceの引き渡し用であり、AppleがPKCE対応すると仮定しない。

Appleのrefresh tokenは、認証状態の確認と連携解除・アカウント削除時のrevokeのため、サーバーで暗号化保存する。これはハッシュだけを保存するLocalVoice tokenとは別物。暗号鍵をDBと分離して保管し、token平文をログに出さない。Apple側の状態確認は1日1回以下を基本とし、明示的な失効・連携取り消しでは該当Apple連携を無効化し、Appleで認証したLocalVoiceセッションを失効する。通信障害だけでアカウントを削除しない。

Apple解除/アカウント削除時はAppleのrevoke endpointも呼ぶ。一時失敗時はローカル認証を先に失効し、必要最小限の暗号化tokenを削除処理キューへ移して再試行する。Apple側の取り消しを確認してからキューのtokenを削除し、取り消し完了を偽って表示しない。認証を完了しなかったchallengeの期限切れ時にも、交換済みApple tokenがあれば取り消しキューで処理する。

中継メールへ確認・復旧メールを送る場合はAppleのPrivate Email Relayへ送信元を登録し、SPF/DKIM等を設定する。非公開メールを選んだだけでは復旧用メールを自動登録せず、利用者が設定したメールを確認する。

根拠: [Apple本人確認](https://developer.apple.com/documentation/signinwithapple/verifying-a-user)、[他プラットフォーム対応](https://developer.apple.com/documentation/signinwithapple/incorporating-sign-in-with-apple-into-other-platforms)、[初回の氏名等](https://developer.apple.com/documentation/signinwithapple/authenticating-users-with-sign-in-with-apple)、[token取り消し](https://developer.apple.com/documentation/signinwithapplerestapi/revoke-tokens)、[Flutter package](https://pub.dev/packages/sign_in_with_apple)、[Private Email Relay設定](https://developer.apple.com/help/account/configure-app-capabilities/configure-private-email-relay-service/)

## 3. ID・パスワード

- IDは一意。password_credentialsに保存した正規化IDで検索する。
- パスワードはArgon2idでソルト付きハッシュとして保存する。平文や復号可能な暗号で保存しない。
- 初期方針は15文字以上、少なくとも64文字まで入力可能とし、任意の記号・空白を許可する。貼り付け・パスワードマネージャーを妨げず、入力を勝手に短縮・正規化しない。上限は実装で明示する。
- よく使われる/漏洩済みのパスワードを拒否する。これを外部APIの利用必須にはせず、採用方法は実装時に決定する。
- ログイン試行はIDと送信元単位で回数制限し、IDの存在を漏らさない共通エラーを返す。
- 復旧用メールは任意入力。利用する場合はメール確認を行い、確認済みメールだけに再設定リンクを送る。Google/Apple連携も復旧用メールもない場合は、パスワードを忘れると自動復旧できないことを登録画面で伝える。

Argon2idの初期最低値はOWASP推奨のm=19 MiB、t=2、p=1以上とし、実環境の負荷に合わせて検証する。期限付き・一度だけ使える再設定tokenをハッシュ保存し、再設定後は全ログインセッションを失効する。

根拠: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)、[Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

## 4. 連携と本人確認

設定の「ログイン方法」から次を行う。
- ID・パスワード利用者が、直近のパスワード再認証と追加するGoogle/Appleログインの両方を行って連携。
- Google/Apple利用者が、直近の連携済み方法による再認証後に、未使用IDとパスワードまたはもう一方の外部ログインを追加。
- Google/Appleを解除する場合は直近の再認証を求め、別の有効なログイン方法が残る場合だけ許可。Appleの場合はサーバー側のApple tokenも取り消す。

メールアドレスの一致だけで既存ユーザーを自動統合しない。Google/Appleの識別子は(provider, subject)で一意にし、別user_idへ連携済みなら409を返す。既に別々に作成された2アカウントの履歴統合はMVP外。連携前後でuser_id・旅行履歴の所有者を変更しない。

直近の再認証は5分以内を初期値とする。LocalVoiceの通常token更新だけでは再認証扱いにしない。Googleの場合は保存済みtokenの再送ではなく、新たなGoogle認証イベントに基づきiat等の鮮度も検証する。Appleの場合は目的・本人を紐づけた新しいchallengeで認証し、nonce/state・認可コード・tokenを検証して再認証時刻を更新する。

## 5. LocalVoiceのログインセッション

MVPはサーバーで失効を管理できるランダムなopaque tokenを利用する。初期値はaccess token 15分、refresh tokenはログインから30日の絶対期限とする。これらはGoogle/Appleのtokenではない。

- access tokenはAuthorization: Bearerで送る。サーバーは有効期限・失効状態・user_idを照合する。
- refresh tokenは端末のKeychain/Keystoreに基づく安全な保存領域へ保存し、access tokenは原則メモリに置く。
- サーバーはtokenのハッシュだけを保存する。
- refresh時に旧refresh tokenを一度だけ消費して新tokenへ交換する。消費済みtokenの再利用を検出したら該当ログインセッション全体を失効する。交換はトランザクションで処理し、アプリ側も同時refreshをまとめる。
- ログアウト時は当該セッションを失効し、端末のtokenを削除する。
- パスワード変更・再設定・アカウント削除では全セッションを失効する。

通信断中は既存ガイドセッションのローカル記録・キャッシュ表示を継続できる。認証切れではサーバー送信を保留し、通信回復時にtoken更新、必要なら再ログインする。旅行中に毎回Google/Appleの画面を開かない。

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

Google・Apple・ID／パスワードの3方式をMVP必須とする。iOS公開時はAppleログインの同等な提示・メール非公開・審査ガイドライン4.8への適合を確認する。アカウント作成対応アプリのアプリ内削除要件と、Apple連携を含む削除時のtoken取り消しにも対応する。

根拠: [Apple App Review Guidelines 4.8 / 5.1.1](https://developer.apple.com/app-store/review/guidelines/)

## 8. 実装時の確認

- 3方式で登録・ログインし、連携後に同じ趣向と履歴を参照できる。
- 改ざん・期限切れ・issuer/audience不一致のGoogle/Apple ID tokenを拒否する。
- Appleのnonce/state不一致、challenge/認可コード/handoffの再利用を拒否する。
- iOS/AndroidのApple sub対応、メール非公開、初回だけの表示名を確認する。
- Appleの明示的失効で該当セッションが停止し、解除・削除時のrevokeと失敗時の再試行を確認する。
- ID重複、誤パスワード、token失効、refresh再利用を正しく処理する。
- メール一致では統合せず、別ユーザーに連携済みのGoogle/Appleアカウントを拒否する。
- user Aのtokenでuser Bのtrip/track/feedbackへアクセスできない。
- 通信断、token期限切れ、ログアウト、別アカウントへの切替で履歴が混ざらない。
- パスワード再設定tokenは期限付き・一回限り、再設定後は全セッションが失効する。
- アカウント削除後にサーバー履歴の取得と端末からの再送ができない。

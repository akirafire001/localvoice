# LocalVoice iPhone / TestFlight

SpotMemoと同じCodemagicのPersonal Accountと、既存のApple Developer連携 `Codemagic` を使う。

## 固定した設定

- リポジトリ: `akirafire001/localvoice`。Flutterプロジェクトは `app/`。
- Workflow: `production-ios-testflight`（リポジトリ直下の `codemagic.yaml`）。
- Flutter: `3.47.6`。Swift Package Managerと未対応プラグインのCocoaPodsフォールバックをFlutter自身に設定させる。
- iOS Bundle ID: `tech.ideaworks.localvoice`。Google Cloudの既存iOS OAuthクライアントと一致する。
- 対象: iPhone、iOS 15以降。表示名: `LocalVoice`。
- API: `https://localvoice.ideaworks.tech`。
- 配布証明書: Codemagic上の既存 `SpotMemo Distribution`。
- プロファイル参照名: `localvoice_app_store`（LocalVoice専用のApp Store配布プロファイル）。
- ビルド番号: Codemagicの `PROJECT_BUILD_NUMBER`。同一アプリで一意に増加する。Androidの番号とは独立。
- App Store Connectへのアップロードを有効化。外部TestFlight審査と正式App Store審査の自動提出は無効。

## 初回セットアップの記録（2026-10-11）

- Apple App ID `tech.ideaworks.localvoice` を登録し、Sign in with Appleを有効化済み。
- Google Cloudの既存iOS OAuthクライアントのBundle IDを上記へ変更し、保存を確認済み。
- App Store Connectアプリ: `LocalVoice`、Apple ID `6821467770`、SKU `localvoice-ios`、日本語。
- Appleの配布プロファイル `LocalVoice App Store` を既存配布証明書で作成し、Codemagicへ `localvoice_app_store` として取り込み済み。
- CodemagicアプリID: `6acabdc634b7f3fd846ddadd`。GitHub連携にLocalVoiceを追加済み。
- 初回ビルドは `codex/localvoice-ios-testflight` ブランチで起動。外部テストを希望するため、TestFlightのベータ説明・連絡先・専用審査アカウント情報を保存済み。
- 本番APIで審査専用アカウントのログインを確認済み。秘密情報は無視対象の `docs/store/ios/` に保存し、Gitには含めない。
- 初回時点のAppleログインは `/api/v1/auth/apple/start` が503。Apple用鍵とサーバー環境変数を設定し、成功を確認してから外部審査へ提出する。

## 初回登録

1. Apple Developerの更新された契約にAccount Holderが同意する。
2. LocalVoiceの明示的App IDを登録し、Sign in with Appleを有効にする。
3. 既存配布証明書を選んでLocalVoice専用のApp Store Connectプロファイルを作る。
4. CodemagicのCode signing identitiesからプロファイルを取得し、参照名を `localvoice_app_store` にする。
5. App Store ConnectにLocalVoiceのiOSアプリを登録する（Bundle IDは上記、基本言語は日本語、SKUは `localvoice-ios`）。
6. CodemagicにLocalVoiceリポジトリを追加し、設定ファイルのあるブランチでWorkflowを実行する。
7. ビルド・署名・アップロードの成功後、App Store ConnectのTestFlightで処理完了を確認し、内部テスターグループに追加する。
8. 外部テスターに配布する場合は、ベータ版説明、連絡先、テストアカウント等を用意し、TestFlightのベータ審査へ提出する。

## Appleログインのサーバー設定

iOSの権限とApple Developerの設定に加えて、サーバーの `APPLE_BUNDLE_ID=tech.ideaworks.localvoice`、`APPLE_TEAM_ID`、`APPLE_KEY_ID`、`APPLE_PRIVATE_KEY` が必要。既存のApp Store Connect APIキーと、Sign in with Apple用の秘密鍵は用途が異なる。鍵をGitやビルド設定ファイルへ入れない。

## 実機確認

- TestFlightからのインストール、起動、ID/パスワード・Google・Appleログイン。
- ガイド開始、現在地の許可、地図の表示、実際の音声再生。
- 画面ロック中の位置更新と音声、ガイド停止時の位置更新停止。
- 通信断からの復帰、ログアウト、再ログイン、アカウント削除。

Windows上の静的解析・FlutterテストだけではiOSのネイティブビルドや実機動作は確認できない。配布完了は、Codemagicの成功とTestFlightでインストール可能な状態を確認して判断する。

参考: [Codemagic Flutterビルド](https://docs.codemagic.io/yaml-quick-start/building-a-flutter-app/)、[App Store Connectへの配布](https://docs.codemagic.io/yaml-publishing/app-store-connect/)、[Flutter Swift Package Manager](https://docs.flutter.dev/packages-and-plugins/swift-package-manager/for-app-developers)。

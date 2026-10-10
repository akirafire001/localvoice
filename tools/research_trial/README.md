# Gemini無料枠のWeb調査の試験

今の町の調査（gpt-6.1-sol のWeb検索）と、Gemini API 無料枠の「Google検索によるグラウンディング」を、
同じ町・同じテーマ・同じ指示文で比べるための試験です。本番のプロンプトとテーマ（`llm.research_local_history`）と
町の取得（Nominatim）をそのまま使い、DBにも本番サーバーにも書き込みません。結果は `C:\work\git\localvoice\.research_trial\` に出ます。

## 準備

1. Google AI Studio（https://aistudio.google.com/apikey）でAPIキーを作る。請求先（課金）を紐づけないプロジェクトのままにすると無料枠だけで動き、課金は起きません。
2. PCの環境変数 `LOCALVOICE_GEMINI_API_KEY` にキーを設定する（`GEMINI_API_KEY` でも可）。OpenAIは今の `LOCALVOICE_OPENAI_API_KEY` を使います。
3. 実際の上限は https://aistudio.google.com/rate-limit で確認できます。

## 比べる（compare）

```
C:\work\git\localvoice\server\.venv\Scripts\python C:\work\git\localvoice\tools\research_trial\research_trial.py compare
```

既定は 尻手・矢向・パリのマレ地区 × 8テーマ（由来、地形と水、寺社と伝承、食、歴史上の人物、穴場、地元の本音、土地のマナー）。
OpenAI側は24回の調査で費用がかかります。Gemini側は無料枠を24回使います。
`--themes all` で42テーマ全部、`--place "名前,緯度,経度"` で場所を変えられます。`--gemini-only` でOpenAIを使わずに試せます。

出力の `compare-日時.md` に、事実の数・出典が開ける割合・出典に町名が載っている割合・数字が出典と一致する割合・費用の表と、
テーマごとの事実と出典の一覧が並びます。正確さは一覧を出典と読み比べて判断します。

## 1日の量を測る（volume）

```
C:\work\git\localvoice\server\.venv\Scripts\python C:\work\git\localvoice\tools\research_trial\research_trial.py volume
```

Geminiだけで、1日の上限に当たるまで（最大600回）調査を続けます。1分あたりの上限に当たると指示された秒数だけ待って続け、
1日の上限に当たったら止まって、成功した調査回数と「1日に回せる生成ジョブの数」の目安を出します。
1日の上限は太平洋時間の0時（日本時間で夏時間中は16時、11月からは17時）に戻ります。

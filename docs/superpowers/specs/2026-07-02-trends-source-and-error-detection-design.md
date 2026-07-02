# Google Trends 話題ソース追加＋自動処理エラー検知の設計

- 日付: 2026-07-02
- ステータス: 設計承認済み（実装計画待ち）
- 対象リポジトリ: finlab-se
- 関連spec: `2026-06-30-x-morning-topic-inline-selection-design.md`（朝のX話題連動のサーバー化）

## 1. 背景と課題

朝7:30のX話題連動投稿は、現在 Yahoo!経済アクセスランキング＋Google News RSS の2ソースで「話題」を判定している。ここに2つの改善を行う。

1. **検索行動シグナルの追加**: 現在の2ソースは「読まれている」「報じられている」を測るが、「検索されている」シグナルがない。Google Trends の検索急上昇ワードを3本目として追加する（置き換えではなく追加。実績評価の仕組みがないため、観測期間を置かず追加する判断をユーザーが下した）。
2. **サイレント故障の検知**: Google Trends は公式APIがなくRSSも仕様変更リスクがある。現状、時間実行の自動処理（GitHub Actions）が壊れても検知する仕組みがない。特にニュースソースの故障は投稿がrotationにフォールバックして「成功」扱いになるため、ジョブ失敗の監視だけでは気づけない。エラーを共通の場所に記録し、Claude起動時に毎回チェックしてユーザーに報告・対応する仕組みを作る。

## 2. 確定した設計判断

1. Google Trends は **3本目のソースとして追加**（既存2ソースは維持）。graceful degradation（取れない日は空リストで続行）。
2. エラーの共通ログは **GitHub Issues**（ラベル `automation-error`）。Open=未対応、Close=対応済みという状態管理が自然にでき、GitHubのメール通知も副次的に得られる。
3. エラーは2種類を検知する:
   - **ハードエラー**: ワークフローのジョブ失敗（exit≠0）
   - **ソフトエラー**: ニュースソースのいずれかが**0件**（サイレント故障。今回の設計の主目的）
4. 対象は時間実行される2ワークフロー: `x-post-scheduled.yml`（朝7:30/夜21:05）と `deploy.yml`（朝5:35/6:35）。
5. Claude起動時チェックは既存の SessionStart フック群（`~/.claude/scripts/*.mjs`）に1本追加する方式。

## 3. 機能①: Google Trends 3本目ソース

### 3.1 取得（collect_news.py）

- URL: `https://trends.google.co.jp/trending/rss?geo=JP`（**2026-07-02 実地検証済み**: APIキー不要・10件取得。内容は分野を問わない一般の急上昇ワードで、スポーツ・芸能が多い）
- `parse_google_trends_rss(xml_text) -> list[dict]` を追加。各要素 `{title, traffic}`。`traffic` は RSS の `ht:approx_traffic`（例 "20,000+"）で、取れなければ空文字（パース失敗で全体を落とさない）。
- `collect()` の出力を `{"yahoo": [...], "google": [...], "trends": [...]}` の3キーに拡張。既存同様、ソース単位の try/except で片方が壊れても続行。
- 依存は引き続き `requests`＋標準ライブラリのみ。

### 3.2 選定プロンプト（select_topic.py）

`_SYSTEM` に trends の扱いを追記する:

- trends は**分野を問わない日本全体の検索急上昇ワード**である
- **金融・経済に関するワードが入っている場合のみ強い加点材料**とし、スポーツ・芸能など無関係なワードは無視する
- 複数ソースに跨って現れる話題ほど優先（既存ルールの自然な拡張）
- こじつけ禁止は従来どおり維持

### 3.3 ログ（morning_post.py）

起動ログの件数行を3ソースに拡張: `collect_news: yahoo=15 google=69 trends=10`

## 4. 機能②: 自動処理エラー検知

### 4.1 エラーの定義と検知方法

| 種類 | 定義 | 検知方法 |
|---|---|---|
| ハードエラー | ジョブのいずれかのステップが失敗 | ワークフローに `if: failure()` の報告ステップを追加 |
| ソフトエラー | 朝スロットでニュースソースのいずれかが0件 | morning実行のstderrをファイルに捕捉し、`collect_news:` 行の件数を実行後ステップで検査 |

- ソフトエラー検査は **morning スロットのみ**（night は collect_news を使わない。night のハードエラーはジョブ失敗検知でカバー）。
- `collect_news:` の件数行が **stderr に存在しない場合**（ニュース収集が丸ごと失敗し話題選定がスキップされたケース）も、全ソース故障相当のソフトエラーとして Issue を作成する。
- 話題連動がrotationへフォールバックすること自体（該当なし・280字超過）は設計どおりの動作であり、**エラーとして扱わない**。

### 4.2 Issue の作成（report_automation_error.py 新設）

- `.github/scripts/report_automation_error.py`: `gh` CLI（ランナーに標準搭載、`GH_TOKEN=${{ github.token }}`）で Issue を作成する共通スクリプト。
- タイトル形式: `[automation-error] <ワークフロー名>/<スロット>: <要約>`
  - 例: `[automation-error] x-post-scheduled/morning: ニュースソース0件 (trends)`
  - 例: `[automation-error] deploy: ジョブ失敗`
- 本文: 発生日時（JST）・エラー種類・実行ログURL（`$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID`）・確認手順。
- ラベル: `automation-error`（リポジトリに事前作成する）。
- **重複防止**: 同一タイトルの Open な Issue が既に存在する場合は作成しない（`gh issue list --state open --label automation-error` で照合）。故障が継続しても Issue が毎日増えない。0件ソースの組み合わせが変われば別タイトル＝新規 Issue になる（意図どおり）。

### 4.3 ワークフロー改修

- `x-post-scheduled.yml`:
  - `permissions` に `issues: write` を追加
  - morning ステップで stderr をファイル（例 `stderr.log`）に捕捉しつつ従来どおりログにも出す
  - 実行後に `if: always()` のステップを追加し、(a) ジョブ失敗なら ハードエラー Issue、(b) morning かつ `collect_news:` 行に0件があれば ソフトエラー Issue を作成
- `deploy.yml`:
  - `permissions` に `issues: write` を追加
  - `if: failure()` のハードエラー報告ステップのみ追加

### 4.4 Claude起動時チェック（ローカル）

- `~/.claude/scripts/check-automation-errors.mjs` を新設し、ユーザー設定の SessionStart フックに追加（既存の Obsidian 読み込み等と同列）。
- 動作: `gh issue list -R nyo0521-a11y/finlab-se --label automation-error --state open --json number,title,createdAt,url` を実行。
  - **0件なら何も出力しない**（起動を汚さない）
  - **1件以上あれば**、Claude への指示文を出力: 「未対応の自動処理エラーがある。ユーザーに報告し、`gh run view` 等でログを調査し、修正し、対応内容を Issue にコメントして Close せよ」＋ Issue 一覧
  - `gh` 失敗時（オフライン等）は静かにスキップ（`|| true` パターン、既存フックと同じ）
- タイムアウト目安: 数秒以内。起動をブロックしない。

### 4.5 対応フロー（運用）

1. エラー発生 → Issue 自動作成（＋GitHubからメール通知）
2. Claude 起動時にフックが Open Issue を検知 → セッション冒頭で Claude がユーザーに報告
3. Claude が実行ログを調査・原因特定・修正
4. 対応内容を Issue にコメントし Close（＝既読化。次回起動では通知されない）

## 5. 併せて行う小さな掃除

`.github/scripts/__pycache__/` がgit管理に入っており、テスト実行のたびに作業ツリーが汚れて `git pull` を妨げている（本セッションで3回発生）。`git rm -r --cached` で管理から外し、`.gitignore` に `__pycache__/` を追加する。

## 6. テスト方針

- `parse_google_trends_rss`: 名前空間付きRSSモックでのパース、`approx_traffic` 欠落時の空文字、不正XMLで空リスト（単体）
- `collect`: trends を含む3キー出力、trends のみ失敗しても他2ソースが返る（単体・fetch注入）
- ソフトエラー判定: `collect_news:` 行から0件ソースを抽出するロジック（単体）
- `report_automation_error.py`: 重複タイトル存在時にスキップする分岐（gh呼び出しをモック）
- 結合: 実ワークフローを1回流し、(a) 正常時にIssueが作られないこと、(b) 擬似エラーでIssueが作られること、(c) 起動フックが検知すること、(d) Close後は通知されないこと、の一巡を確認

## 7. スコープ外（YAGNI）

- ローカルのスケジュールタスク（Claude Code上で動くもの）のエラー監視 — アプリ上で実行が見えるため対象外
- GitHubメール以外の通知チャネル（ntfy等）
- 話題連動の成立率などの実績ダッシュボード
- night スロットのソフトエラー検査（collect_news 不使用のため対象なし）

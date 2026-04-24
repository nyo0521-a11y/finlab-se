# X（Twitter）自動投稿 運用ガイド

finlab-se.com の記事を X に自動投稿する仕組みです。B案（下書き → GitHub Issue 承認 → 投稿）で運用します。

## 投稿枠（1日2枠）

| 枠 | 時刻 (JST) | cron (UTC) | 担当 workflow | 発火条件 |
|---|---|---|---|---|
| 朝 | 07:30 毎日 | `30 22 * * *` | `x-post-scheduled` | キューの先頭を 1 件投稿（常時） |
| 夜 | 21:00 毎日 | `0 12 * * *` | `x-post-scheduled` | キュー残 ≥ 2 件の時のみ投稿。1 件以下なら rotation に譲る |
| 夜 | 21:00 月金 | `0 12 * * 1,5` | `x-rotation` | キュー残 < 2 件の時のみ既存記事リマインダー draft を作成 |

**設計意図**: 新記事告知（キュー）を優先しつつ、キューが薄いときは既存記事リマインダーで間を埋める。二重投稿が起きないよう、rotation 側でキュー残をチェックして skip する。

## 仕組みの全体像

```
[新記事を main に push]
     ↓
x-new-post-draft.yml
  → 追加された content/posts/*.md を検出
  → 投稿文を生成して draft Issue 作成（label: x-post-pending, x-post-new）
  → data/x-queue.yaml に post_path と issue_number を追記
     ↓
[ユーザーが承認: 👍/❤️/🎉/🚀 または /approve コメント]
     ↓
x-post-scheduled.yml (朝7:30 / 夜21:00 cron)
  → data/x-queue.yaml の先頭 Issue を拾う
  → 夜枠は キュー残 ≥ 2 でないと投稿しない
  → 承認済み & open なら投稿
  → 成功: Issue close + label 更新 + queue から削除 → commit & push
```

リマインダー側:

```
x-rotation.yml (月金 21:00 JST cron)
  → data/x-queue.yaml の残数チェック
    - 残 ≥ 2 件 → skip（x-post-scheduled が夜枠を使う）
    - 残 < 2 件 → rotation.yaml から1件選定して draft Issue 作成
  → [ユーザー承認]
  → 翌朝 7:30 または手動実行で投稿
```

## 初期セットアップ

### 1. X Developer Portal で API キー発行

- X API Free tier（月500 post write 可）
- OAuth 1.0a（User Context）
- 以下4値を取得:
  - API Key / API Secret / Access Token / Access Token Secret

### 2. GitHub Secrets に登録

| Secret 名 | 内容 |
|---|---|
| `X_API_KEY` | API Key |
| `X_API_SECRET` | API Secret |
| `X_ACCESS_TOKEN` | Access Token |
| `X_ACCESS_TOKEN_SECRET` | Access Token Secret |

### 3. キュー初期化（`x-queue-init`）

運用開始時、`data/x-queue.yaml` に `issue_number: null` で登録されている既存エントリを Issue 化する **1 回こっきりの workflow**。

手順:
1. Actions → `X Auto Post - Queue Init (one-shot)` → Run workflow
2. 対象エントリごとに draft Issue が作成され、yaml に番号が書き戻される
3. 各 Issue を承認すると、翌朝 7:30 から順次投稿される

通常運用では不要（新記事 push 時に `x-new-post-draft` が自動で Issue 作成＋enqueue するため）。

## 日常運用

### 新記事告知

1. 新記事を main に push（`content/posts/**.md`）
2. `x-new-post-draft` が数十秒以内に draft Issue 作成＋キュー追記
3. Issue 本文を確認、問題なければ 👍 / `/approve`
4. 朝 7:30 または（キュー残≥2の場合）夜 21:00 に自動投稿

### リマインダー

1. 月・金 21:00 に `x-rotation` が起動
2. キュー残 ≥ 2 件なら **skip**（新記事告知を優先）
3. キュー残 < 2 件なら rotation.yaml から1件選んで draft Issue 作成
4. 承認 → 翌朝 7:30 または手動起動で投稿

### アドホック投稿（初投稿・特別告知）

`x-adhoc-post.yml` は cron を待たず即座に投稿したい時に使う 2 段運用の workflow。キューや rotation には触らない。

**1 段目: draft Issue 作成**
1. Actions → `X Auto Post - Adhoc` → Run workflow
2. 入力:
   - `text`: 投稿本文（必須、改行可）
   - `image_path`: リポジトリ内画像パス（任意、例 `static/images/x/first-post-card.png`）
   - `issue_number`: **空欄のまま**
3. 実行すると draft Issue が作成される。ログに Issue URL が出る。

**2 段目: 承認後に投稿**
1. 作成された Issue に 👍 や `/approve` を付ける
2. Actions → `X Auto Post - Adhoc` → Run workflow
3. 入力:
   - `text`: **何でも OK**（2段目では使われない。Issue 本文から抽出される）
   - `image_path`: **何でも OK**（同上）
   - `issue_number`: 先ほど作成された Issue の番号
4. 承認チェック → 投稿 → Issue に結果コメント＋close

### 投稿文の編集

Issue 本文の ``` コードブロック内を書き換えてから承認する。投稿時は本文から抽出するので編集内容がそのまま使われる。

### キャンセル

Issue を close するだけで OK。`x-post-scheduled` は先頭エントリが closed だと「キューから除外」扱いでスキップする。

## 画像指定について

`post_to_x.py` はローカル画像パスと URL の両方に対応:
- `image_url` (http/https): ダウンロードしてアップロード
- `image_path` (リポジトリ内相対パス): そのままアップロード
- 両方あれば `image_url` 優先

新記事告知・rotation は記事 frontmatter の `cover.image` から `image_path` を自動抽出。adhoc は入力で直接指定。

## トラブル対応

### 投稿失敗した場合

- Issue に `x-post-failed` ラベルが付き、エラー内容がコメントされる
- 原因:
  - **429 Too Many Requests**: Free tier 月500上限超過
  - **403 Forbidden**: 認証情報か App permission
  - **duplicate content**: 同一本文を直近で投稿済み
- 対処後、Issue を re-open して `x-post-pending` ラベルを付け直す → 次回 cron で再試行

### rotation.yaml を手動編集

- 一時除外: `priority: low` にするか行削除
- 強制浮上: `last_promoted: null`

### 新記事を rotation 対象に追加

`x-new-post-draft` では rotation.yaml に自動追加しない（告知後に反応を見てから）。以下を手動追記:

```yaml
  - post_path: content/posts/xxxx.md
    last_promoted: null
    promote_count: 0
    priority: normal
```

## ファイル一覧

### Workflows

- `x-new-post-draft.yml` — 新記事 push → draft Issue + queue 追記
- `x-post-scheduled.yml` — 朝 7:30 / 夜 21:00 に queue 先頭を投稿
- `x-rotation.yml` — 月金 21:00 にリマインダー draft（queue 残 < 2 の時のみ）
- `x-adhoc-post.yml` — アドホック投稿（2 段運用: 作成 → 承認 → 再 dispatch）
- `x-queue-init.yml` — queue 内 `issue_number: null` の Issue を遡って作成（one-shot）

### Scripts

- `generate_post_text.py` — frontmatter → 投稿文
- `check_approval.py` — Issue 承認状態チェック
- `post_to_x.py` — X API 投稿（OAuth 1.0a + 画像、URL/ローカルパス両対応）
- `enqueue_post.py` — queue に追記
- `dequeue_and_post.py` — queue 先頭を拾って投稿
- `select_rotation.py` — rotation 次の1件選定
- `update_rotation.py` — rotation.yaml の last_promoted 更新

### Data

- `data/x-queue.yaml` — 新記事告知の FIFO キュー
- `data/x-rotation.yaml` — リマインダー ローテーション管理

## 注意事項

- 投稿は X API Free tier の月500件が上限。新記事告知 + 週2リマインダー = 月10件程度なので十分余裕あり
- Issue 本文の ``` コードブロック内がそのまま投稿されるため、編集時はバッククォートや改行に注意
- workflow_dispatch で手動起動時、`x-post-scheduled` の `slot` 入力を `morning` / `night` / `manual` で切り替え可
- queue 更新コミットは `github-actions[bot]` 名義。CF Pages の build ログにも出る

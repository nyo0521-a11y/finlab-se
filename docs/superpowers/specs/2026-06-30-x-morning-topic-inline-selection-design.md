# 朝のX話題連動投稿のサーバー化（インライン選定方式）設計

- 日付: 2026-06-30
- ステータス: 設計承認待ち（レビュー対象）
- 対象リポジトリ: finlab-se

## 1. 背景と課題

finlab-se.com の朝のX投稿は「その日のホットな話題に連動した既存記事のおすすめ」を出す。
現在、その**記事選定**だけがローカルの Claude Code スケジュールタスク（前夜22:00／当日6:30 の SKILL.md）に依存している。
これらは **PCが起動して Claude Code が動いているときしか実行されない**。

この構成が原因で、以下の事故が起きてきた（すべて中間ファイル `data/x-topic-pick.yaml` 起因）。

| 日付 | 事故 | 原因 |
|---|---|---|
| 6/20 | 朝が完全に無投稿 | `x-topic-pick.yaml` が二重pickでYAML破損 |
| 6/22・6/24 | 話題連動が失敗→おすすめに降格 | `x-topic-pick.yaml` への書き込みで画像パスが化けた（Git Bashのパス変換） |
| 全般 | 「準備したのに7時台で別物が出る」 | 準備時刻と投稿時刻がズレ、その間に状態が変わる／6:30タスクがPC都合で動かない |

なお、**投稿そのもの（朝・夜）はすでに完全にサーバー化されており PC は不要**。
PC依存なのは「朝の記事選定」だけである。

## 2. ゴールと非ゴール

### ゴール
- 朝の話題連動の記事選定を **PC起動に依存せず**、毎朝サーバー側で必ず実行する。
- 事故の温床だった中間ファイル `x-topic-pick.yaml` を**廃止**し、事故クラスごと消す。
- これまでの選定思想（客観ランキング起点・こじつけ禁止・直近重複回避）を維持する。

### 非ゴール（今回はやらない）
- 夜21:05の新着投稿ロジックの変更（対象外）。
- サイレント失敗の通知・可視化（任意・別途）。
- 投稿時刻の自動最適化（手動で cron を調整する運用は維持）。

## 3. 確定した設計判断（ブレインストーミングの結論）

1. **実行は朝の1回**に集約（前夜22:00の準備は廃止）。
2. 選定と投稿を分離せず、**7:30の投稿ワークフロー内で「ニュース取得→選定→即投稿」をインライン実行**する（中間ファイルなし）。
3. ニュースは**客観ソース**（Yahoo!ニュース経済アクセスランキング＋Google News RSS）を取得し、Claude に渡す（主観キーワード検索はしない）。
4. 記事選定は **Claude（Opus）** が担う。「候補を広げてから絞る」2段階方式。
5. 直近重複除外は **全投稿タイプ横断（新着・おすすめ・話題連動すべて）／直近7日**。
6. ローカルのスケジュールタスク2本（22:00／6:30）は**廃止**。
7. **投稿時刻は 7:30**（CF Workers の cron を JST 07:05 → 07:30 に変更）。

## 4. アーキテクチャ全体

```
CF Workers cron (JST 07:30・"30 22 * * *")
   │  workflow_dispatch (slot=morning)
   ▼
GitHub Actions: x-post-scheduled.yml (morning ジョブ)
   ▼
morning_post.py
   ├─ ① collect_news.py   … Yahoo!経済ランキング + Google News RSS を取得
   ├─ ② select_topic.py   … ①＋記事一覧＋除外リスト → Claude(Opus) → 選定結果(JSON)
   ├─ 選定あり → post_topic()  … その記事で投稿（画像は記事frontmatterから取得）
   └─ 該当なし/失敗 → post_rotation()  … 通常おすすめ（既存の安全装置）
```

投稿API・履歴記録・rotation台帳更新・多重起動防止（`morning_last_posted`）は**既存実装をそのまま流用**する。

## 5. コンポーネント設計

### 5.1 `collect_news.py`（新規・ニュース取得）

`news-collect` スキルの思想をサーバー用に翻訳する。WebFetch/Chrome は使えないため HTTP 取得に置き換える。

- 取得元1: **Yahoo!ニュース 経済アクセスランキング** `https://news.yahoo.co.jp/ranking/access/news/business`
  - `requests` で HTML を取得し、見出しを**順位つき**で抽出（上位10〜15件）。
- 取得元2: **Google News RSS（ビジネス）** `https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ja&gl=JP&ceid=JP:ja`
  - `requests` で XML を取得し、標準ライブラリ `xml.etree.ElementTree` で `<title>` を抽出。
- **ホットさの判定はこの係では行わない**。順位という生データだけ集め、②の Claude に渡す（主観排除のため）。
- 出力（stdout, JSON）: `{ "yahoo": [{rank, title, url}, ...], "google": [{title, url}, ...] }`
- 堅牢性: 片方が取得失敗しても、取れた方だけで続行。両方失敗なら `{ "yahoo": [], "google": [] }` を返す（②側で「ニュースなし→該当なし」と判断）。
- 依存ライブラリは `requests` のみ（標準ライブラリで完結。pytrends 等は入れない）。

### 5.2 `select_topic.py`（新規・Claude選定）

①の結果と記事一覧・除外リストを組み立て、Claude（Opus）を**1回**呼ぶ。

#### 入力の組み立て
1. **今日のホットな話題**: ①の出力（順位つき）。
2. **記事一覧**: `content/posts/*.md` の frontmatter から `{title, url, categories, tags, description}` を抽出。
   - `url` は slug から生成（`https://finlab-se.com/posts/<slug>/`。slug 未指定ならファイル名 stem）。
   - `x-rotation.yaml` で `exclude: true` の記事は最初から除外。
3. **今日は出さない記事（除外リスト）**: §7 のロジックで直近7日に投稿済みの post_path を集め、一覧から除く。

#### Claude への判断ルール（プロンプト本文）
- ホットさは**渡された順位を根拠に**判断する（自分でキーワードを作らない）。2ソース両方に上位で出る話題ほど優先。
- **「候補を広げてから絞る」2段階**で考える:
  - STEP1: ホットな話題を上位5件ランク付け。
  - STEP2: 各話題に「自然にマッチする記事候補」を挙げる（0件・複数件いずれも可）。
  - STEP3: マッチが成立した話題を**ホットな順**に見て、最上位話題の記事を採用。同一話題に複数候補があれば直近に出していない方を優先。
  - どの話題にも自然な記事が無ければ **「該当なし」**。
- **こじつけ禁止**（候補は広げるが、採用基準「自然にマッチ」は下げない）。
- 同じ話題に**別の記事で乗るのはOK**（既存方針）。
- 投稿文: **280字以内**（全角2字・半角1字・URL23字換算）・**1段落推奨**・煽り表現（爆益・億り人・必ず儲かる・○○一択）禁止・丁寧で論理的・ハッシュタグ1〜3個。
- URL形式: `https://finlab-se.com/posts/<slug>/`。

#### 出力（構造化・JSON）
```
成功:   { "selected_post_path": "content/posts/xxx.md",
          "text": "<投稿文>",
          "topic_reason": "<選定理由>",
          "candidates": [ {topic, rank, matched_posts:[...]}, ... ] }
該当なし: { "selected_post_path": null, "reason": "<理由>",
          "candidates": [...] }
```
- `candidates`（中間の候補リスト）も返させ、選定ログに残す（「なぜこの記事か」を後から検証可能にする）。

#### 投稿文の文字数検証
- 返ってきた `text` を `select_topic.py` 内で**280カウント検証**（全角2・半角1・URL23）。
- 超過していたら Claude に「280字以内に短く」と**1回だけ**再依頼。それでも超過なら `selected_post_path: null`（→ おすすめ降格）。

#### モデル
- **Claude Opus**（実装時点の最新 Opus。例: `claude-opus-4-8`）。`anthropic` Python SDK を使用。
- APIキーは環境変数 `ANTHROPIC_API_KEY`（GitHub Secrets 由来）。コードに直書きしない。

### 5.3 `morning_post.py`（改修）

- 現在の `get_valid_pick()`（`x-topic-pick.yaml` を読む）を、`select_topic_inline()` に**置き換える**。
- `select_topic_inline()` の処理:
  1. `collect_news.py` を subprocess 実行（`capture_output=True`）。
  2. ニュース結果を `select_topic.py` に渡して実行（`capture_output=True`）。
  3. 出力 JSON をパース。`selected_post_path` があり、かつ記事ファイルが存在すれば、
     `{post_path, text, image_path}` を返す。`image_path` は**選定記事の frontmatter `cover.image` を Python で直接読む**（中間ファイルを経由しないためパス化けは発生しない）。
  4. `null`・失敗・例外時は `None` を返す。
- `main()` の制御は既存のまま:
  - 選定あり → `post_topic()` → 失敗時は `post_rotation()` にフォールバック。
  - 選定なし → `post_rotation()`。
  - `morning_last_posted == today` の多重起動防止は維持。
- `clear_pick()` など pick 関連の補助関数は削除。

## 6. 既存資産の再利用

- 投稿: `post_to_x.py`（画像=v1.1 upload / 投稿=v2 /2/tweets）— 変更なし。
- 履歴: `append_post_history.py`（type=topic で記録）— 変更なし。
- rotation台帳更新: `update_rotation.py`（last_promoted 更新）— 変更なし。
- フォールバック: `rotation_post.py` / `select_rotation.py` — §7 の除外日数のみ変更。

## 7. 除外ロジック（全投稿タイプ横断・直近7日）

直近 N 日に**何らかの形で**Xに出した記事を、話題連動・おすすめ双方で候補から除外する。

- **2つの台帳の合わせ技**（既存の考え方を踏襲）:
  1. `x-rotation.yaml` の `last_promoted` が直近 N 日以内（新着・おすすめ・話題連動のどのタイプ投稿でも更新される）。
  2. `x-post-history.yaml` の `posted_at` が直近 N 日以内のエントリの `post_path`（type を問わず全件）。
- **N = 7**（現行3から変更）。`select_rotation.py` は環境変数 `ROTATION_EXCLUDE_DAYS` で制御済み。
  - ワークフローで `ROTATION_EXCLUDE_DAYS=7` を設定し、話題連動（`select_topic.py`）・おすすめ（`select_rotation.py`）で**同じ7日**を使う。
- 在庫評価: 記事72本・恒久除外2本＝実質70本。1日最大2投稿×7日＝最大14本除外でも**約56本（8割）が常に候補**に残る。おすすめ循環に支障なし。
- 全候補が除外で枯れた場合は、既存の安全弁（`select_rotation.py` の「全除外ならフォールバック」）で無投稿を回避。

## 8. エラーハンドリングとフォールバック

朝枠が無投稿になることは**絶対に起こさない**。以下のいずれが起きても通常おすすめ（rotation）に切り替える。

| 失敗 | 挙動 |
|---|---|
| ニュース取得が両ソースとも失敗 | 該当なし扱い → rotation |
| Claude API 失敗・タイムアウト | rotation |
| 出力JSONの破損・必須キー欠落 | rotation |
| 選定記事のファイルが存在しない | rotation |
| 投稿文が280字超（再依頼後もNG） | rotation |
| `post_topic()` 自体が投稿失敗 | rotation（既存フォールバック） |

## 9. 廃止対象

- `data/x-topic-pick.yaml`（中間ファイル）。
- `.github/scripts/set_topic_pick.py`。
- ローカルスケジュールタスク2本: `~/.claude/scheduled-tasks/x-morning-topic-pick-2200/`・`.../x-morning-topic-pick-0630/`。
- `x-post-scheduled.yml` 内の pick 関連 commit ステップ（pick を git add していた箇所）。
- `morning_post.py` の pick 読み込み・`clear_pick()` 関連コード。

## 10. 設定・シークレット・cron 変更

- **GitHub Secrets**: `ANTHROPIC_API_KEY` を追加（手動。手順は実装時に案内）。
- **ワークフロー依存**: `x-post-scheduled.yml` の `pip install` に `anthropic` を追加。`ROTATION_EXCLUDE_DAYS=7` を env に設定。
- **cron 変更**: `workers/x-post-trigger/`
  - `wrangler.toml` の `"5 22 * * *"` → `"30 22 * * *"`（JST 07:05 → 07:30）。
  - `src/index.js` の `case "5 22 * * *":` を `case "30 22 * * *":` に変更。
  - cron 本数は4本のまま（増やさない）。
  - 変更後 `wrangler deploy` が必要。

## 11. テスト方針

- `collect_news.py`: 取得元のHTML/XMLをモックし、見出し抽出・順位付け・片側失敗フォールバックを単体検証。
- `select_topic.py`: **dry-run モード**（実際に投稿せず選定結果JSONだけ出力）を用意し、実ニュース＋実記事一覧で「候補→採用」の妥当性を手元確認。文字数検証・280字超の再依頼・該当なし分岐をテスト。
- `morning_post.py`: 選定あり／該当なし／各種失敗時に rotation へ落ちることを、API/ニュースをモックして検証。
- 結合: ステージング的に dry-run で1日分を流し、投稿直前の text と image_path が正しいことを確認してから本番 cron を切り替える。

## 12. スコープ外（YAGNI）

- 失敗の通知・Issue自動起票（サイレント失敗の可視化）。必要になれば別途。
- 複数記事の同時投稿・スレッド化。
- 投稿時刻の自動最適化やA/Bテスト。

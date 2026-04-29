---
title: "Xの自動投稿で苦労した話——GitHubとCloudflareで作る定時投稿の仕組み"
date: 2026-04-29T08:00:00+09:00
draft: false
categories: ["AI活用"]
tags: ["X自動投稿", "GitHub Actions", "Cloudflare Workers", "ブログ運営", "API活用", "自動化"]
description: "ブログの流入経路を増やすためにXの自動投稿を仕組み化した際の試行錯誤を紹介。X API・GitHub・Cloudflare Workersがどのように連携して動くかを図解。最初にGitHub Actionsで時刻ズレに苦しんだ経験と、Cloudflare Workers移行で解決するまでの流れを解説します。"
showToc: true
cover:
  image: "/images/x-autopost-thumbnail.png"
  alt: "Xの自動投稿で苦労した話"
  relative: false
  hiddenInList: false
---

ブログを書いていると、「記事を書くだけでなく、もっと多くの人に届けたい」という気持ちが生まれてきます。

Google検索からの流入を増やすのは時間がかかります。そこで目を向けたのが、Xへの定期的な投稿です。ブログ記事の要点をXで発信することで、検索以外の流入経路を作れるのではないかと考えました。

ただ、1日2回投稿を手動で続けるのは現実的ではありません。そこで**Xの自動投稿を仕組み化**<!-- -->することにしました。

この記事を読み終える頃には、以下ができるようになっています。

- X自動投稿の仕組みに登場するツール・サービスの役割を理解できる
- 最初にはまったGitHub Actionsの時刻ズレ問題とその解決策を把握できる
- 実装のキーワードを知ることで、Claude Codeなどを活用して自分でも仕組みを作れる

なお、実装の細かいコードはClaude Codeに相談しながら作りました。この記事では「何がどう繋がって動くか」の全体像に絞って解説します。

## なぜX自動投稿をしようと思ったのか

ブログの流入経路は、現状ほぼGoogle検索一本です。SEOで順位が上がれば読者は増えますが、それには時間がかかります。

検索以外のルートとして考えたのがXです。投資・資産形成の話題は、XでもAアクティブに情報交換されています。ブログ記事の要点を短くまとめてXで発信することで、

- ブログを知らない人にリーチできる
- 記事へのリンクをXから踏んでもらえる

という効果が期待できます。

「1日2回投稿する」という目標を設定しましたが、毎日手動でやるのは続きません。であれば自動化してしまおう、というのが出発点です。

## 登場人物：どのツールが何をしているか

自動投稿の仕組みを作るにあたって、以下のツール・サービスが登場します。

{{< figure src="/images/x-autopost-cast.png" alt="X自動投稿の登場人物と役割：ブログ記事からGitHub・Cloudflare Workers・X APIを経てXに投稿される流れ" caption="左から右へ：ブログ記事の内容がCloudflare WorkersとX APIを通じてXに届く" >}}

### X API（X開発者プログラム）

Xに自動投稿するためには、**X APIという「外部からXを操作するための窓口」**<!-- -->を利用する必要があります。

X APIを使うには、Xの開発者プログラムに登録して認証キー（APIキーやアクセストークン）を取得する手順があります。料金体系はプランによって異なりますが、1日あたり数十投稿程度のライトな利用であれば費用を抑えられるプランを選べます。

### GitHub

ブログのソースコードをすでにGitHubで管理しているため、自動投稿のプログラム（スクリプト）もここに置くことにしました。

GitHubには**GitHub Actions**<!-- -->という自動化機能があり、「毎日○時にこのプログラムを実行する」という設定ができます。最初はこの機能を使って自動投稿を試みました。

### Cloudflare Workers

このブログはCloudflare Pagesというサービスでホスティングしています。Cloudflareには**Cloudflare Workers**<!-- -->という、サーバーレスでプログラムを実行できる環境があります。

ブログのインフラとして既に使っているCloudflareの中に、定時実行の仕組みも持てることがわかり、後にGitHub ActionsからCloudflare Workersに移行しました。

## 最初の設定：GitHub Actionsで試みた

まず試みたのは、**GitHubのCron（定時実行）機能を使ったGitHub Actionsによる自動投稿**<!-- -->です。

GitHub Actionsには「毎日8時と20時に実行する」といった設定を書くだけで定時実行ができる機能があります。設定ファイル（YAML形式）を書いてGitHubに置くだけなので、仕組みとしては比較的シンプルです。

しかし、**実際に動かしてみると大きな問題が発覚しました。**

### 問題：時刻のズレが大きすぎる

設定では「朝8時に投稿する」としていたにもかかわらず、実際に投稿される時刻が読めません。早ければ8時数分後、遅ければ11時になることもありました。

{{< figure src="/images/x-autopost-comparison.png" alt="GitHub Actions（時刻ズレあり）とCloudflare Workers（時刻安定）の仕組み比較図" caption="左：GitHub Actionsは混雑時に大幅な遅延が発生。右：Cloudflare Workersは±1分以内で安定" >}}

**なぜこうなるか？** GitHub Actionsのcronは、GitHubのサーバが混雑しているときにキュー（順番待ち）に入ります。無料枠・共有サーバの仕様上、ズレは「仕様の範囲内」とされており、保証はありません。多くのユーザが使う時間帯（UTCで整時など）は特に遅延しやすいことが知られています。

「投稿時刻を気にしなければいい」と思えればそれまでですが、SNS投稿のエンゲージメントはタイミングに左右される面があります。朝の通勤時間帯に届けたいのに昼以降に投稿されては意図通りになりません。

## 改善策：Cloudflare Workersに移行する

解決策として選んだのが、**GitHub ActionsからCloudflare Workersへのタイマー処理の移管**<!-- -->です。

投稿スクリプト自体（どんな文章をXに送るか）はGitHubで管理しつつ、そのスクリプトをデプロイして**定時実行するタイマーはCloudflare Workersに任せる**<!-- -->という構成に変えました。

Cloudflare WorkersにはCron Triggersという機能があり、指定した時刻に±1分以内で安定して実行されます。また、このブログのサーバと同じCloudflareのインフラ上で動くため、設定の一元管理という副次的なメリットもあります。

### 構成の全体像（改善後）

ここで正確に説明すると、Cloudflare Workersは「投稿コードをそのまま実行する」のではなく、**定刻にGitHub ActionsをAPI経由で呼び出す（workflow_dispatch）タイマー**<!-- -->として機能しています。投稿の実処理はGitHub Actions上のPythonスクリプトが担当し、APIキーもGitHub Secretsで安全に管理されています。

1. **Cloudflare Workers（Cron Triggers）**：朝・夜の指定時刻に起動し、GitHubのAPIを叩いてGitHub Actionsを起動する
2. **GitHub Actions（`x-post-scheduled`）**：起動されたら投稿キューの先頭を読み取り、X APIで投稿する
3. **X API**：リクエストを受け取りXに投稿する
4. **X**：フォロワーのタイムラインに届く

「タイマーの信頼性はCloudflare Workersに任せ、実処理はGitHub Actionsが行う」という役割分担です。

GitHub ActionsとCloudflare WorkersでCronの「確かさ」がこれほど違うとは、やってみるまで気づきませんでした。

## 補足：新記事を本番アップしたらGitHubが自動でキュー登録する

投稿タイミングの問題が解決したところで、次に考えたのが「何を投稿するか」の管理です。記事ごとに手動で投稿内容を書くのでは自動化の意味が薄れてしまいます。

そこで導入したのが**投稿キュー**<!-- -->という概念です。記事のパスを並べたYAMLファイル（`data/x-queue.yaml`）を用意し、Cloudflare Workersに呼び出されたGitHub Actionsがその先頭から1件ずつ取り出して投稿する、というFIFO（先入れ先出し）方式です。

```yaml
# data/x-queue.yaml のイメージ
queue:
  - post_path: content/posts/記事A.md
    added_at: '2026-04-29T11:00:00+09:00'
  - post_path: content/posts/記事B.md
    added_at: '2026-04-30T09:00:00+09:00'
```

さらに便利なのが、**記事を本番にアップした瞬間にGitHub Actionsが自動でこのキューに登録してくれる**<!-- -->仕組みです。`content/posts/`配下に新しいMarkdownファイルが追加されたことをGitHub Actionsのワークフロー（`x-new-post-enqueue`）が検知し、キューへの追記とコミットまで自動で行います。

```
新記事を content/posts/ にpush
    ↓
GitHub Actions（x-new-post-enqueue）が変更を検知
    ↓
data/x-queue.yaml に post_path を追記してコミット
    ↓
次の投稿スロット（朝7時台・夜21時台）にCloudflare WorkersがGitHub Actionsを起動
    ↓
キューの先頭から1件を取り出してX APIで投稿
```

「記事を公開したら勝手にXへの告知が予約される」という状態が実現しており、記事公開後にXへの投稿を忘れる心配がなくなりました。

## 実装のキーワード（Claude Codeを使えばできる）

細かい実装はClaude Codeに相談しながら進めました。「何を作ればいいか」を理解した上でClaude Codeに依頼すると、コードを書いてもらいながら仕組みを動かすことができます。

実装を進める際に登場するキーワードをまとめておきます。これらを知っておくと、Claude Codeに相談するときの言語化がしやすくなります。

| キーワード | 意味 |
|---|---|
| X API v2 | XをプログラムからWrite操作するためのAPI（第2世代） |
| OAuth 1.0a | X APIの認証方式。APIキー・シークレット・アクセストークンの4値で認証する |
| GitHub Actions | GitHubの自動化機能。YAMLで条件・処理を定義する |
| workflow_dispatch | GitHub Actionsを外部APIから手動/プログラムで起動するトリガー |
| Cloudflare Workers | Cloudflareのサーバーレス実行環境。JavaScriptで動く |
| Cron Triggers（Cloudflare） | Cloudflare Workersの定時実行機能。UTCで設定、±1分以内で安定 |
| Wrangler | Cloudflare WorkersのCLI（コマンドラインツール）。デプロイに使う |
| FIFO キュー（YAML） | 投稿待ちリスト。先に追加した記事から順番に投稿される |
| paths フィルター | GitHub Actionsの起動条件。特定ディレクトリへの変更だけをトリガーにできる |
| GitHub Secrets | APIキーなどの機密情報を暗号化して管理する仕組み。Actions内で環境変数として使える |

Claude Codeへの依頼例としては、次のような形が有効です。

> 「Cloudflare WorkersのCron Triggersを使って、毎日7時30分にGitHub ActionsをworkflowDispatchで起動するスクリプトを作ってください。GitHub APIのトークンはCloudflareの環境変数から読み込む形にしてください。起動されたGitHub Actionsは、data/x-queue.yamlの先頭エントリを読み取ってX APIで投稿し、投稿後はキューから削除してコミットする処理を行います。」

このような依頼文を出せれば、実装の骨格はClaude Codeが書いてくれます。

## まとめ

Xの自動投稿を仕組み化する上で経験した試行錯誤をまとめます。

- **目的**：ブログの流入経路を増やすため、1日2回のX定期投稿を自動化したかった
- **登場人物**：X API（投稿の窓口）・GitHub（コード管理・実処理）・Cloudflare Workers（タイマー）
- **最初の問題**：GitHub Actionsのcronは混雑時に大幅な時刻ズレが発生する
- **解決策**：Cloudflare WorkersのCron Triggersが定刻にGitHub Actions（workflow_dispatch）を呼び出す構成に変更。±1分以内の安定した定時実行を実現
- **自動キュー登録**：記事を本番に公開するとGitHub Actionsが自動検知し、投稿キュー（YAML）に追記。次のスロットで自動投稿される

「自動化したい」という気持ちはあっても、どのツールが何をするのかが見えていないと最初の一歩が踏み出しにくいものです。この記事の図解で全体像が掴めた方は、ぜひClaude Codeを使った実装も試してみてください。

何かの参考になれば幸いです。

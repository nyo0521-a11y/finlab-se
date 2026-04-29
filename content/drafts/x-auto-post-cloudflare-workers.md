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

ただ、1日2回投稿を手動で続けるのは現実的ではありません。そこで**Xの自動投稿を仕組み化**することにしました。

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

Xに自動投稿するためには、**X APIという「外部からXを操作するための窓口」**を利用する必要があります。

X APIを使うには、Xの開発者プログラムに登録して認証キー（APIキーやアクセストークン）を取得する手順があります。料金体系はプランによって異なりますが、1日あたり数十投稿程度のライトな利用であれば費用を抑えられるプランを選べます。

### GitHub

ブログのソースコードをすでにGitHubで管理しているため、自動投稿のプログラム（スクリプト）もここに置くことにしました。

GitHubには**GitHub Actions**という自動化機能があり、「毎日○時にこのプログラムを実行する」という設定ができます。最初はこの機能を使って自動投稿を試みました。

### Cloudflare Workers

このブログはCloudflare Pagesというサービスでホスティングしています。Cloudflareには**Cloudflare Workers**という、サーバーレスでプログラムを実行できる環境があります。

ブログのインフラとして既に使っているCloudflareの中に、定時実行の仕組みも持てることがわかり、後にGitHub ActionsからCloudflare Workersに移行しました。

## 最初の設定：GitHub Actionsで試みた

まず試みたのは、**GitHubのCron（定時実行）機能を使ったGitHub Actionsによる自動投稿**です。

GitHub Actionsには「毎日8時と20時に実行する」といった設定を書くだけで定時実行ができる機能があります。設定ファイル（YAML形式）を書いてGitHubに置くだけなので、仕組みとしては比較的シンプルです。

しかし、**実際に動かしてみると大きな問題が発覚しました。**

### 問題：時刻のズレが大きすぎる

設定では「朝8時に投稿する」としていたにもかかわらず、実際に投稿される時刻が読めません。早ければ8時数分後、遅ければ11時になることもありました。

{{< figure src="/images/x-autopost-comparison.png" alt="GitHub Actions（時刻ズレあり）とCloudflare Workers（時刻安定）の仕組み比較図" caption="左：GitHub Actionsは混雑時に大幅な遅延が発生。右：Cloudflare Workersは±1分以内で安定" >}}

**なぜこうなるか？** GitHub Actionsのcronは、GitHubのサーバが混雑しているときにキュー（順番待ち）に入ります。無料枠・共有サーバの仕様上、ズレは「仕様の範囲内」とされており、保証はありません。多くのユーザが使う時間帯（UTCで整時など）は特に遅延しやすいことが知られています。

「投稿時刻を気にしなければいい」と思えればそれまでですが、SNS投稿のエンゲージメントはタイミングに左右される面があります。朝の通勤時間帯に届けたいのに昼以降に投稿されては意図通りになりません。

## 改善策：Cloudflare Workersに移行する

解決策として選んだのが、**GitHub ActionsからCloudflare Workersへのタイマー処理の移管**です。

投稿スクリプト自体（どんな文章をXに送るか）はGitHubで管理しつつ、そのスクリプトをデプロイして**定時実行するタイマーはCloudflare Workersに任せる**という構成に変えました。

Cloudflare WorkersにはCron Triggersという機能があり、指定した時刻に±1分以内で安定して実行されます。また、このブログのサーバと同じCloudflareのインフラ上で動くため、設定の一元管理という副次的なメリットもあります。

### 構成の全体像（改善後）

1. **GitHub**：投稿スクリプト（コード）を管理する
2. **Cloudflare Workers**：スクリプトを受け取り、Cron Triggersで定時に実行する
3. **X API**：Cloudflare Workersからのリクエストを受け取り、Xに投稿する
4. **X**：フォロワーのタイムラインに届く

GitHub ActionsとCloudflare WorkersでCronの「確かさ」がこれほど違うとは、やってみるまで気づきませんでした。

## 実装のキーワード（Claude Codeを使えばできる）

細かい実装はClaude Codeに相談しながら進めました。「何を作ればいいか」を理解した上でClaude Codeに依頼すると、コードを書いてもらいながら仕組みを動かすことができます。

実装を進める際に登場するキーワードをまとめておきます。これらを知っておくと、Claude Codeに相談するときの言語化がしやすくなります。

| キーワード | 意味 |
|---|---|
| X API v2 | XをプログラムからReader/Write操作するためのAPI（第2世代） |
| OAuth 2.0 / Bearer Token | X APIの認証方式。APIキーとトークンを使ってアクセスを許可する |
| GitHub Actions（Cron） | GitHubの定時実行機能。YAMLで設定する |
| Cloudflare Workers | Cloudflareのサーバーレス実行環境。JavaScriptで動く |
| Cron Triggers（Cloudflare） | Cloudflare Workersの定時実行機能。UTCで設定する |
| Wrangler | Cloudflare WorkersのCLI（コマンドラインツール）。デプロイに使う |
| 環境変数（Secrets） | APIキーなどの機密情報をコードに直接書かずに管理する仕組み |

Claude Codeへの依頼例としては、次のような形が有効です。

> 「Cloudflare WorkersのCron Triggersを使って、毎日8時と20時にX API v2で固定のツイートを投稿するスクリプトを作ってください。APIキーはCloudflareの環境変数から読み込む形にしてください。」

このような依頼文を出せれば、実装の骨格はClaude Codeが書いてくれます。

## まとめ

Xの自動投稿を仕組み化する上で経験した試行錯誤をまとめます。

- **目的**：ブログの流入経路を増やすため、1日2回のX定期投稿を自動化したかった
- **登場人物**：X API（投稿の窓口）・GitHub（コード管理）・Cloudflare Workers（定時実行環境）
- **最初の問題**：GitHub Actionsのcronは混雑時に大幅な時刻ズレが発生する
- **解決策**：Cloudflare WorkersのCron Triggersに移行することで±1分以内の安定した定時実行を実現

「自動化したい」という気持ちはあっても、どのツールが何をするのかが見えていないと最初の一歩が踏み出しにくいものです。この記事の図解で全体像が掴めた方は、ぜひClaude Codeを使った実装も試してみてください。

何かの参考になれば幸いです。

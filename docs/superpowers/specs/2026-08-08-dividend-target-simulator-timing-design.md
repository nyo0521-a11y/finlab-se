# 配当目標逆算シミュレーター改修設計書（投資タイミング分離・実物対応版）

## 背景

前回の設計検討は誤ったファイル（`finlab-se` リポジトリ外の別ファイル）を対象にしていたことが判明したため、実際に `https://finlab-se.com/tools/dividend-target-simulator/` として公開されているソース（`static/tools/dividend-target-simulator/index.html`、このリポジトリ内）を読み直し、設計を作り直す。

ChatGPTによるレビューの趣旨（今後投資予定の資金にまで増配成長をフルに見込むと必要利回りを甘く見積もる）は実物のコードにも当てはまる。ただし実物は以下の点でレビュー時の想定と異なっていた：

- 「月の入金額」という項目は存在せず、既に「今後の入金額（累計）」という一括金額の入力になっている（`index.html:342-347`）
- チャート注釈に「今後の入金額を t=0 で一括投入する前提」と明記済み（`index.html:429`）。ただし入力欄から離れたチャート下の小さい注釈のみで、目立たない
- 「現在の年間配当額（税引前）」という既存ポートフォリオの受取配当を増配率で伸ばして目標から差し引くロジックが既に実装されている（`index.html:493-511`）。これは正しい実装で変更不要
- レビュー指摘②（上限超入力時の表示と計算の不整合）は実際に存在するバグ：目標配当額の数値入力（`n_target`）は1,200万円超を入力すると内部計算は上限(600万円)に丸められるが、入力欄の表示自体は書き換わらない（`index.html:799-804`、`els.nTarget.value = v` の書き戻しが漏れている）

## 目的・方針

運営者の投資哲学（高配当株投資はタイミング投資であり、DCA=毎月コツコツ積立ではない）に基づき、「今後の入金額（累計）」を以下の2区分に分割する：

- **A: 今すぐ投資できる金額** — 投資期間まるまる増配成長を見込む
- **B: 今後投資予定額（時期未定・累計）** — 投資タイミングが未定のため、控えめに投資期間の半分の期間だけ増配成長を見込む

「現在の年間配当額」（既存保有分の受取配当）は変更しない（既に投資済みでフル成長が正しいため）。

併せて、レビュー指摘②の入力欄同期バグも本改修で修正する。

## 計算式の変更

現行（`index.html:493-511`）:
```
targetPretax = 税引前換算後の目標額
growthFactor = (1+g)^years
targetTodayBasis = targetPretax / growthFactor
remainingNeeded = targetTodayBasis - current
y = remainingNeeded / future * 100        // future: 今後の入金額（累計、単一値）
yAtN = y * growthFactor
```

変更後:
```
targetPretax = 税引前換算後の目標額（変更なし）
growthFull = (1+g)^years
growthHalf = (1+g)^(years/2)
currentAtN = current * growthFull          // 既存配当のN年後成長額
remainingAtN = targetPretax - currentAtN   // N年後時点で新規資金が稼ぐべき配当額

A = 今すぐ投資できる金額（新規入力）
B = 今後投資予定額（時期未定・累計、既存の future を改名）
investedAtN = A * growthFull + B * growthHalf

if (A + B <= 0):
    remainingAtN <= 0 ? 達成済み(0%) : Infinity
elif remainingAtN <= 0:
    達成済み(0%)
else:
    y = remainingAtN / investedAtN * 100   // 必要利回り（現在時点で買うべき利回り）
```

`y` の意味は「今すぐ買うべき配当利回り」のまま変わらない。Aはフル成長・Bは半期間成長という重み付けだけが変わる。

## UI変更

### 入力欄（`index.html` セクション02「入金・期間」）

- 既存の `n_future`（今後の入金額・累計）フィールドを2つに分割:
  - 新規: 「今すぐ投資できる金額」`n_futureNow`（today's investable capital、A）
  - 既存を改名: 「今後投資予定額（時期未定・累計）」`n_futureLater`（旧`n_future`、B）
- 両方とも既存の `n_future` と同じスタイル・制約（min=0, max=100000, step=10, 万円）を踏襲

### 感度マトリクス（セクション05）

- 現行は行=今後の入金額（future の±30%）、列=投資期間の3×3
- 変更後は行=B（futureLaterの±30%）、Aは現在の入力値で固定
- 行見出しに「B額」と「A+B合計額」を併記（例: 「700万<br><span>(合計1,200万)</span>」）

### チャート（セクション06）

- 棒グラフ（累計入金額、Y0のみ）は `A + B`（増配成長前の単純合計）を表示
- 折れ線（年間配当額）は新しい計算式に従って自動更新
- 注釈文を「A（今すぐ投資できる金額）は投資期間まるまる、B（今後投資予定額）は時期未定のため投資期間の半分だけ増配成長を見込む」という趣旨に更新し、**入力欄の近く（セクション02の下）にも同趣旨の短い説明を追加**して目立たない問題を解消する

### バグ修正（レビュー指摘②）

`index.html:799-804` の `els.nTarget` の `input` イベントリスナーに `els.nTarget.value = v;` を追加し、上限クランプ後の値を入力欄の表示にも反映する。

## スコープ外（今回対応しない）

- 税引後モードの口座区分（NISA/特定口座）対応 — 一律20.315%換算のまま維持
- 判定ラベル（現実的／要努力／利回り罠リスク／達成困難）への一般的な断り書き追加
- 「現在の年間配当額」欄・その他の入力欄の上限超同期バグ（`n_current`, `n_futureNow`, `n_futureLater`, `r_years` は元々 `els.nTarget.value=v` のような書き戻しが不要な設計＝スライダー経由や `clamp()` のみのため対象外。対象は `n_target` の数値入力欄のみ）

## 影響ファイル

- `C:/Users/oui_k/OneDrive/finlab-se/static/tools/dividend-target-simulator/index.html`（1ファイル完結）

## デプロイ

`static/` はHugoのstaticディレクトリで、ビルド後 `public/tools/dividend-target-simulator/` に配置される（`public/`, `_staging/` は`.gitignore`対象のビルド生成物）。デプロイ手順は既存のfinlab-seデプロイフロー（`docs/`配下の手順書があれば参照、なければユーザーに確認）に従う。今回の実装計画はコード変更のみをスコープとし、デプロイは実装完了後に別途行う。

# 配当目標逆算シミュレーター 再指摘対応 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ChatGPT再レビューで指摘された5件（税引後モードとチャートの不整合、累計投資額グラフのタイミング不整合、入力欄3箇所の上限同期漏れ、説明文2箇所の不正確な表現）を修正する。

**Architecture:** 単一HTMLファイル内の素のJS。`buildChartData()`の税金・タイミング処理を修正し、`n_current`/`n_futureNow`/`n_futureLater`のイベントリスナーに既存の`n_target`パターンを横展開し、2箇所の説明文言を修正する。自動テストなし。各タスクの最後にブラウザで手動確認する。

**Tech Stack:** HTML / CSS / Vanilla JavaScript / Chart.js 4.4.1（CDN）

## Global Constraints

- 対象ファイルは `static/tools/dividend-target-simulator/index.html` の1ファイルのみ
- 税引後モード時、チャートの配当額系列（`divArr`）は`NET_FACTOR`(0.79685)で税引後換算する。投資元本系列（`principalArr`）は換算しない
- 累計投資額グラフは `t=0` に `A`（`state.futureNow`）のみ、`t=Math.ceil(state.years/2)` に `A+B`（`state.futureNow+state.futureLater`）を描画する（それ以外は`null`のまま、既存の疎データパターンを維持）
- `Math.ceil(state.years/2)`は既存の`divFutureLater`のB発生条件（`t < state.years/2`が偽になる最初の整数年）と一致させること
- 上限同期パターンは既存の`n_target`実装（`index.html:822-832`）と完全に同じ構造にする: `input`イベントで上限超過時のみ即時書き戻し、`change`イベントで最終的な状態値に正規化
- スコープ外: 税引後の口座区分対応、判定ラベルへの断り書き追加

---

### Task 1: 税引後モードとチャート金額の整合

**Files:**
- Modify: `static/tools/dividend-target-simulator/index.html:713-739`（JS: buildChartData関数）

**Interfaces:**
- Consumes: 既存の`state.isAfterTax`, `NET_FACTOR`（`index.html:494`付近で定義済み）, `calcRequiredYield(state)`
- Produces: `buildChartData()`の戻り値`divArr`が税引後モード時は税引後換算された値になる（後続タスクなし、Task 2が同じ関数の別部分を修正するため、その前提として必要）

- [ ] **Step 1: buildChartData() の div 計算部分に税引後換算を追加する**

`static/tools/dividend-target-simulator/index.html`の713-739行目を以下に置き換える（`principal`関連の計算はTask 2で別途変更するため、ここでは既存のまま維持しつつ`div`計算にのみ税引後換算を加える）:

```javascript
// ----- chart -----
let chart = null;
function buildChartData(){
  const labels = [], principalArr = [], divArr = [];
  // このツールは「A(今すぐ投資できる金額)をいま投資、B(今後投資予定額)は時期未定のため
  // 投資期間の中間時点から増配成長」という前提で必要利回りを逆算しているので、
  // チャートもその前提に沿って t=0 時点の投資元本と、年ごとの配当額を描く。
  const r = calcRequiredYield(state);
  const yNow = isFinite(r.y) ? r.y / 100 : 0;
  const g = state.growth / 100;
  const taxFactor = state.isAfterTax ? NET_FACTOR : 1; // 税引後モードならチャートの配当額も税引後換算する
  for(let t = 0; t <= state.years; t++){
    labels.push('Y' + t);
    // 累計投資額（A+B、増配成長前の単純合計）は t=0 のみ表示
    const principal = state.futureNow + state.futureLater;
    // A分の配当：yNowで買った利回りが年数分フルに増配成長
    const divFutureNow = state.futureNow * yNow * Math.pow(1 + g, t);
    // B分の配当：投資タイミングが未定のため、投資期間の半分までは寄与ゼロとし、
    // そこから残り半分の期間で増配成長する（t=years時点でA同様のフル成長と同じ値に収束）
    const divFutureLater = t < state.years / 2
      ? 0
      : state.futureLater * yNow * Math.pow(1 + g, t - state.years / 2);
    // 現在配当も同じ増配率で成長
    const divCurrent = state.current * Math.pow(1 + g, t);
    const div = (divFutureNow + divFutureLater + divCurrent) * taxFactor;
    principalArr.push(t === 0 ? Math.round(principal) : null);
    divArr.push(Math.round(div * 10) / 10);
  }
  return { labels, principalArr, divArr };
}
```

（`principalArr`の計算はこの時点では変更せず、Task 2でのみ変更する。このステップの差分は`taxFactor`の追加と`div`計算式の末尾に`* taxFactor`を掛ける部分のみ）

- [ ] **Step 2: ブラウザで手動確認する**

`preview_start`で`{name: "finlab-static"}`を起動し、`http://localhost:3478/tools/dividend-target-simulator/`を開く。以下を設定する:

- 税引:「税引後」を選択
- 目標年間配当額: 120万円
- 現在の年間配当額: 0
- 今すぐ投資できる金額: 500万円
- 今後投資予定額: 700万円
- 投資期間: 15年
- 想定増配率: 3%

期待値（手計算）:
- `targetPretax = 120 / 0.79685 ≈ 150.59`
- 必要利回り（前回の検証と同じロジック）: `y ≈ 150.59 / (500×1.03^15 + 700×1.03^7.5) ≈ 150.59/1652.0 ≈ 9.12%`
- チャートのY15（最終年）の配当額表示: `div[15](税引前) ≈ targetPretax ≈ 150.6` を `× NET_FACTOR(0.79685)` した **約120.0万円**（入力した目標額と一致することを確認）

Chart.jsの内部データを読む場合は`javascript_tool`で`chart.data.datasets[1].data`を読み取り確認してよい（読み取り専用、UI操作の代替としてのみ使用）。コンソールにエラーが出ていないことも確認する。

- [ ] **Step 3: コミット**

```bash
git add static/tools/dividend-target-simulator/index.html
git commit -m "$(cat <<'EOF'
配当目標逆算シミュレーター: 税引後モード時はチャートの配当額も税引後換算する
EOF
)"
```

---

### Task 2: 累計投資額グラフをBの投資タイミングに合わせる

**Files:**
- Modify: `static/tools/dividend-target-simulator/index.html`（Task 1で変更した`buildChartData()`の`principal`関連部分。Task 1のコミット後の行番号で該当箇所を検索すること）

**Interfaces:**
- Consumes: Task 1で確定した`buildChartData()`の構造、`state.futureNow`, `state.futureLater`, `state.years`
- Produces: `principalArr`が2点（`t=0`にA、`t=Math.ceil(years/2)`にA+B）を持つ配列になる（後続タスクなし）

- [ ] **Step 1: principalArr の計算を2点描画に変更する**

`buildChartData()`内の以下の行（Task 1のコミット後、`// 累計投資額（A+B、増配成長前の単純合計）は t=0 のみ表示`というコメントの行と、それに続く`const principal = state.futureNow + state.futureLater;`の行、および末尾の`principalArr.push(...)`の行）を探し、以下のロジックに置き換える:

ループの外側（`for`ループの直前）に以下を追加する:
```javascript
  const principalMidT = Math.ceil(state.years / 2); // Bの投資が実行されたとみなす年（divFutureLaterの発生条件と一致させる）
```

ループ内の該当行を以下に置き換える:
```javascript
    // 累計投資額：Y0はA(今すぐ投資できる金額)のみ、B(今後投資予定額)が実行される中間時点でA+Bに切り替わる
    let principalPoint = null;
    if (t === 0) principalPoint = state.futureNow;
    else if (t === principalMidT) principalPoint = state.futureNow + state.futureLater;
```

そして`principalArr.push(...)`の行を以下に置き換える:
```javascript
    principalArr.push(principalPoint !== null ? Math.round(principalPoint) : null);
```

（`const principal = state.futureNow + state.futureLater;`の行は不要になるため削除する）

- [ ] **Step 2: ブラウザで手動確認する**

Task 1の入力値のまま（税引後・目標120万・現在0・A=500・B=700・15年・3%）確認する。`Math.ceil(15/2) = 8`。

- `javascript_tool`で読み取り専用に`chart.data.datasets[0].data`を確認し、インデックス0（Y0）が`500`、インデックス8（Y8）が`1200`、それ以外が`null`になっていることを確認する
- コンソールにエラーが出ていないこと
- 投資期間を14年に変更し、`Math.ceil(14/2)=7`なのでインデックス7（Y7）が`1200`になることも確認する（境界値の動作確認）

- [ ] **Step 3: コミット**

```bash
git add static/tools/dividend-target-simulator/index.html
git commit -m "$(cat <<'EOF'
配当目標逆算シミュレーター: 累計投資額グラフをY0=A、B投資実行時点=A+Bの2点表示に変更
EOF
)"
```

---

### Task 3: 入力欄の上限同期修正と説明文の言い回し修正

**Files:**
- Modify: `static/tools/dividend-target-simulator/index.html:845-860`（JS: n_current/n_futureNow/n_futureLaterのイベントリスナー）
- Modify: `static/tools/dividend-target-simulator/index.html:356`（HTML: Bの増配成長の説明文）
- Modify: `static/tools/dividend-target-simulator/index.html:294`（HTML: イントロ文の「いま買うべき」表現）
- Modify: `static/tools/dividend-target-simulator/index.html:388`（HTML: 結果ヒーローセクションのリード文）

**Interfaces:**
- Consumes: 既存の`clamp(v, lo, hi)`関数（`index.html:814`）、既存の`n_target`の実装パターン（`index.html:822-832`）
- Produces: なし（最終タスク）

- [ ] **Step 1: n_current のイベントリスナーを書き換える**

`static/tools/dividend-target-simulator/index.html`の以下のブロック（`// current dividend (税引前 万円/年)`というコメントの直後）:

```javascript
els.nCurrent.addEventListener('input', () => {
  state.current = clamp(+els.nCurrent.value || 0, 0, 10000);
  update();
});
```

を以下に置き換える:

```javascript
els.nCurrent.addEventListener('input', () => {
  const raw = +els.nCurrent.value;
  const v = clamp(raw || 0, 0, 10000);
  state.current = v;
  if (raw > 10000) els.nCurrent.value = v;
  update();
});
els.nCurrent.addEventListener('change', () => {
  els.nCurrent.value = state.current;
});
```

- [ ] **Step 2: n_futureNow のイベントリスナーを書き換える**

```javascript
els.nFutureNow.addEventListener('input', () => {
  state.futureNow = clamp(+els.nFutureNow.value || 0, 0, 100000);
  update();
});
```

を以下に置き換える:

```javascript
els.nFutureNow.addEventListener('input', () => {
  const raw = +els.nFutureNow.value;
  const v = clamp(raw || 0, 0, 100000);
  state.futureNow = v;
  if (raw > 100000) els.nFutureNow.value = v;
  update();
});
els.nFutureNow.addEventListener('change', () => {
  els.nFutureNow.value = state.futureNow;
});
```

- [ ] **Step 3: n_futureLater のイベントリスナーを書き換える**

```javascript
els.nFutureLater.addEventListener('input', () => {
  state.futureLater = clamp(+els.nFutureLater.value || 0, 0, 100000);
  update();
});
```

を以下に置き換える:

```javascript
els.nFutureLater.addEventListener('input', () => {
  const raw = +els.nFutureLater.value;
  const v = clamp(raw || 0, 0, 100000);
  state.futureLater = v;
  if (raw > 100000) els.nFutureLater.value = v;
  update();
});
els.nFutureLater.addEventListener('change', () => {
  els.nFutureLater.value = state.futureLater;
});
```

- [ ] **Step 4: Bの増配成長の説明文を修正する**

`index.html:356`の以下の行:

```html
        <div class="hint" style="margin-top:4px">「今すぐ投資できる金額」は投資期間まるまる増配成長を見込みます。「今後投資予定額」は投資タイミングが未定のため、控えめに投資期間の半分の期間だけ増配成長したものとして計算します。</div>
```

を以下に置き換える:

```html
        <div class="hint" style="margin-top:4px">「今すぐ投資できる金額」は投資期間まるまる増配成長を見込みます。「今後投資予定額」は投資タイミングが未定のため、便宜上、投資期間の中間時点で一括投資したものとして計算します。</div>
```

- [ ] **Step 5: 「いま買うべき」表現を2箇所修正する**

`index.html:294`の以下の行:

```html
  <p>「年◯◯万円の配当が欲しい」というゴールから、<b>いま買うべき平均配当利回り</b>を逆算します。投資できる金額・投資期間・増配率を動かしながら、現実的な達成プランを探してください。</p>
```

を以下に置き換える:

```html
  <p>「年◯◯万円の配当が欲しい」というゴールから、<b>目標達成に必要な平均配当利回り</b>を逆算します。投資できる金額・投資期間・増配率を動かしながら、現実的な達成プランを探してください。</p>
```

`index.html:388`の以下の行:

```html
          <div class="lead">あなたの目標に届くために、いま買うべき</div>
```

を以下に置き換える:

```html
          <div class="lead">あなたの目標に届くために、必要な</div>
```

- [ ] **Step 6: ブラウザで手動確認する**

`http://localhost:3478/tools/dividend-target-simulator/`で以下を確認する:

- 現在の年間配当額に`20000`と入力し、フォーカスを外す（blur/Tab等）と表示が`10000`に正規化されること
- 今すぐ投資できる金額に`200000`と入力し、フォーカスを外すと`100000`に正規化されること
- 今後投資予定額に`200000`と入力し、フォーカスを外すと`100000`に正規化されること
- いずれの欄も、入力中（フォーカスがある間）は上限超の値を入力しても即座に強制的な書き換えが起きない（＝上限を超えていても打ち終わるまで自由に編集できる）こと（`n_target`と同じ挙動）
- セクション02の説明文が「便宜上、投資期間の中間時点で一括投資」という文言になっていること
- イントロ文が「目標達成に必要な平均配当利回り」、結果ヒーローセクションが「あなたの目標に届くために、必要な」になっていること
- コンソールにエラーが出ていないこと

- [ ] **Step 7: コミット**

```bash
git add static/tools/dividend-target-simulator/index.html
git commit -m "$(cat <<'EOF'
配当目標逆算シミュレーター: 現在配当/A/B入力欄の上限同期を追加し、説明文言を修正

n_targetと同じ「上限超は即時同期・下限はblur時に正規化」パターンを横展開。
Bの増配成長説明と「いま買うべき」表現をより正確な言い回しに修正。
EOF
)"
```

---

## 実装後の残タスク（このプランの範囲外・ユーザー確認事項）

- `main`へのマージ後、`git push origin main`でCloudflare Pagesへの自動デプロイ
- デプロイ後、本番URLで実機確認

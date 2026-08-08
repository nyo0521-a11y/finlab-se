# 配当目標逆算シミュレーター タイミング分離（実物対応） 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `static/tools/dividend-target-simulator/index.html` の必要利回り計算を、「今すぐ投資できる金額（A・投資期間まるまる増配成長）」と「今後投資予定額（B・時期未定のため期間半分の増配成長）」に分割し、UI・感度マトリクス・チャート・注釈文を更新する。併せてChatGPTレビュー指摘②（目標配当額入力欄の上限クランプ後、表示が同期しないバグ）を修正する。

**Architecture:** 単一HTMLファイル内の素のJS（フレームワークなし、Chart.js CDN読み込み）。既存の `state.future` を廃止し `state.futureNow`（A）・`state.futureLater`（B）を新設。`calcRequiredYield()` のロジックを変更し、呼び出し元（`update()` / `drawHeatmap()` / `buildChartData()`）を追従させる。自動テストなし。各タスクの最後にブラウザで手動確認する。

**Tech Stack:** HTML / CSS / Vanilla JavaScript / Chart.js 4.4.1（CDN）

## Global Constraints

- 対象ファイルは `static/tools/dividend-target-simulator/index.html` の1ファイルのみ
- 計算式: `y = remainingAtN / (A × (1+g)^n + B × (1+g)^(n/2)) × 100`、`remainingAtN = targetPretax - current × (1+g)^n`（設計書 `docs/superpowers/specs/2026-08-08-dividend-target-simulator-timing-design.md` と厳密に一致させる）
- `A + B <= 0` の場合: `remainingAtN <= 0` なら達成済み(`y=0`)、そうでなければ `Infinity`（現行の `totalInvested <= 0` 分岐と同じ扱いを維持）
- `remainingAtN <= 0` の場合（Aが正でも）: 達成済み(`y=0`)（現行の分岐を維持）
- 既存の変数命名規則（`state.xxx`、`els.xxx`、キャメルケース）・インデント（2スペース）に合わせる
- 感度マトリクスの行見出しはB額とA+B合計額を2行で表示する
- スコープ外: 税引後モードの口座区分対応、判定ラベルへの一般的断り書き追加、`n_current`/`r_years`等の他の入力欄の同期修正（`n_target`のみが対象）

---

### Task 1: 計算エンジンとメイン入力欄をA/B方式に変更する

**Files:**
- Modify: `static/tools/dividend-target-simulator/index.html:341-347`（HTML: 既存の「今後の入金額（累計）」フィールドをA/B2つに分割）
- Modify: `static/tools/dividend-target-simulator/index.html:474-481`（JS: state）
- Modify: `static/tools/dividend-target-simulator/index.html:486-511`（JS: calcRequiredYield）
- Modify: `static/tools/dividend-target-simulator/index.html:604-624`（JS: els 参照）
- Modify: `static/tools/dividend-target-simulator/index.html:627-654`（JS: update()）
- Modify: `static/tools/dividend-target-simulator/index.html:822-826`（JS: future用イベントリスナー）

**Interfaces:**
- Consumes: なし（Task 1が起点）
- Produces:
  - `state.futureNow`（number, 万円, A: 今すぐ投資できる金額。初期値500）
  - `state.futureLater`（number, 万円, B: 今後投資予定額・時期未定・累計。旧`state.future`を置き換え、初期値1500）
  - `calcRequiredYield(s)` — 引数は変更なし（`s`オブジェクトを受け取る形は維持）だが、内部で `s.futureNow` と `s.futureLater` を使う。戻り値の形は変更なし: `{ y, yAtN, totalInvested, targetPretax, achieved? }`。`totalInvested` は `A×(1+g)^n + B×(1+g)^(n/2)` の値を返す
  - HTML要素 `id="n_futureNow"`（今すぐ投資できる金額の数値入力、min=0, max=100000, step=10, value=500）と `id="n_futureLater"`（今後投資予定額、min=0, max=100000, step=10, value=1500）が新設される。`id="n_future"` は削除される

- [ ] **Step 1: HTMLの入力欄を書き換える**

`static/tools/dividend-target-simulator/index.html` の341-347行目を以下に置き換える:

```html
        <label class="field">
          <span class="lbl">今すぐ投資できる金額</span>
          <div class="suffix">
            <input type="number" id="n_futureNow" value="500" min="0" max="100000" step="10" />
            <span class="unit">万円</span>
          </div>
        </label>

        <label class="field" style="margin-top:10px">
          <span class="lbl">今後投資予定額（時期未定・累計）</span>
          <div class="suffix">
            <input type="number" id="n_futureLater" value="1500" min="0" max="100000" step="10" />
            <span class="unit">万円</span>
          </div>
        </label>
        <div class="hint" style="margin-top:4px">「今すぐ投資できる金額」は投資期間まるまる増配成長を見込みます。「今後投資予定額」は投資タイミングが未定のため、控えめに投資期間の半分の期間だけ増配成長したものとして計算します。</div>
```

- [ ] **Step 2: state を書き換える**

474-481行目を以下に置き換える:

```javascript
const state = {
  target: 120,        // 目標年間配当額（万円）
  isAfterTax: false,  // 税引後入力か
  current: 0,         // 現在の年間配当額・税引前（万円）
  futureNow: 500,      // A: 今すぐ投資できる金額（万円） - フル増配成長
  futureLater: 1500,   // B: 今後投資予定額・時期未定・累計（万円） - 半期間の増配成長
  years: 15,           // 目標達成までの投資期間（年）
  growth: 3,            // 想定増配率（%）
};
```

- [ ] **Step 3: calcRequiredYield を書き換える**

486-511行目（コメント含む）を以下に置き換える:

```javascript
// ----- core calculation -----
// 必要利回りを逆算する（現在の配当を控除し、A/Bで増配成長の重みを変える版）：
//   targetPretax = 税引前換算の目標額（万円）
//   現在配当 current は同じ増配率 g で N年後に current*(1+g)^N に成長
//   A（今すぐ投資できる金額）は N年分フルの増配成長: A*Y0*(1+g)^N
//   B（今後投資予定額・時期未定）は投資タイミング未定のため N/2年分だけ増配成長: B*Y0*(1+g)^(N/2)
//   合計が targetPretax と等しい：
//     current*(1+g)^N + A*Y0*(1+g)^N + B*Y0*(1+g)^(N/2) = targetPretax
//   → Y0 = (targetPretax - current*(1+g)^N) / (A*(1+g)^N + B*(1+g)^(N/2))
function calcRequiredYield(s){
  const targetPretax = s.isAfterTax ? s.target / NET_FACTOR : s.target;
  const growthFull = Math.pow(1 + s.growth/100, s.years);
  const growthHalf = Math.pow(1 + s.growth/100, s.years / 2);
  const currentAtN = s.current * growthFull;
  const remainingAtN = targetPretax - currentAtN; // N年後時点で新規資金が稼ぐべき配当額
  const totalInvested = s.futureNow * growthFull + s.futureLater * growthHalf;
  if(totalInvested <= 0){
    // 新規投資なしでも現在配当だけで目標到達なら 0%、そうでなければ達成不可
    if(remainingAtN <= 0) return { y: 0, yAtN: 0, totalInvested, targetPretax, achieved: true };
    return { y: Infinity, yAtN: Infinity, totalInvested, targetPretax };
  }
  if(remainingAtN <= 0){
    // 既に現在配当だけで（増配込みで）目標到達
    return { y: 0, yAtN: 0, totalInvested, targetPretax, achieved: true };
  }
  const y = (remainingAtN / totalInvested) * 100;
  const yAtN = y * growthFull;
  return { y, yAtN, totalInvested, targetPretax };
}
```

- [ ] **Step 4: els 参照を書き換える**

604-624行目のうち、`nFuture: document.getElementById('n_future'),` の行を以下に置き換える:

```javascript
  nFutureNow: document.getElementById('n_futureNow'),
  nFutureLater: document.getElementById('n_futureLater'),
```

（他の `els` プロパティ行はそのまま変更しない）

- [ ] **Step 5: future用イベントリスナーを書き換える**

822-826行目（`// future contribution (累計万円)` のコメントブロック）を以下に置き換える:

```javascript
// futureNow: A（今すぐ投資できる金額）
els.nFutureNow.addEventListener('input', () => {
  state.futureNow = clamp(+els.nFutureNow.value || 0, 0, 100000);
  update();
});

// futureLater: B（今後投資予定額・時期未定・累計）
els.nFutureLater.addEventListener('input', () => {
  state.futureLater = clamp(+els.nFutureLater.value || 0, 0, 100000);
  update();
});
```

- [ ] **Step 6: ブラウザで手動確認する**

`static/tools/dividend-target-simulator/index.html` をブラウザで開く。以下の値を入力して確認する:

- 目標年間配当額: 240万円、税引前
- 現在の年間配当額: 0万円
- 今すぐ投資できる金額: 500万円
- 今後投資予定額: 700万円
- 投資期間: 15年
- 想定増配率: 3%

期待値（手計算）:
- `(1.03)^15 ≈ 1.55797`
- `(1.03)^7.5 ≈ 1.24864`
- `currentAtN = 0`
- `remainingAtN = 240`
- `totalInvested = 500×1.55797 + 700×1.24864 ≈ 778.99 + 874.05 = 1653.04`
- `必要利回り = 240 / 1653.04 × 100 ≈ 14.52%`

画面の「平均配当利回り」が **約14.5%** と表示され、判定バッジが「達成困難」（赤）になっていることを確認する。ブラウザのコンソールにエラーが出ていないことも確認する。

- [ ] **Step 7: コミット**

```bash
git add static/tools/dividend-target-simulator/index.html
git commit -m "$(cat <<'EOF'
配当目標逆算シミュレーター: 入金をA(今すぐ)/B(今後・時期未定)に分離

Bは投資タイミングが未定なため増配成長を期間の半分だけ見込む方式に変更。
EOF
)"
```

---

### Task 2: 感度マトリクスをB軸＋A+B合計表示に変更する

**Files:**
- Modify: `static/tools/dividend-target-simulator/index.html:656-684`（JS: drawHeatmap関数）

**Interfaces:**
- Consumes: Task 1の `state.futureNow`（A）、`state.futureLater`（B）、`calcRequiredYield(s)`
- Produces: マトリクスDOM要素の内容更新（後続タスクなし。これが最終タスクの一つ）

- [ ] **Step 1: drawHeatmap() を書き換える**

656-684行目を以下に置き換える:

```javascript
// ----- heatmap (3x3) -----
// rows: B(今後投資予定額): x0.7, x1.0, x1.3 ; cols: years: base-3, base, base+3
// A(今すぐ投資できる金額)は state.futureNow の現在値で固定
function drawHeatmap(){
  const baseY = state.years;
  const baseB = state.futureLater;
  const yrsArr = [Math.max(1, baseY - 3), baseY, Math.min(40, baseY + 3)];
  const bArr   = [Math.max(0, Math.round(baseB * 0.7)), baseB, Math.round(baseB * 1.3)];

  let html = '';
  // header row
  html += '<div class="haxis"></div>';
  yrsArr.forEach(y => { html += `<div class="haxis">${y}年</div>`; });
  // body rows (rows = B: 今後投資予定額、A+B合計を併記)
  bArr.forEach((bv, ri) => {
    const total = state.futureNow + bv;
    html += `<div class="haxis">${bv}万<br><span style="opacity:.7;font-size:11px">(計${total}万)</span></div>`;
    yrsArr.forEach((yr, ci) => {
      const r = calcRequiredYield({...state, futureLater: bv, years: yr});
      const cls = heatClass(r.y);
      const isCenter = (ri === 1 && ci === 1);
      const yTxt = isFinite(r.y) ? r.y.toFixed(1) + '%' : '∞';
      const labelText = labelForYield(r.y);
      html += `<div class="hcell ${cls}${isCenter ? ' center' : ''}">
        <span class="v">${yTxt}</span>
        <span class="l">${labelText}</span>
      </div>`;
    });
  });
  els.heat.innerHTML = html;
}
```

- [ ] **Step 2: 感度マトリクスの説明文を更新する**

`index.html:416` の `<div class="hint" style="margin-bottom:8px">期間 × 今後の入金額で必要利回りがどう動くか</div>` を以下に置き換える:

```html
          <div class="hint" style="margin-bottom:8px">期間 × B(今後投資予定額)で必要利回りがどう動くか。A(今すぐ投資できる金額)は現在の入力値で固定。</div>
```

同じセクション内の `index.html:418` の `<div class="hyl">今後の入金額 →</div>` を以下に置き換える:

```html
            <div class="hyl">B: 今後投資予定額 →</div>
```

- [ ] **Step 3: ブラウザで手動確認する**

Task 1の入力値（現在0、今すぐ500万円、今後700万円、15年、増配3%）のまま画面を確認する。

- マトリクスの中央行見出しが「700万 / (計1,200万)」相当の表示になっていること
- 上段（今後490万=700×0.7）・下段（今後910万=700×1.3）の見出しにもそれぞれの合計額（990万・1,410万）が表示されていること
- 中央セル（15年×今後700万）に強調枠（`center`クラス）が付いていること
- コンソールにエラーが出ていないこと

- [ ] **Step 4: コミット**

```bash
git add static/tools/dividend-target-simulator/index.html
git commit -m "$(cat <<'EOF'
感度マトリクスをB(今後投資予定額)軸に変更し、A+B合計を見出しに併記
EOF
)"
```

---

### Task 3: チャート更新と入力欄同期バグの修正

**Files:**
- Modify: `static/tools/dividend-target-simulator/index.html:428-429`（HTML: チャートカードの説明文）
- Modify: `static/tools/dividend-target-simulator/index.html:696-716`（JS: buildChartData関数）
- Modify: `static/tools/dividend-target-simulator/index.html:799-804`（JS: n_targetのイベントリスナー、上限同期バグ修正）

**Interfaces:**
- Consumes: Task 1の `state.futureNow`, `state.futureLater`, `calcRequiredYield(s)`
- Produces: なし（最終タスク）

- [ ] **Step 1: チャートの説明文を書き換える**

428-429行目を以下に置き換える:

```html
        <div class="sketch-card">
          <h3><span class="num">06</span> 年次推移</h3>
          <div class="hint" style="margin-bottom:8px">累計投資額（グレー・Y0のみ）と年間配当額（緑）の推移 ※ A(今すぐ投資できる金額)は投資期間まるまる、B(今後投資予定額)は時期未定のため投資期間の半分だけ、それぞれ増配成長したものとして計算</div>
```

- [ ] **Step 2: buildChartData() を書き換える**

696-716行目を以下に置き換える:

```javascript
function buildChartData(){
  const labels = [], principalArr = [], divArr = [];
  // このツールは「A(今すぐ投資できる金額)をいま投資、B(今後投資予定額)は時期未定のため
  // 半期間だけ増配成長」という前提で必要利回りを逆算しているので、
  // チャートもその前提に沿って t=0 時点の投資元本と、年ごとの配当額を描く。
  const r = calcRequiredYield(state);
  const yNow = isFinite(r.y) ? r.y / 100 : 0;
  const g = state.growth / 100;
  for(let t = 0; t <= state.years; t++){
    labels.push('Y' + t);
    // 累計投資額（A+B、増配成長前の単純合計）は t=0 のみ表示
    const principal = state.futureNow + state.futureLater;
    // A分の配当：yNowで買った利回りが年数分フルに増配成長
    const divFutureNow = state.futureNow * yNow * Math.pow(1 + g, t);
    // B分の配当：同じ利回りだが、半期間分の増配成長を上限として t 年時点の成長を反映
    const divFutureLater = state.futureLater * yNow * Math.pow(1 + g, Math.min(t, state.years / 2));
    // 現在配当も同じ増配率で成長
    const divCurrent = state.current * Math.pow(1 + g, t);
    const div = divFutureNow + divFutureLater + divCurrent;
    principalArr.push(t === 0 ? Math.round(principal) : null);
    divArr.push(Math.round(div * 10) / 10);
  }
  return { labels, principalArr, divArr };
}
```

- [ ] **Step 3: n_target の入力欄同期バグを修正する**

799-804行目を以下に置き換える:

```javascript
els.nTarget.addEventListener('input', () => {
  const v = clamp(+els.nTarget.value || 0, 12, 600);
  state.target = v;
  els.rTarget.value = v;
  els.nTarget.value = v;
  update();
});
```

- [ ] **Step 4: ブラウザで手動確認する**

Task 1の入力値（現在0、今すぐ500万円、今後700万円、15年、増配3%）のまま画面を確認する。

- チャートカードの説明文が新しい文言（A/Bの増配成長の違いに言及）になっていること
- チャートの棒グラフ（Y0）が1,200万円（500+700）付近であること
- チャートの折れ線（Y15）が、Task 1で確認した約14.5%の利回りから逆算される配当額付近になっていること
- 投資期間スライダーを動かし、折れ線がなめらかに変化し、エラーが出ないこと

次に、目標配当額の数値入力欄に `1000` と入力する:

- 入力欄の表示が `600` に書き換わること（旧バグでは `1000` のまま表示されていた）
- スライダーも600の位置に移動していること
- 「平均配当利回り」の表示が、目標600万円を前提にした値になっていること

- [ ] **Step 5: コミット**

```bash
git add static/tools/dividend-target-simulator/index.html
git commit -m "$(cat <<'EOF'
チャートをA/B方式に更新し、目標配当額入力欄の上限同期バグを修正
EOF
)"
```

---

## 実装後の残タスク（このプランの範囲外・ユーザー確認事項）

- Hugoビルド（`hugo`コマンド等）を実行し、`public/tools/dividend-target-simulator/` に正しく反映されることを確認する
- 本番デプロイ（finlab-seの既存デプロイフローに従う。本番デプロイはOpusモデルで実施する運用ルールがあるため、デプロイ自体は別セッション/別モデルで行う）
- デプロイ後、本番URLで実機確認

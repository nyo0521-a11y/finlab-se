# サムネ ベース画像 生成プロンプト（hengakuhoken-vs-nisa）

- 用途: finlab-se 記事「変額保険とNISA どっちがいい？手数料の実質差を比較」のサムネ**ベース画像（文字なし）**
- 生成ツール: ChatGPT（gpt-image-2）
- 保存先: `static/images/thumb-hengakuhoken-vs-nisa-base.png`
- サイズ: 1376×768px（16:9・横長）
- 文字は一切入れない（タイトルは後からHTMLで焼き込む）

---

## 貼り付け用プロンプト（英語）

A cinematic 16:9 financial-tech background image, 1376x768, no text, no logos, no letters, no numbers anywhere.

Dark navy to near-black gradient background (#050C23 to #0A1A4A), sophisticated Bloomberg / Nikkei style 3D CG world. Subtle circuit lines, data grid, and floating light particles.

Main visual on the RIGHT 55% of the frame: two glowing translucent vertical vessels or capsules standing side by side, made of luminous glass, filled with rising streams of tiny light coins and particles. The LEFT capsule is wrapped in extra translucent outer shells/layers that dim and absorb some of the rising light (evoking hidden fee layers eroding the flow). The RIGHT capsule is clean and single-layered, letting the light rise brighter and higher. Emerald green (#4ADE80) and amber gold (#F59E0B) as the accent colors of the light streams and glow.

The LEFT 45% of the frame must stay dark, quiet and uncluttered (reserved for a title overlay added later) — only faint circuit lines and a soft vignette there.

Soft bloom, depth of field, high contrast, premium editorial finance aesthetic.

Do NOT include: any text, letters, numbers, currency symbols as readable characters, white infographic backgrounds, four-panel splits, checkmarks or crosses, icebergs (already used in another article), human figures.

---

## 補足（テイスト共通規定・スキル準拠）
- 右55%にメインビジュアル、左45%は暗く保つ（後で文字を載せるため）
- 主役色: エメラルドグリーン #4ADE80／アンバーゴールド #F59E0B
- **氷山モチーフは別記事（mutual-fund-real-cost）で使用済みのため使わない** → 今回は「2本の透明カプセル（＝変額保険＝多層で光が減衰／NISA＝単層で光が伸びる）」で"手数料の層の差"を表現
- テキスト・ロゴ・数字・通貨記号は一切入れない（文字化け・再利用性のため）
- 生成後は無加工で `thumb-hengakuhoken-vs-nisa-base.png` として保存・コミット。タイトル文字は `finlab-se-thumbnail` スキルのSTEP2でHTMLオーバーレイする

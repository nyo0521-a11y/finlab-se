# サムネイル テキスト合成スクリプト
# 記事: 暗号資産取引所の選び方｜安全性・手数料・金融グループ傘下で比較2026
#
# 使い方:
#   1. ベース画像を生成して以下に配置:
#      static/images/thumb-crypto-exchange-financial-group-2026-base.png
#   2. finlab-seリポジトリルートで以下を実行:
#      powershell.exe -ExecutionPolicy Bypass -File scripts\thumb-crypto-exchange-financial-group-2026-compose.ps1
#
# タイトルを変更する場合は -Title1 / -Title2 / -Sub1 / -Sub2 を編集して再実行。

$repoRoot = Split-Path -Parent $PSScriptRoot

& powershell.exe -ExecutionPolicy Bypass -Command "& '$env:USERPROFILE\tmp_compose_thumb.ps1' ``
  -BasePath  '$repoRoot\static\images\thumb-crypto-exchange-financial-group-2026-base.png' ``
  -OutputPath '$repoRoot\static\images\thumb-crypto-exchange-financial-group-2026.png' ``
  -Badge  '資産形成' ``
  -Title1 '暗号資産取引所の選び方' ``
  -Title2 '金融グループ別比較2026' ``
  -Sub1   '安全性・手数料・親会社の資本力を' ``
  -Sub2   '実体験から徹底比較'"

Write-Host "完了: static/images/thumb-crypto-exchange-financial-group-2026.png"

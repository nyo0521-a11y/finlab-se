# サムネイル テキスト合成スクリプト
# 記事: 高配当株でインデックス投資は不要なのか？老後資金から逆算した結論
#
# 使い方:
#   1. ベース画像を生成して以下に配置:
#      static/images/thumb-index-vs-highyield-retirement-allocation-base.png
#   2. finlab-seリポジトリルートで以下を実行:
#      powershell.exe -ExecutionPolicy Bypass -File scripts\thumb-index-vs-highyield-retirement-allocation-compose.ps1
#
# タイトルを変更する場合は -Title1 / -Title2 / -Sub1 / -Sub2 を編集して再実行。

$repoRoot = Split-Path -Parent $PSScriptRoot

& powershell.exe -ExecutionPolicy Bypass -Command "& '$env:USERPROFILE\tmp_compose_thumb.ps1' ``
  -BasePath  '$repoRoot\static\images\thumb-index-vs-highyield-retirement-allocation-base.png' ``
  -OutputPath '$repoRoot\static\images\thumb-index-vs-highyield-retirement-allocation.png' ``
  -Badge  '資産形成' ``
  -Title1 'インデックス投資は' ``
  -Title2 '本当に不要なのか？' ``
  -Sub1   '高配当株のみで老後資金を賄えるのか' ``
  -Sub2   '必要な積立額を逆算した結論'"

Write-Host "完了: static/images/thumb-index-vs-highyield-retirement-allocation.png"

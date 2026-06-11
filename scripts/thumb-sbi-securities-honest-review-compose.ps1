# サムネイル テキスト合成スクリプト
# 記事: SBI証券のS株で高配当株100銘柄超を買った正直レビュー
#
# 使い方:
#   1. ベース画像を生成して以下に配置:
#      static/images/thumb-sbi-securities-honest-review-base.png
#   2. finlab-seリポジトリルートで以下を実行:
#      powershell.exe -ExecutionPolicy Bypass -File scripts/thumb-sbi-securities-honest-review-compose.ps1
#
# タイトルを変更する場合は -Title1 / -Title2 / -Sub1 / -Sub2 を編集して再実行。

$repoRoot = Split-Path -Parent $PSScriptRoot

& "$env:USERPROFILE/tmp_compose_thumb.ps1" `
  -BasePath  "$repoRoot/static/images/thumb-sbi-securities-honest-review-base.png" `
  -OutputPath "$repoRoot/static/images/thumb-sbi-securities-honest-review.png" `
  -Badge  '高配当株投資' `
  -Title1 'SBI証券のS株' `
  -Title2 '正直レビュー' `
  -Sub1   '高配当株100銘柄超を買い集めて' `
  -Sub2   '分かった強みと不満点'

Write-Host "Done: static/images/thumb-sbi-securities-honest-review.png"

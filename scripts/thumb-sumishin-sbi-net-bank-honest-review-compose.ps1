# Thumbnail text compose script
# Article: Sumishin SBI Net Bank honest review
#
# Usage:
#   powershell.exe -ExecutionPolicy Bypass -File scripts/thumb-sumishin-sbi-net-bank-honest-review-compose.ps1
#
# To change the title, edit -Title1 / -Title2 / -Sub1 / -Sub2 and re-run.

$repoRoot = Split-Path -Parent $PSScriptRoot

& "$env:USERPROFILE/tmp_compose_thumb.ps1" `
  -BasePath  "$repoRoot/static/images/thumb-sumishin-sbi-net-bank-honest-review-base.png" `
  -OutputPath "$repoRoot/static/images/thumb-sumishin-sbi-net-bank-honest-review.png" `
  -Badge  '資産形成' `
  -Title1 '住信SBIネット銀行' `
  -Title2 '正直レビュー' `
  -Sub1   '目的別口座の使い方と' `
  -Sub2   '小遣い管理の実体験'

Write-Host "Done: static/images/thumb-sumishin-sbi-net-bank-honest-review.png"

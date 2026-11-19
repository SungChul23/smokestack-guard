<#
.SYNOPSIS
  서비스 인프라를 운영 구성(off / dev / demo)으로 한 번에 켜고 끈다.
  specs/a-platform/009-service-infra/contracts/toggles.md

.EXAMPLE
  .\service-env.ps1 dev          # 개발: NAT 1, DB 단일 AZ + 배스천, ALB, 서버 각 1  (하루 약 $5)
  .\service-env.ps1 demo         # 시연: NAT 2, DB Multi-AZ + 배스천, ALB, 서버 각 2 (하루 약 $8)
  .\service-env.ps1 off          # 꺼 둠: NAT·ALB·서버 0. DB·배스천은 켜 둔다(대시보드 적재 012, 2026-11-19)
  .\service-env.ps1 dev -AutoApprove   # 스택마다 yes 입력 없이

.NOTES
  - 켤 때 순서: tms-network → tms-database → tms-app (서버보다 NAT·DB가 먼저)
  - 끌 때 순서: tms-app → tms-database → tms-network (서버가 NAT보다 먼저 사라져야 함)
  - 각 스택은 terraform init이 끝나 있어야 한다. tms-foundation·tms-serving은 건드리지 않는다.
#>
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("off", "dev", "demo")]
  [string]$Mode,

  [switch]$AutoApprove
)

$ErrorActionPreference = "Stop"
$stacks = Join-Path $PSScriptRoot "..\stacks"

$config = @{
  off  = @{ nat = 0; rds = "true";  multiAz = "false"; alb = "false"; api = 0; agent = 0 }
  dev  = @{ nat = 1; rds = "true";  multiAz = "false"; alb = "true";  api = 1; agent = 1 }
  demo = @{ nat = 2; rds = "true";  multiAz = "true";  alb = "true";  api = 2; agent = 2 }
}[$Mode]

$steps = @(
  @{ stack = "tms-network";  vars = @("-var", "nat_gateway_count=$($config.nat)") },
  @{ stack = "tms-database"; vars = @("-var", "rds_enabled=$($config.rds)", "-var", "db_multi_az=$($config.multiAz)") },
  @{ stack = "tms-app";      vars = @("-var", "alb_enabled=$($config.alb)", "-var", "api_desired=$($config.api)", "-var", "agent_desired=$($config.agent)") }
)
if ($Mode -eq "off") { [array]::Reverse($steps) }

# 배스천은 DB와 함께 뜬다. 켜기 전에 키 쌍이 있는지 확인
if ($config.rds -eq "true") {
  aws ec2 describe-key-pairs --key-names tms-bastion --query "KeyPairs[0].KeyName" --output text 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "키 쌍 tms-bastion이 없다. EC2 콘솔 > 키 페어에서 먼저 만들어라 (.pem)."
  }
}

Write-Host "== 운영 구성: $Mode ==" -ForegroundColor Cyan
foreach ($s in $steps) {
  Write-Host "`n-- $($s.stack): $($s.vars -join ' ')" -ForegroundColor Yellow
  Push-Location (Join-Path $stacks $s.stack)
  try {
    $tfArgs = @("apply", "-input=false") + $s.vars
    if ($AutoApprove) { $tfArgs += "-auto-approve" }
    terraform @tfArgs
    if ($LASTEXITCODE -ne 0) { throw "$($s.stack) apply 실패. 위 오류를 확인하고 다시 실행하라 (이미 적용된 스택은 그대로 둔다)." }
  }
  finally {
    Pop-Location
  }
}

Write-Host "`n== 완료: $Mode ==" -ForegroundColor Green
if ($Mode -ne "off") {
  Write-Host "확인 (서버가 뜨고 약 5분 뒤):"
  Write-Host "  https://api.smokestack-guard.store/api/health"
  Write-Host "  https://api.smokestack-guard.store/agent/health"
  Write-Host "  https://api.smokestack-guard.store/api/db-check"
  Write-Host "  DBeaver: infra/stacks/tms-database/README.md (SSH 호스트 bastion.smokestack-guard.store)"
  Write-Host "끝나면 꼭 끄기:  .\service-env.ps1 off" -ForegroundColor Red
}

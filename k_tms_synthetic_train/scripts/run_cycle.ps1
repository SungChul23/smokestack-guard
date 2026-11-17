# run_cycle.ps1: 발행 -> Spark 적재 한 사이클
param([int]$LookbackMin = 0)      
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$cmd = @("-m", "synth_train", "cycle", "--config", "config/daily.yaml")
if ($LookbackMin -gt 0) { $cmd += @("--lookback-min", "$LookbackMin") }
& python @cmd
exit $LASTEXITCODE
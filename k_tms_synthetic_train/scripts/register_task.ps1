# register_task.ps1: 10분마다 run_cycle.ps1을 실행하는 작업을 등록한다.
param([switch]$Remove, [string]$TaskName = "sg-synth-train-cycle")
if ($Remove) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; exit 0 }
$script = Join-Path $PSScriptRoot "run_cycle.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "합성 데이터 발행 후 MinIO 적재 (10분마다)"
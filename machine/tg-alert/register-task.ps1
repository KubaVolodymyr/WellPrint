$d = 'C:\ProgramData\tg-alert'
$a  = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('//nologo ' + (Join-Path $d 'tg-alert.vbs'))
$t1 = New-ScheduledTaskTrigger -AtStartup
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)
$p  = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$s  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'TG-Alert' -Action $a -Trigger @($t1,$t2) -Principal $p -Settings $s -Force | Out-Null
(Get-ScheduledTask 'TG-Alert').State
icacls $d /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null

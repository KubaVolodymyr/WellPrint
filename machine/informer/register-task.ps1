$d = 'C:\ProgramData\tg-informer'; $u = "$env:COMPUTERNAME\uf3570"
$a = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$d\run.vbs`""
$t = New-ScheduledTaskTrigger -AtLogOn -User $u; $t.Delay = 'PT40S'
$p = New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Limited
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -Priority 7
Register-ScheduledTask -TaskName 'TG-Informer' -Action $a -Trigger $t -Principal $p -Settings $s -Force
Start-ScheduledTask 'TG-Informer'

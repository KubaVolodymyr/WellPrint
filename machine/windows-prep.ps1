# Крок 0 — живлення без сну
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /h off

# Крок 0 — Windows Update без автоматичного перезавантаження
$k = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
New-Item -Path $k -Force | Out-Null
Set-ItemProperty $k NoAutoRebootWithLoggedOnUsers 1 -Type DWord   # не ребутити, поки хтось увійшов (автологін = завжди)
Set-ItemProperty $k AUOptions 3 -Type DWord                        # 3 = завантажувати, питати перед встановленням; 4 = ставити за розкладом

# tg-alert.ps1 — слухач стану машини. Лише читає (процес, аптайм) і шле в Telegram.
# Нічого не запускає, не вбиває, не змінює. Стан: state.json, лог: alert.log.
param([switch]$Test)
$ErrorActionPreference = 'SilentlyContinue'
$Dir = 'C:\ProgramData\tg-alert'
$DownAfterMin  = 15     # процес лежить довше → алерт
$RepeatMin     = 60     # повтор алерту, поки лежить
$BootWindowMin = 30     # аптайм менший → «щойно перезавантажився»

$cfg   = Get-Content (Join-Path $Dir 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$Token = $cfg.token; $Chat = $cfg.chat_id; $Proc = $cfg.process; $Label = $cfg.label
$StateFile = Join-Path $Dir 'state.json'
$Log = Join-Path $Dir 'alert.log'

function Log($m) { Add-Content -Path $Log -Value ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' ' + $m) -Encoding UTF8 }
function Send($text) {
    $json  = @{ chat_id = $Chat; text = ('🖨 ' + $Label + ': ' + $text); disable_web_page_preview = $true } | ConvertTo-Json -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    try {
        $r = Invoke-RestMethod -Method Post -Uri ('https://api.telegram.org/bot' + $Token + '/sendMessage') -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 20
        Log ('SEND ok: ' + $text)
    } catch { Log ('SEND FAIL: ' + $text + ' => ' + $_.Exception.Message) }
}

if ($Test) { Send ('Тест слухача ' + (Get-Date).ToString('HH:mm')); exit 0 }

$st = @{ down_since = $null; down_alerted_at = $null; boot_alerted = '' }
if (Test-Path $StateFile) {
    try { $j = Get-Content $StateFile -Raw | ConvertFrom-Json; foreach ($k in 'down_since','down_alerted_at','boot_alerted') { $st[$k] = $j.$k } } catch {}
}

$now   = Get-Date
$boot  = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$upMin = [int](($now - $boot).TotalMinutes)
$running = [bool](Get-Process $Proc -ErrorAction SilentlyContinue)

# 1) ребут Windows — один алерт на кожне завантаження
$bootKey = $boot.ToString('yyyyMMddHHmmss')
if ($upMin -le $BootWindowMin -and $st.boot_alerted -ne $bootKey) {
    $s = if ($running) { $Proc + ' запущений (автозапуск)' } else { $Proc + ' НЕ запущений' }
    Send ('⚠️ Windows перезавантажився о ' + $boot.ToString('HH:mm') + ' (аптайм ' + $upMin + ' хв). ' + $s + '. Перевір машину.')
    $st.boot_alerted = $bootKey
}

# 2) процес лежить
if (-not $running) {
    if (-not $st.down_since) { $st.down_since = $now.ToString('o') }
    $downMin = [int](($now - [datetime]$st.down_since).TotalMinutes)
    $last = if ($st.down_alerted_at) { [datetime]$st.down_alerted_at } else { $null }
    if ($downMin -ge $DownAfterMin -and (-not $last -or ($now - $last).TotalMinutes -ge $RepeatMin)) {
        Send ('🔴 ' + $Proc + ' не запущений уже ' + $downMin + ' хв. Запусти програму.')
        $st.down_alerted_at = $now.ToString('o')
    }
} else {
    if ($st.down_alerted_at) { Send ('🟢 ' + $Proc + ' знову працює (лежав із ' + ([datetime]$st.down_since).ToString('HH:mm') + ').') }
    $st.down_since = $null; $st.down_alerted_at = $null
}

[IO.File]::WriteAllText($StateFile, ($st | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))

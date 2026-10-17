# informer.ps1 — інформер тиражу на екрані принтерної машини. Маленьке вікно поверх усіх вікон:
# прогрес тиражу з хаба (batch-bot.py), зворотний відлік до кінця поточного столу, кнопки «Старт» і «Брак».
# Лише опитує хаб (GET /status раз на 5 с). Принтер, RIP і файли не чіпає. Зберігати як UTF-8 з BOM.
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName Microsoft.VisualBasic

# ---- налаштування (три рядки) ----
$Hub       = 'http://192.168.1.10:8765'                 # адреса хаба з Кроку 7
$Machine   = 'UF-3570'                                  # мітка машини — така сама, як у machines у config.json хаба
$TokenFile = 'C:\ProgramData\tg-informer\.token'        # файл з hub_token (один рядок, без лапок)
$Interval  = 5                                          # секунд між запитами до хаба

function Get-Token { try { (Get-Content -LiteralPath $TokenFile -Raw -ErrorAction Stop).Trim() } catch { '' } }
function Post-Hub($path, $obj) {
    $body = [System.Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Compress))
    Invoke-RestMethod -Method Post -Uri ($Hub + $path) -Headers @{ 'X-Hub-Token' = (Get-Token) } `
        -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 10 -ErrorAction Stop
}

$form = New-Object System.Windows.Forms.Form
$form.FormBorderStyle = 'None'; $form.TopMost = $true; $form.ShowInTaskbar = $false; $form.StartPosition = 'Manual'
$form.BackColor = [System.Drawing.Color]::FromArgb(30, 30, 32); $form.Opacity = 0.93
$form.Width = 440; $form.Height = 84

$label = New-Object System.Windows.Forms.Label
$label.AutoSize = $false; $label.Dock = 'Fill'
$label.Padding = New-Object System.Windows.Forms.Padding(10, 8, 4, 8)
$label.Font = New-Object System.Drawing.Font('Segoe UI', 11); $label.ForeColor = [System.Drawing.Color]::White
$label.Text = 'Інформер тиражу: завантаження…'
$form.Controls.Add($label)

# великий зворотний відлік (хв:сс до кінця поточного столу) — видно здалеку
$big = New-Object System.Windows.Forms.Label
$big.AutoSize = $false; $big.Dock = 'Right'; $big.Width = 104; $big.TextAlign = 'MiddleCenter'
$big.Font = New-Object System.Drawing.Font('Segoe UI', 26, [System.Drawing.FontStyle]::Bold)
$big.ForeColor = [System.Drawing.Color]::FromArgb(170, 255, 170); $big.Visible = $false
$form.Controls.Add($big)
$script:due = $null; $script:per = 1

$btnPanel = New-Object System.Windows.Forms.Panel
$btnPanel.Dock = 'Right'; $btnPanel.Width = 64
function New-Btn($text, $color) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $text; $b.Width = 58; $b.Height = 32; $b.Left = 6; $b.Top = 26
    $b.FlatStyle = 'Flat'; $b.FlatAppearance.BorderSize = 0
    $b.BackColor = $color; $b.ForeColor = 'White'
    $b.Font = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
    $b.Visible = $false
    $btnPanel.Controls.Add($b); $b
}
$btn      = New-Btn 'Брак'  ([System.Drawing.Color]::FromArgb(150, 40, 40))   # активний тираж: n шт зі столу у брак
$btnStart = New-Btn 'Старт' ([System.Drawing.Color]::FromArgb(40, 110, 60))   # тиражу нема: по скільки → всього
$form.Controls.Add($btnPanel)

function Start-Batch {
    $a = [Microsoft.VisualBasic.Interaction]::InputBox('Скільки штук за раз (на стіл)?', 'Почати тираж', '1')
    if (-not ($a -match '^\d{1,2}$') -or [int]$a -lt 1) { return }
    $b = [Microsoft.VisualBasic.Interaction]::InputBox('Скільки всього штук у тиражі?', 'Почати тираж', '')
    if (-not ($b -match '^\d{1,4}$') -or [int]$b -lt 1) { return }
    try { Post-Hub '/batch-start' @{ per = [int]$a; total = [int]$b; machine = $Machine } | Out-Null }
    catch {
        $msg = $_.Exception.Message
        try { $msg = ($_.ErrorDetails.Message | ConvertFrom-Json).msg } catch {}
        [void][System.Windows.Forms.MessageBox]::Show($form, 'Не вдалося: ' + $msg, 'Почати тираж', 'OK', 'Error')
    }
    Refresh-Status
}
$btnStart.Add_Click({ Start-Batch })

function Report-Defect {
    $n = 1
    if ($script:per -gt 1) {
        $ans = [Microsoft.VisualBasic.Interaction]::InputBox(("Скільки штук браку зі столу (на столі {0})?" -f $script:per), 'Брак', [string]$script:per)
        if (-not $ans -or -not ($ans -match '^\d{1,3}$')) { return }
        $n = [int]$ans; if ($n -lt 1) { return }
    } else {
        $ok = [System.Windows.Forms.MessageBox]::Show($form, 'Позначити 1 шт як брак? Піде в Telegram і додасться до тиражу.', 'Брак', 'YesNo', 'Warning')
        if ($ok -ne 'Yes') { return }
    }
    try {
        Post-Hub '/defect' @{ pieces = $n; machine = $Machine } | Out-Null
        $label.Text = 'Брак ' + $n + ' шт зараховано · ' + (Get-Date -Format 'HH:mm')
    } catch {
        $msg = $_.Exception.Message
        try { $msg = ($_.ErrorDetails.Message | ConvertFrom-Json).msg } catch {}
        [void][System.Windows.Forms.MessageBox]::Show($form, 'Не вдалося: ' + $msg, 'Брак', 'OK', 'Error')
    }
    Refresh-Status
}
$btn.Add_Click({ Report-Defect })

function Tick-Countdown {
    if (-not $big.Visible -or -not $script:due) { return }
    $left = ($script:due - (Get-Date)).TotalSeconds
    if ($left -gt 0) {
        $s = [int][math]::Ceiling($left)
        $big.Text = '{0}:{1:00}' -f [math]::Floor($s / 60), ($s % 60)   # тікає локально — запитів не додає
        $big.ForeColor = [System.Drawing.Color]::FromArgb(170, 255, 170)
    } else {
        $big.Text = '0:00'
        $big.ForeColor = [System.Drawing.Color]::FromArgb(255, 190, 120)   # стіл триває довше за прогноз — гляньте на машину
    }
}

function Place {
    $wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $btn.Top = [int](($form.Height - $btn.Height) / 2); $btnStart.Top = $btn.Top
    $form.Left = $wa.Right - $form.Width - 12
    $form.Top = $wa.Top + 48          # правий верхній кут; змініть, якщо там кнопки RIP-а
}

function Refresh-Status {
    $tok = Get-Token
    if (-not $tok) { $label.ForeColor = 'Orange'; $label.Text = 'Нема токена ' + $TokenFile; return }
    try {
        $r = Invoke-RestMethod -Uri ($Hub + '/status') -Headers @{ 'X-Hub-Token' = $tok } -TimeoutSec 10 -ErrorAction Stop
    } catch {
        $label.ForeColor = 'Orange'; $label.Text = 'Хаб недоступний · ' + (Get-Date -Format 'HH:mm')
        $big.Visible = $false; $btn.Visible = $false; $btnStart.Visible = $false
        $form.Width = 440; $form.Height = 40; Place; return
    }
    if ($r.active) {
        $btnStart.Visible = $false; $btn.Visible = $true
        $label.ForeColor = [System.Drawing.Color]::FromArgb(220, 255, 220)
        $label.Text = ($r.text -replace "`n", "`r`n")
        $form.Height = 84
        $script:per = [int]$r.per
        if ($r.round_s -gt 0) {
            # кінець поточного столу = зараз + (last_ts + round_s − server_ts): без залежності від зсуву годинників
            $script:due = (Get-Date).AddSeconds([double]$r.last_ts + [double]$r.round_s - [double]$r.server_ts)
            $big.Visible = $true; Tick-Countdown
        } else { $big.Visible = $false; $script:due = $null }     # перший стіл: темпу ще нема
    } else {
        $big.Visible = $false; $script:due = $null; $btn.Visible = $false; $btnStart.Visible = $true
        if ($r.done) {
            # підсумок останнього тиражу — хаб віддає 5 хв після завершення
            $label.ForeColor = [System.Drawing.Color]::FromArgb(190, 235, 190)
            $label.Text = ($r.text -replace "`n", "`r`n"); $form.Height = 84
        } else { $label.Text = ''; $form.Height = 48 }           # тиражу нема: лише зелена кнопка «Старт»
    }
    $form.Width = $(if ($r.active -or $r.done) { 440 } else { 76 })
    Place
}

# тягнути мишкою + ПКМ-меню
$script:drag = $false; $script:dx = 0; $script:dy = 0
$label.Add_MouseDown({ param($s, $e) if ($e.Button -eq 'Left') { $script:drag = $true; $script:dx = $e.X; $script:dy = $e.Y } })
$label.Add_MouseMove({ param($s, $e) if ($script:drag) { $form.Left += $e.X - $script:dx; $form.Top += $e.Y - $script:dy } })
$label.Add_MouseUp({ $script:drag = $false })
$menu = New-Object System.Windows.Forms.ContextMenuStrip
[void]$menu.Items.Add('Оновити зараз', $null, { Refresh-Status })
[void]$menu.Items.Add('У кут', $null, { Place })
[void]$menu.Items.Add('Вийти', $null, { $form.Close() })
$label.ContextMenuStrip = $menu; $big.ContextMenuStrip = $menu

$timer = New-Object System.Windows.Forms.Timer; $timer.Interval = $Interval * 1000; $timer.Add_Tick({ Refresh-Status })
$sec = New-Object System.Windows.Forms.Timer; $sec.Interval = 1000; $sec.Add_Tick({ Tick-Countdown })
$form.Add_Shown({ Place; Refresh-Status; $timer.Start(); $sec.Start() })
[void]$form.ShowDialog()

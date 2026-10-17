# print-watch.ps1 — запасний вотчер: читає PrintHistory.xml WellPrint і шле кожен завершений джоб у хаб.
# Лише читає. Стан: seen.json. Задача планувальника раз на хвилину.
$ErrorActionPreference = 'SilentlyContinue'
$Dir = 'C:\ProgramData\print-watch'
$cfg = Get-Content (Join-Path $Dir 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$SeenFile = Join-Path $Dir 'seen.json'; $Log = Join-Path $Dir 'watch.log'
function Log($m) { Add-Content $Log ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' ' + $m) -Encoding UTF8 }

$files = Get-ChildItem 'C:\Users\*\Documents\*\WellPrint*\AssemblyData\Variable\*\*\PrintHistory.xml' -ErrorAction SilentlyContinue
if (-not $files) { Log 'PrintHistory.xml не знайдено'; exit 0 }
$seen = @{}
if (Test-Path $SeenFile) { try { (Get-Content $SeenFile -Raw | ConvertFrom-Json).psobject.Properties | ForEach-Object { $seen[$_.Name] = 1 } } catch {} }
$first = ($seen.Count -eq 0)
$enc = [Text.Encoding]::GetEncoding(936)   # GB2312
foreach ($f in $files) {
  $txt = $enc.GetString([IO.File]::ReadAllBytes($f.FullName))
  foreach ($m in [regex]::Matches($txt, '<SPrintHistoryRecord>(.*?)</SPrintHistoryRecord>', 'Singleline')) {
    $r = $m.Groups[1].Value
    $pt = [regex]::Match($r, '<printTime>(.*?)</printTime>').Groups[1].Value.Trim()
    if (-not $pt -or $seen.ContainsKey($pt)) { continue }
    $seen[$pt] = 1
    if ($first) { continue }
    $age = (Get-Date) - [datetime]::ParseExact($pt.Substring(0, 19), 'yyyy-MM-ddTHH:mm:ss', $null)
    $cancel = [regex]::Match($r, '<jobCancel>(.*?)</jobCancel>').Groups[1].Value.Trim().ToLower()
    $all = [regex]::Match($r, '<copyCount_all>(.*?)</copyCount_all>').Groups[1].Value.Trim()
    $done = [regex]::Match($r, '<copyCount_complete>(.*?)</copyCount_complete>').Groups[1].Value.Trim()
    if ($age.TotalDays -gt 2 -or $cancel -eq 'true' -or $all -ne $done) { continue }
    $job = [IO.Path]::GetFileNameWithoutExtension([regex]::Match($r, '<jobFullPath>(.*?)</jobFullPath>').Groups[1].Value.Trim())
    $body = [Text.Encoding]::UTF8.GetBytes((@{ machine = $cfg.machine; job = $job; printTime = $pt } | ConvertTo-Json -Compress))
    try {
      Invoke-RestMethod -Method Post -Uri $cfg.hub -Headers @{ 'X-Hub-Token' = $cfg.hub_token } -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 15 | Out-Null
      Log ('sent: ' + $job + ' ' + $pt)
    } catch { $seen.Remove($pt); Log ('FAIL: ' + $job + ' => ' + $_.Exception.Message) }
  }
}
if ($first) { Log ('baseline: ' + $seen.Count) }
$keep = @{}; $seen.Keys | Sort-Object | Select-Object -Last 5000 | ForEach-Object { $keep[$_] = 1 }
[IO.File]::WriteAllText($SeenFile, ($keep | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))

<#
青草编辑器 / GitHub Actions Runner 清理脚本
用法（管理员 PowerShell）：
  powershell -ExecutionPolicy Bypass -File tools\cleanup_runner_artifacts.ps1
  powershell -ExecutionPolicy Bypass -File tools\cleanup_runner_artifacts.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File tools\cleanup_runner_artifacts.ps1 -IncludeWorkCache
#>
param(
  [switch]$DryRun,
  [switch]$IncludeWorkCache
)

$ErrorActionPreference = "Stop"
$Root = "D:\actions-runner"
$Log = Join-Path $PSScriptRoot "cleanup_runner_artifacts.log"

function Write-Log($msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Write-Host $line
  Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Get-SizeMB($path) {
  if (-not (Test-Path $path)) { return 0 }
  $sum = (Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object Length -Sum).Sum
  if ($null -eq $sum) { return 0 }
  return [Math]::Round($sum / 1MB, 1)
}

$isAdmin = ([Security.Principal.WindowsPrincipal](
  [Security.Principal.WindowsIdentity]::GetCurrent())
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin -and -not $DryRun) {
  throw "请以管理员身份运行（或先使用 -DryRun 预览）"
}

$targets = @(
  "$Root\bin.2.338.2",
  "$Root\crash_dumps"
)
if ($IncludeWorkCache) {
  $targets += @(
    "$Root\_work\qingcao\qingcao\build",
    "$Root\_work\qingcao\qingcao\dist",
    "$Root\_work\qingcao\qingcao\installer"
  )
}

Write-Log "模式: $(if($DryRun){'DryRun'}else{'执行'})"
$total = 0
foreach ($t in $targets) {
  $sz = Get-SizeMB $t
  $total += $sz
  Write-Log ("目标 {0} = {1} MB" -f $t, $sz)
}
Write-Log ("预计回收: {0} MB" -f [Math]::Round($total, 1))

if ($DryRun) {
  Write-Log "DryRun 结束，未做任何修改"
  exit 0
}

$workers = Get-Process -Name "Runner.Worker" -ErrorAction SilentlyContinue
if ($workers) {
  throw "检测到活动 Runner.Worker，停止清理，避免破坏 CI 任务"
}

$services = Get-Service -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like "actions.runner.*" -and $_.Status -eq "Running" }
$originallyRunning = @()
foreach ($svc in $services) { $originallyRunning += $svc.Name }

$stopped = @()
try {
  foreach ($name in $originallyRunning) {
    try {
      Stop-Service -Name $name -Force -ErrorAction Stop
      $stopped += $name
      Write-Log "已停止服务: $name"
    } catch {
      Write-Log "停止失败 $name : $($_.Exception.Message)"
    }
  }
  Start-Sleep -Seconds 3

  foreach ($t in $targets) {
    if (-not (Test-Path $t)) { Write-Log "跳过（不存在）: $t"; continue }
    $resolved = (Resolve-Path -LiteralPath $t).Path
    if (-not $resolved.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)) {
      Write-Log "安全跳过（不在 $Root 下）: $resolved"
      continue
    }
    try {
      Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
      Write-Log "已删除: $resolved"
    } catch {
      Write-Log "删除失败 $resolved : $($_.Exception.Message)"
    }
  }

  # _diag：仅保留最近 5 个 Worker 日志
  $diag = Join-Path $Root "_diag"
  if (Test-Path $diag) {
    $logs = Get-ChildItem $diag -Filter "Worker_*.log" |
      Sort-Object LastWriteTime -Descending
    if ($logs.Count -gt 5) {
      $old = $logs | Select-Object -Skip 5
      $old | Remove-Item -Force -ErrorAction SilentlyContinue
      Write-Log ("已清理旧诊断日志: {0} 个" -f $old.Count)
    }
  }
} finally {
  foreach ($name in $stopped) {
    try {
      Start-Service -Name $name -ErrorAction Stop
      Write-Log "已启动服务: $name"
    } catch {
      Write-Log "启动失败 $name : $($_.Exception.Message)"
    }
  }
  Get-Service -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "actions.runner.*" } |
    ForEach-Object { Write-Log ("服务状态 {0} = {1}" -f $_.Name, $_.Status) }
}

Write-Log "完成"

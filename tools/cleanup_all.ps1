<#
青草编辑器总清理入口
用法：
  powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1            # 管理员
  powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1 -IncludeWorkCache
  powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1 -SkipRunner
#>
param(
  [switch]$DryRun,
  [switch]$IncludeWorkCache,
  [switch]$SkipRunner
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\QingCaoEditor"
$Log = Join-Path $PSScriptRoot "cleanup_all.log"

function Write-Log($msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Write-Host $line
  Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Get-SizeMB($path) {
  if (-not (Test-Path -LiteralPath $path)) { return 0 }
  $sum = (Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object Length -Sum).Sum
  if ($null -eq $sum) { return 0 }
  return [Math]::Round($sum / 1MB, 1)
}

function Remove-Target($path) {
  if (-not (Test-Path -LiteralPath $path)) { return 0 }
  $resolved = (Resolve-Path -LiteralPath $path).Path
  if (-not $resolved.StartsWith($ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Log "安全跳过（不在项目目录）: $resolved"
    return 0
  }
  $size = Get-SizeMB $resolved
  if ($DryRun) {
    Write-Log ("[预览] {0} MB  {1}" -f $size, $resolved)
    return 0
  }
  try {
    Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
    Write-Log ("[删除] {0} MB  {1}" -f $size, $resolved)
    return $size
  } catch {
    Write-Log "删除失败 $resolved : $($_.Exception.Message)"
    return 0
  }
}

$isAdmin = ([Security.Principal.WindowsPrincipal](
  [Security.Principal.WindowsIdentity]::GetCurrent())
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Log "模式: $(if($DryRun){'DryRun'}else{'执行'}) 管理员: $isAdmin"

# 0) 进程检查
$running = Get-Process -Name "QingCaoEditor" -ErrorAction SilentlyContinue
if ($running -and -not $DryRun) {
  throw "检测到 QingCaoEditor 正在运行，请先关闭再清理"
}

$reclaimed = 0

# 1) 旧运行版：保留最新一个
$rr = Join-Path $ProjectRoot "release_runtime"
if (Test-Path $rr) {
  $versions = Get-ChildItem $rr -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
  if ($versions.Count -gt 1) {
    foreach ($v in ($versions | Select-Object -Skip 1)) {
      $reclaimed += Remove-Target $v.FullName
    }
  }
  if ($versions.Count -gt 0) { Write-Log ("保留运行版: " + $versions[0].Name) }
}

# 2) 本地构建/打包产物
$dist = Join-Path $ProjectRoot "dist"
if (Test-Path $dist) {
  $reclaimed += Remove-Target (Join-Path $dist "QingCaoEditor")
  Get-ChildItem $dist -Filter "QingCaoEditor-v*-windows.zip" -File -ErrorAction SilentlyContinue |
    ForEach-Object { $reclaimed += Remove-Target $_.FullName }
  Get-ChildItem $dist -Filter "QingCaoEditor-v*-windows.zip.sha256.txt" -File -ErrorAction SilentlyContinue |
    ForEach-Object { $reclaimed += Remove-Target $_.FullName }
}
$reclaimed += Remove-Target (Join-Path $ProjectRoot "build")

# 3) 旧安装器：保留最新一个
$installer = Join-Path $ProjectRoot "installer"
if (Test-Path $installer) {
  $setups = Get-ChildItem $installer -Filter "QingCaoEditor_Setup_v*.exe" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
  if ($setups.Count -gt 1) {
    foreach ($s in ($setups | Select-Object -Skip 1)) { $reclaimed += Remove-Target $s.FullName }
  }
  if ($setups.Count -gt 0) { Write-Log ("保留安装器: " + $setups[0].Name) }
}

# 4) 测试/演练 dump 与旧回收目录（保留 data\crashes）
$data = Join-Path $ProjectRoot "data"
if (Test-Path $data) {
  foreach ($name in @("crashes_test", "crash_dumps_drill", "crash_dumps_tool")) {
    $reclaimed += Remove-Target (Join-Path $data $name)
  }
  Get-ChildItem $data -Directory -Filter "_trash_*" -ErrorAction SilentlyContinue |
    ForEach-Object { $reclaimed += Remove-Target $_.FullName }
}

Write-Log ("普通清理回收: {0} MB" -f [Math]::Round($reclaimed, 1))

# 5) Runner 清理
if (-not $SkipRunner) {
  $runnerScript = Join-Path $PSScriptRoot "cleanup_runner_artifacts.ps1"
  if (-not (Test-Path $runnerScript)) {
    Write-Log "未找到 Runner 清理脚本，跳过"
  } elseif (-not $isAdmin -and -not $DryRun) {
    Write-Log "非管理员：跳过 Runner 清理（请用管理员运行，或加 -SkipRunner）"
  } else {
    $runnerArgs = @()
    if ($DryRun) { $runnerArgs += "-DryRun" }
    if ($IncludeWorkCache) { $runnerArgs += "-IncludeWorkCache" }
    & powershell -ExecutionPolicy Bypass -File $runnerScript @runnerArgs
  }
}

if (-not $DryRun) {
  $free = (Get-Volume -DriveLetter D).SizeRemaining
  Write-Log ("D 盘可用: {0} GB" -f [Math]::Round($free / 1GB, 1))
}
Write-Log "完成"

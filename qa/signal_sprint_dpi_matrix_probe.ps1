# Real Windows OS DPI probe. Never emulates DPI, changes OS settings, or certifies sales.
param(
  [Parameter(Mandatory=$true)][string]$ExePath,
  [Parameter(Mandatory=$true)][string]$BaseReceiptPath,
  [Parameter(Mandatory=$true)][string]$ProbeReceiptPath,
  [Parameter(Mandatory=$true)][string]$ScreenshotDir,
  [Parameter(Mandatory=$true)][ValidateSet(125,150)][int]$TargetDpiPercent
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$probe = [ordered]@{
  schema_version = 1
  product = 'Signal Sprint'
  registration = 'GDK_GAME'
  immutable_source_sha = 'c058cbf7fe38e02d929c67d047d717ff74bd522e'
  revision_sha = $env:SIGNAL_SPRINT_REVISION_SHA
  workflow_run_id = $env:GITHUB_RUN_ID
  exe_sha256 = $null
  exe_size_bytes = $null
  target_dpi_percent = $TargetDpiPercent
  os_system_dpi_percent = $null
  graphics_dpi_percent = $null
  monitor_bounds = $null
  work_area_bounds = $null
  gui_receipt_path = $null
  text_clipping = 'HOLD_NOT_AUTOMATICALLY_RECOGNIZED'
  uia_text_semantics = 'HOLD_NOT_AUTOMATICALLY_RECOGNIZED'
  human_qa_pass = $false
  sale_ready = $false
  cas_return_pass = $false
  gdk_sdk_executed = $false
  msixvc2_built = $false
  store_submitted = $false
  status = 'HOLD_DPI_UNVERIFIED'
  reason = 'NOT_EXECUTED'
}
try {
  if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'NOT_WINDOWS' }
  if ($env:SIGNAL_SPRINT_REVISION_SHA -notmatch '^[a-f0-9]{40}$') { throw 'REVISION_SHA_NOT_BOUND' }
  $base = Get-Content -LiteralPath $BaseReceiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($base.revision_sha -cne $env:SIGNAL_SPRINT_REVISION_SHA) { throw 'BASE_REVISION_MISMATCH' }
  if ($base.workflow_run_id -cne $env:GITHUB_RUN_ID) { throw 'BASE_RUN_MISMATCH' }
  if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) { throw 'SAME_EXE_MISSING' }
  $probe.exe_sha256 = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
  $probe.exe_size_bytes = (Get-Item -LiteralPath $ExePath).Length
  if ($base.exe_sha256 -cne $probe.exe_sha256 -or $base.exe_size_bytes -ne $probe.exe_size_bytes) { throw 'SAME_EXE_SHA_MISMATCH' }
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SignalSprintSystemDpi {
    [DllImport("user32.dll", ExactSpelling=true)]
    public static extern uint GetDpiForSystem();
}
'@
  $dpi = [SignalSprintSystemDpi]::GetDpiForSystem()
  if ($dpi -gt 0) { $probe.os_system_dpi_percent = [int][Math]::Round($dpi / 96.0 * 100) }
  $g = [System.Drawing.Graphics]::FromHwnd([IntPtr]::Zero)
  try { $probe.graphics_dpi_percent = [int][Math]::Round($g.DpiX / 96.0 * 100) }
  finally { $g.Dispose() }
  $screen = [System.Windows.Forms.Screen]::PrimaryScreen
  if ($null -eq $screen) { throw 'NO_PHYSICAL_MONITOR' }
  $monitor = $screen.Bounds
  $work = $screen.WorkingArea
  $probe.monitor_bounds = @([int]$monitor.Left,[int]$monitor.Top,[int]$monitor.Right,[int]$monitor.Bottom)
  $probe.work_area_bounds = @([int]$work.Left,[int]$work.Top,[int]$work.Right,[int]$work.Bottom)
  if ($null -eq $probe.os_system_dpi_percent -or $null -eq $probe.graphics_dpi_percent -or
      $probe.os_system_dpi_percent -ne $probe.graphics_dpi_percent) {
    $probe.status = 'HOLD_DPI_UNVERIFIED'
    $probe.reason = 'OS_AND_GRAPHICS_DPI_DISAGREE_OR_UNAVAILABLE'
  } elseif ($probe.os_system_dpi_percent -ne $TargetDpiPercent) {
    $probe.status = 'HOLD_OS_DPI_NOT_TARGET'
    $probe.reason = 'REAL_WINDOWS_OS_DPI_NOT_TARGET_NO_EMULATION'
  } elseif ($monitor.Width -ne 1024 -or $monitor.Height -ne 768 -or
            $work.Width -ne 1024 -or $work.Height -ne 720) {
    $probe.status = 'HOLD_DPI_UNVERIFIED'
    $probe.reason = 'PHYSICAL_MONITOR_OR_TASKBAR_WORK_AREA_MISMATCH'
  } else {
    # Only an actual OS display-scale match may run the real same-EXE GUI suite.
    $inner = Join-Path (Split-Path -Parent $ProbeReceiptPath) ("gui-dpi-" + $TargetDpiPercent + ".json")
    $probe.gui_receipt_path = [System.IO.Path]::GetFullPath($inner)
    & (Join-Path $PSScriptRoot 'signal_sprint_ui_revision_gui.ps1') -ExePath $ExePath -ReceiptPath $inner -ScreenshotDir $ScreenshotDir -TargetDpiPercent $TargetDpiPercent
    if ($LASTEXITCODE -ne 0) {
      $probe.status = 'HOLD_GUI_UNVERIFIED'
      $probe.reason = 'REAL_GUI_CHECK_ONLY_FAILED'
    } else {
      $probe.status = 'CHECK_ONLY_REAL_DPI_GUI'
      $probe.reason = 'REAL_OS_DPI_AND_GUI_CHECK_ONLY_NOT_CONSUMER_QA'
    }
  }
} catch {
  $probe.status = 'HOLD_DPI_UNVERIFIED'
  $probe.reason = [string]$_.Exception.Message
} finally {
  $dir = Split-Path -Parent $ProbeReceiptPath
  if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $probe | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ProbeReceiptPath -Encoding UTF8
  Write-Host ($probe | ConvertTo-Json -Compress -Depth 8)
}
# A valid HOLD is data, not a successful DPI test. The Python verifier enforces this.
exit 0

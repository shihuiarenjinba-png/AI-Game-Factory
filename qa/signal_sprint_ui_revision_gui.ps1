# Signal Sprint NEW UI revision: real Windows GUI evidence, never a Store/QA certification.
param(
  [Parameter(Mandatory=$true)][string]$ExePath,
  [Parameter(Mandatory=$true)][string]$ReceiptPath,
  [Parameter(Mandatory=$true)][string]$ScreenshotDir
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$receipt = [ordered]@{
  schema_version = 1
  product = 'Signal Sprint'
  registration = 'GDK_GAME'
  evidence_kind = 'NEW_REVISION_REAL_WINDOWS_GUI_CHECK_ONLY'
  immutable_source_sha = 'c058cbf7fe38e02d929c67d047d717ff74bd522e'
  revision_sha = $env:SIGNAL_SPRINT_REVISION_SHA
  workflow_run_id = $env:GITHUB_RUN_ID
  exe_sha256 = $null
  exe_size_bytes = $null
  monitor_bounds = $null
  work_area_bounds = $null
  window_bounds = $null
  dpi_percent = $null
  jp_window_title_observed = $false
  en_screenshot_sha256 = $null
  jp_screenshot_sha256 = $null
  after_input_screenshot_sha256 = $null
  input_pixel_change_observed = $false
  ui_automation_controls = 'HOLD_UNVERIFIED'
  dpi_125_150 = 'HOLD_NOT_TESTED'
  jp_gameplay_text_verified = $false
  human_qa_pass = $false
  sale_ready = $false
  cas_return_pass = $false
  gdk_sdk_executed = $false
  msixvc2_built = $false
  store_submitted = $false
  status = 'GUI_CHECK_ONLY_HOLD'
  reason = 'NOT_EXECUTED'
}
$proc = $null
function Assert([bool]$condition, [string]$reason) {
  if (-not $condition) { throw $reason }
}
function Capture-Monitor([string]$name, $screen) {
  $bounds = $screen.Bounds
  $bmp = [System.Drawing.Bitmap]::new([int]$bounds.Width, [int]$bounds.Height)
  try {
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    try {
      $graphics.CopyFromScreen([int]$bounds.Left, [int]$bounds.Top, 0, 0,
                               ([System.Drawing.Size]::new([int]$bounds.Width, [int]$bounds.Height)))
    } finally { $graphics.Dispose() }
    $path = Join-Path $ScreenshotDir $name
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  } finally { $bmp.Dispose() }
}
function Press-Key([string]$key, [int]$pidValue) {
  [Microsoft.VisualBasic.Interaction]::AppActivate($pidValue) | Out-Null
  Start-Sleep -Milliseconds 200
  [System.Windows.Forms.SendKeys]::SendWait($key)
  Start-Sleep -Milliseconds 400
}
try {
  Assert ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) 'NOT_WINDOWS'
  Assert ([bool]($env:SIGNAL_SPRINT_REVISION_SHA -match '^[0-9a-f]{40}$')) 'REVISION_SHA_NOT_BOUND'
  Assert (Test-Path -LiteralPath $ExePath -PathType Leaf) 'REVISION_EXE_MISSING'
  $receipt.exe_size_bytes = (Get-Item -LiteralPath $ExePath).Length
  $receipt.exe_sha256 = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
  Assert ($receipt.exe_size_bytes -gt 100000) 'REVISION_EXE_TOO_SMALL'
  $bytes = [System.IO.File]::OpenRead((Resolve-Path -LiteralPath $ExePath).Path)
  try {
    Assert ($bytes.ReadByte() -eq 77 -and $bytes.ReadByte() -eq 90) 'REVISION_EXE_NOT_PE'
  } finally { $bytes.Dispose() }
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  Add-Type -AssemblyName Microsoft.VisualBasic
  New-Item -ItemType Directory -Force -Path $ScreenshotDir | Out-Null
  $exe = (Resolve-Path -LiteralPath $ExePath).Path
  $proc = Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -PassThru
  $window = $null
  $guiProcess = $null
  for ($attempt = 0; $attempt -lt 45; $attempt++) {
    Start-Sleep -Milliseconds 500
    $proc.Refresh()
    Assert (-not $proc.HasExited) 'REVISION_EXE_EXITED_BEFORE_GUI'
    $candidates = @($proc)
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($proc.Id)" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
      $candidate = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
      if ($null -ne $candidate) { $candidates += $candidate }
    }
    foreach ($candidate in $candidates) {
      $candidate.Refresh()
      if ($candidate.HasExited -or $candidate.MainWindowHandle -eq [IntPtr]::Zero) { continue }
      $element = [System.Windows.Automation.AutomationElement]::FromHandle($candidate.MainWindowHandle)
      if ($null -ne $element -and $element.Current.Name -eq 'Signal Sprint | EN') {
        $window = $element
        $guiProcess = $candidate
        break
      }
    }
    if ($null -ne $window) { break }
  }
  Assert ($null -ne $window) 'REAL_GUI_WINDOW_NOT_FOUND'
  $screen = [System.Windows.Forms.Screen]::FromHandle($guiProcess.MainWindowHandle)
  $monitor = $screen.Bounds
  $work = $screen.WorkingArea
  $win = $window.Current.BoundingRectangle
  $receipt.monitor_bounds = @([int]$monitor.Left,[int]$monitor.Top,[int]$monitor.Right,[int]$monitor.Bottom)
  $receipt.work_area_bounds = @([int]$work.Left,[int]$work.Top,[int]$work.Right,[int]$work.Bottom)
  $receipt.window_bounds = @([int]$win.Left,[int]$win.Top,[int]$win.Right,[int]$win.Bottom)
  $g = [System.Drawing.Graphics]::FromHwnd($guiProcess.MainWindowHandle)
  try { $receipt.dpi_percent = [int][math]::Round($g.DpiX / 96.0 * 100) }
  finally { $g.Dispose() }
  Assert ($monitor.Width -eq 1024 -and $monitor.Height -eq 768) 'NOT_1024x768_REAL_MONITOR'
  Assert ($receipt.dpi_percent -eq 100) 'DPI_COORDINATES_UNVERIFIED_125_150_HOLD'
  Assert ($win.Width -gt 700 -and $win.Height -gt 500) 'WINDOW_UNEXPECTEDLY_SMALL'
  Assert ($win.Left -ge $work.Left -and $win.Top -ge $work.Top -and
          $win.Right -le $work.Right -and $win.Bottom -le $work.Bottom) 'WINDOW_OUTSIDE_WORK_AREA'
  $receipt.en_screenshot_sha256 = Capture-Monitor 'signal-sprint-en.png' $screen
  try {
    $condition = [System.Windows.Automation.PropertyCondition]::new(
      [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
      [System.Windows.Automation.ControlType]::Button)
    $controls = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
    if ($controls.Count -gt 0) {
      $receipt.ui_automation_controls = 'OBSERVED_NOT_CONSUMER_CERTIFIED'
      $receipt.control_count = $controls.Count
    }
  } catch { $receipt.ui_automation_controls = 'HOLD_UNAVAILABLE' }
  Press-Key 'j' $guiProcess.Id
  Assert ($window.Current.Name -eq 'Signal Sprint | JP') 'JAPANESE_TOGGLE_NOT_OBSERVED'
  $receipt.jp_window_title_observed = $true
  $receipt.jp_screenshot_sha256 = Capture-Monitor 'signal-sprint-jp.png' $screen
  Assert ($receipt.en_screenshot_sha256 -ne $receipt.jp_screenshot_sha256) 'JAPANESE_SCREEN_NO_PIXEL_CHANGE'
  Press-Key '{RIGHT}' $guiProcess.Id
  $receipt.after_input_screenshot_sha256 = Capture-Monitor 'signal-sprint-jp-after-right.png' $screen
  $receipt.input_pixel_change_observed = $receipt.jp_screenshot_sha256 -ne $receipt.after_input_screenshot_sha256
  Assert ($receipt.input_pixel_change_observed) 'FIRST_INPUT_NO_PIXEL_CHANGE'
  $receipt.status = 'GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY'
  $receipt.reason = 'REAL_WINDOW_AND_IMAGES_OBSERVED; JP_GAMEPLAY_TEXT_AND_DPI_125_150_NOT_CERTIFIED'
} catch {
  $receipt.status = 'GUI_CHECK_ONLY_HOLD'
  $receipt.reason = [string]$_.Exception.Message
} finally {
  if ($null -ne $proc) {
    try {
      $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($proc.Id)" -ErrorAction SilentlyContinue)
      foreach ($child in $children) { Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue }
      Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    } catch { $receipt.cleanup_warning = $_.Exception.Message }
  }
  $parent = Split-Path -Parent $ReceiptPath
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
  Write-Host ($receipt | ConvertTo-Json -Compress -Depth 8)
}
if ($receipt.status -ne 'GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY') { exit 2 }
exit 0

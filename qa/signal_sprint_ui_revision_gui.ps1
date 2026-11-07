# Signal Sprint NEW UI revision: real Windows GUI evidence, never a Store/QA certification.
param(
  [Parameter(Mandatory=$true)][string]$ExePath,
  [Parameter(Mandatory=$true)][string]$ReceiptPath,
  [Parameter(Mandatory=$true)][string]$ScreenshotDir,
  [ValidateSet(100,125,150)][int]$TargetDpiPercent = 100
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
  exe_path = $null
  exe_size_bytes = $null
  monitor_bounds = $null
  work_area_bounds = $null
  window_bounds = $null
  dpi_percent = $null
  target_dpi_percent = $TargetDpiPercent
  en_window_sha256 = $null
  en_after_input_window_sha256 = $null
  en_pre_exhaustion_window_sha256 = $null
  en_exhausted_window_sha256 = $null
  en_post_exhaustion_restart_window_sha256 = $null
  en_replay_window_sha256 = $null
  en_exhaustion_move_count = 0
  en_exhaustion_input_sequence = $null
  en_exhaustion_gui_check_only = 'HOLD_NOT_EXECUTED'
  en_lost_text_semantics = 'HOLD_UNVERIFIED'
  language_matrix_status = 'HOLD_NOT_EXECUTED'
  jp_window_title_observed = $false
  en_screenshot_sha256 = $null
  jp_screenshot_sha256 = $null
  after_input_screenshot_sha256 = $null
  jp_window_sha256 = $null
  after_input_window_sha256 = $null
  restart_window_sha256 = $null
  retry_restores_initial_window_pixels = $false
  retry_gui_check_only = 'HOLD_NOT_TESTED'
  exhaustion_input_sequence = $null
  exhaustion_move_count = 0
  pre_exhaustion_window_sha256 = $null
  exhausted_window_sha256 = $null
  post_exhaustion_restart_window_sha256 = $null
  replay_window_sha256 = $null
  exhaustion_pixel_change_observed = $false
  exhaustion_reset_pixel_match = $false
  replay_pixel_match = $false
  lost_text_semantics = 'HOLD_UNVERIFIED'
  jp_en_text_clipping = 'HOLD_UNMEASURED'
  dpi_125 = 'HOLD_UNMEASURED'
  dpi_150 = 'HOLD_UNMEASURED'
  exhaustion_gui_check_only = 'HOLD_NOT_EXECUTED'
  input_pixel_change_observed = $false
  ui_automation_controls = 'HOLD_UNVERIFIED'
  en_buttons_in_workarea = 'HOLD_UNMEASURED'
  jp_buttons_in_workarea = 'HOLD_UNMEASURED'
  dpi_125_150 = 'HOLD_NOT_TESTED'
  jp_gameplay_text_verified = $false
  human_qa_pass = $false
  sale_ready = $false
  cas_return_pass = $false
  gdk_sdk_executed = $false
  msixvc2_built = $false
  store_submitted = $false
  focus_evidence = @()
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
function Capture-Window([string]$name, $rect) {
  # Crop to the measured visible game window, excluding taskbar/clock.
  $left = [int][math]::Floor($rect.Left)
  $top = [int][math]::Floor($rect.Top)
  $width = [int][math]::Ceiling($rect.Width)
  $height = [int][math]::Ceiling($rect.Height)
  Assert ($width -gt 700 -and $height -gt 500) 'RETRY_WINDOW_BOUNDS_INVALID'
  $bmp = [System.Drawing.Bitmap]::new($width, $height)
  try {
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    try {
      $graphics.CopyFromScreen($left, $top, 0, 0,
                               ([System.Drawing.Size]::new($width, $height)))
    } finally { $graphics.Dispose() }
    $path = Join-Path $ScreenshotDir $name
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  } finally { $bmp.Dispose() }
}
function Capture-UIATree([string]$phase, $window) {
  # Capture actual Windows UIA evidence, including when the strict gate fails.
  $entries = @()
  $errorText = $null
  try {
    $elements = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,
      [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($element in $elements) {
      try {
        $c = $element.Current
        $b = $c.BoundingRectangle
        $entries += [ordered]@{
          control_type = [string]$c.ControlType.ProgrammaticName
          name = [string]$c.Name
          automation_id = [string]$c.AutomationId
          process_id = [int]$c.ProcessId
          is_enabled = [bool]$c.IsEnabled
          is_offscreen = [bool]$c.IsOffscreen
          bounds = @([double]$b.Left,[double]$b.Top,[double]$b.Right,[double]$b.Bottom)
        }
      } catch {
        $entries += [ordered]@{ read_error = [string]$_.Exception.Message }
      }
    }
  } catch { $errorText = [string]$_.Exception.Message }
  $filename = "signal-sprint-uia-$phase.json"
  $destination = Join-Path $ScreenshotDir $filename
  $snapshot = [ordered]@{
    phase = $phase
    expected_process_id = [int]$guiProcess.Id
    elements = $entries
    enumeration_error = $errorText
  }
  $snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $destination -Encoding UTF8
  $receipt["uia_tree_$phase"] = [ordered]@{
    path = $filename
    sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    element_count = $entries.Count
    enumeration_error = $errorText
  }
}
function Check-VisibleButtons([string]$language, $window, $work) {
  # UIA is supplementary to the physical GetWindowRect/monitor screenshot.
  # An unavailable Tk UIA tree must NEVER become a fabricated visibility PASS.
  try {
    $condition = [System.Windows.Automation.PropertyCondition]::new(
      [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
      [System.Windows.Automation.ControlType]::Button)
    $controls = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
    if ($controls.Count -lt 5) { return 'HOLD_UIA_FIVE_BUTTONS_NOT_EXPOSED' }
    $names = @()
    foreach ($control in $controls) {
      $rect = $control.Current.BoundingRectangle
      Assert ($rect.Width -gt 0 -and $rect.Height -gt 0 -and
              $rect.Left -ge $work.Left -and $rect.Top -ge $work.Top -and
              $rect.Right -le $work.Right -and $rect.Bottom -le $work.Bottom) 'BUTTON_OUTSIDE_TASKBAR_WORKAREA'
      if ($control.Current.Name) { $names += [string]$control.Current.Name }
    }
    $all = $names -join ' '
    if ($language -eq 'EN') {
      if ($all -notmatch 'Start|Retry|Restart' -or $all -notmatch '\u65e5\u672c\u8a9e') {
        return 'HOLD_UIA_EN_BUTTON_LABELS_NOT_EXPOSED'
      }
    } else {
      if ($all -notmatch '\u518d\u6311\u6226|\u6700\u521d\u304b\u3089' -or $all -notmatch 'English') {
        return 'HOLD_UIA_JP_BUTTON_LABELS_NOT_EXPOSED'
      }
    }
    return 'REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY'
  } catch {
    if ($_.Exception.Message -eq 'BUTTON_OUTSIDE_TASKBAR_WORKAREA') { throw }
    return 'HOLD_UIA_BUTTONS_UNAVAILABLE'
  }
}
# Native foreground-window ownership is measured immediately before every key.
# AppActivate returning successfully is not evidence that the game owns focus.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SignalSprintForeground {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@
$focusEvidence = [System.Collections.Generic.List[object]]::new()
$script:inputPhase = 'JP_TOGGLE'
$script:inputLanguage = 'EN'
function Press-Key([string]$key, [int]$pidValue) {
  [Microsoft.VisualBasic.Interaction]::AppActivate($pidValue) | Out-Null
  Start-Sleep -Milliseconds 200
  $foreground = [SignalSprintForeground]::GetForegroundWindow()
  [uint32]$foregroundPid = 0
  if ($foreground -ne [IntPtr]::Zero) {
    [void][SignalSprintForeground]::GetWindowThreadProcessId($foreground, [ref]$foregroundPid)
  }
  $owned = ($foreground -ne [IntPtr]::Zero -and $foregroundPid -eq [uint32]$pidValue)
  $focusEvidence.Add([ordered]@{ sequence = $focusEvidence.Count + 1; phase = $script:inputPhase; language = $script:inputLanguage; key = $key; expected_pid = $pidValue; foreground_pid = $foregroundPid; foreground_handle = $foreground.ToInt64(); owned_before_input = $owned })
  Assert $owned 'FOCUS_OWNER_MISMATCH_BEFORE_KEY'
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
  # Keep the exact executed PE inside the evidence root for independent hashing.
  $evidenceExeName = 'signal-sprint-qa-executed.exe'
  $evidenceExe = Join-Path $ScreenshotDir $evidenceExeName
  $sourceExe = (Resolve-Path -LiteralPath $ExePath).Path
  Copy-Item -LiteralPath $sourceExe -Destination $evidenceExe -Force
  Assert ((Get-FileHash -LiteralPath $evidenceExe -Algorithm SHA256).Hash.ToLowerInvariant() -eq $receipt.exe_sha256) 'EVIDENCE_EXE_COPY_HASH_MISMATCH'
  $receipt.exe_path = $evidenceExeName
  # Execute the original location so bundled assets and working directory remain unchanged.
  $exe = $sourceExe
  # The EXE starts in dist/game; use an absolute path so its fail-closed
  # physical-geometry trace is uploaded with evidence even if Tk exits.
  $env:SIGNAL_SPRINT_LAYOUT_TRACE = Join-Path (Get-Location).Path 'evidence/workarea-layout-trace.json'
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
  Assert ($receipt.dpi_percent -eq $TargetDpiPercent) 'REAL_GUI_DPI_NOT_REQUESTED_TARGET_HOLD'
  Assert ($win.Width -gt 700 -and $win.Height -gt 500) 'WINDOW_UNEXPECTEDLY_SMALL'
  Assert ($win.Left -ge $work.Left -and $win.Top -ge $work.Top -and
          $win.Right -le $work.Right -and $win.Bottom -le $work.Bottom) 'WINDOW_OUTSIDE_WORK_AREA'
  $receipt.en_screenshot_sha256 = Capture-Monitor 'signal-sprint-en.png' $screen
  Capture-UIATree 'en-initial' $window
  $receipt.en_buttons_in_workarea = Check-VisibleButtons 'EN' $window $work
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
  $script:inputLanguage = 'JP'
  $script:inputPhase = 'JP_FIRST_MOVE'
  Assert ($window.Current.Name -eq 'Signal Sprint | JP') 'JAPANESE_TOGGLE_NOT_OBSERVED'
  $receipt.jp_window_title_observed = $true
  $receipt.jp_screenshot_sha256 = Capture-Monitor 'signal-sprint-jp.png' $screen
  Capture-UIATree 'jp-initial' $window
  $receipt.jp_buttons_in_workarea = Check-VisibleButtons 'JP' $window $work
  Assert ($receipt.en_screenshot_sha256 -ne $receipt.jp_screenshot_sha256) 'JAPANESE_SCREEN_NO_PIXEL_CHANGE'
  $receipt.jp_window_sha256 = Capture-Window 'signal-sprint-jp-window-initial.png' $win
  Press-Key '{RIGHT}' $guiProcess.Id
  $receipt.after_input_screenshot_sha256 = Capture-Monitor 'signal-sprint-jp-after-right.png' $screen
  $receipt.input_pixel_change_observed = $receipt.jp_screenshot_sha256 -ne $receipt.after_input_screenshot_sha256
  Assert ($receipt.input_pixel_change_observed) 'FIRST_INPUT_NO_PIXEL_CHANGE'
  $receipt.after_input_window_sha256 = Capture-Window 'signal-sprint-jp-window-after-right.png' $win
  Assert ($receipt.after_input_window_sha256 -ne $receipt.jp_window_sha256) 'RETRY_PRECONDITION_MOVE_NOT_VISIBLE'
  $script:inputPhase = 'JP_RESET'
  Press-Key 'r' $guiProcess.Id
  Assert ($window.Current.Name -eq 'Signal Sprint | JP') 'RETRY_CHANGED_LANGUAGE'
  $retryWin = $window.Current.BoundingRectangle
  Assert ([int]$retryWin.Left -eq [int]$win.Left -and
          [int]$retryWin.Top -eq [int]$win.Top -and
          [int]$retryWin.Width -eq [int]$win.Width -and
          [int]$retryWin.Height -eq [int]$win.Height) 'RETRY_WINDOW_GEOMETRY_CHANGED'
  $receipt.restart_window_sha256 = Capture-Window 'signal-sprint-jp-window-after-restart.png' $retryWin
  $receipt.retry_restores_initial_window_pixels =
    ($receipt.restart_window_sha256 -eq $receipt.jp_window_sha256)
  Assert ($receipt.retry_restores_initial_window_pixels) 'RETRY_DID_NOT_RESTORE_INITIAL_GUI_PIXELS'
  $receipt.retry_gui_check_only = 'REAL_R_KEY_RESET_PIXEL_MATCH_CHECK_ONLY'
  # This is the SAME real Windows EXE and the SAME process. Start from the
  # proven reset screen; use 30 legal corridor moves (RIGHT, LEFT, repeated).
  # The immutable Game.move() source determines the expected LOST state.
  $script:inputPhase = 'JP_EXHAUSTION'
  $sequence = @()
  for ($turn = 1; $turn -le 30; $turn++) {
    $key = if ($turn % 2 -eq 1) { '{RIGHT}' } else { '{LEFT}' }
    Press-Key $key $guiProcess.Id
    $sequence += $(if ($turn % 2 -eq 1) { 'RIGHT' } else { 'LEFT' })
    $guiProcess.Refresh()
    Assert (-not $guiProcess.HasExited) 'EXHAUSTION_GAME_PROCESS_EXITED'
    $current = $window.Current.BoundingRectangle
    Assert ($current.Left -ge $work.Left -and $current.Top -ge $work.Top -and
            $current.Right -le $work.Right -and $current.Bottom -le $work.Bottom) 'EXHAUSTION_WINDOW_OUTSIDE_WORK_AREA'
    Assert ($window.Current.Name -eq 'Signal Sprint | JP') 'EXHAUSTION_LANGUAGE_CHANGED'
    if ($turn -eq 29) {
      $receipt.pre_exhaustion_window_sha256 = Capture-Window 'signal-sprint-jp-turn-29.png' $current
    }
  }
  $receipt.exhaustion_input_sequence = $sequence
  $receipt.exhaustion_move_count = $sequence.Count
  Assert ($receipt.exhaustion_move_count -eq 30) 'EXHAUSTION_INPUT_COUNT_WRONG'
  $exhaustedRect = $window.Current.BoundingRectangle
  $receipt.exhausted_window_sha256 = Capture-Window 'signal-sprint-jp-turn-30-expected-lost.png' $exhaustedRect
  Assert ($receipt.exhausted_window_sha256 -ne $receipt.pre_exhaustion_window_sha256) 'EXHAUSTION_LAST_MOVE_NO_PIXEL_CHANGE'
  $receipt.exhaustion_pixel_change_observed = $true
  Capture-UIATree 'jp-lost' $window
  # Tk widgets may not expose their text through UIAutomation. A changed
  # screenshot is NOT proof that the visible message actually says LOST.
  try {
    $allText = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,
      [System.Windows.Automation.Condition]::TrueCondition)
    $names = @()
    foreach ($element in $allText) {
      try { if ($element.Current.Name) { $names += [string]$element.Current.Name } } catch {}
    }
    if (($names -join ' ') -match '\u5931\u6557' -and ($names -join ' ') -match '\u624b\u6570\u304c\u306a\u304f\u306a\u308a\u307e\u3057\u305f') {
      $receipt.lost_text_semantics = 'UIAUTOMATION_JP_LOST_TEXT_OBSERVED'
    } else {
      $receipt.lost_text_semantics = 'HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED'
    }
  } catch { $receipt.lost_text_semantics = 'HOLD_UIAUTOMATION_UNAVAILABLE' }
  $receipt.exhaustion_gui_check_only = 'REAL_30_KEYS_AND_CHANGED_LAST_FRAME_CHECK_ONLY'
  $script:inputPhase = 'JP_LOST_RETRY'
  Press-Key 'r' $guiProcess.Id
  $resetRect = $window.Current.BoundingRectangle
  Assert ($resetRect.Left -ge $work.Left -and $resetRect.Top -ge $work.Top -and
          $resetRect.Right -le $work.Right -and $resetRect.Bottom -le $work.Bottom) 'EXHAUSTION_RESET_OUTSIDE_WORK_AREA'
  $receipt.post_exhaustion_restart_window_sha256 = Capture-Window 'signal-sprint-jp-after-lost-restart.png' $resetRect
  $receipt.exhaustion_reset_pixel_match = ($receipt.post_exhaustion_restart_window_sha256 -eq $receipt.jp_window_sha256)
  Assert ($receipt.exhaustion_reset_pixel_match) 'EXHAUSTION_R_DID_NOT_RESTORE_INITIAL_PIXELS'
  $script:inputPhase = 'JP_REPLAY'
  Press-Key '{RIGHT}' $guiProcess.Id
  $replayRect = $window.Current.BoundingRectangle
  $receipt.replay_window_sha256 = Capture-Window 'signal-sprint-jp-after-lost-replay-right.png' $replayRect
  $receipt.replay_pixel_match = ($receipt.replay_window_sha256 -eq $receipt.after_input_window_sha256)
  Assert ($receipt.replay_pixel_match) 'EXHAUSTION_REPLAY_FIRST_MOVE_MISMATCH'
  # Independent EN 30-turn exhaustion, restart and replay in the SAME process
  # and same packaged EXE. The JP screenshots above are never relabeled EN.
  $script:inputPhase = 'EN_TOGGLE'
  Press-Key 'j' $guiProcess.Id
  $script:inputLanguage = 'EN'
  Assert ($window.Current.Name -eq 'Signal Sprint | EN') 'ENGLISH_TOGGLE_NOT_OBSERVED'
  $script:inputPhase = 'EN_RESET'
  Press-Key 'r' $guiProcess.Id
  $enRect = $window.Current.BoundingRectangle
  Assert ($enRect.Left -ge $work.Left -and $enRect.Top -ge $work.Top -and
          $enRect.Right -le $work.Right -and $enRect.Bottom -le $work.Bottom) 'EN_INITIAL_OUTSIDE_WORK_AREA'
  $receipt.en_window_sha256 = Capture-Window 'signal-sprint-en-window-initial.png' $enRect
  $script:inputPhase = 'EN_FIRST_MOVE'
  Press-Key '{RIGHT}' $guiProcess.Id
  $receipt.en_after_input_window_sha256 = Capture-Window 'signal-sprint-en-window-after-right.png' $window.Current.BoundingRectangle
  Assert ($receipt.en_after_input_window_sha256 -ne $receipt.en_window_sha256) 'EN_FIRST_MOVE_NO_CHANGE'
  $script:inputPhase = 'EN_PRE_EXHAUSTION_RESET'
  Press-Key 'r' $guiProcess.Id
  $enReset = Capture-Window 'signal-sprint-en-window-before-exhaustion.png' $window.Current.BoundingRectangle
  Assert ($enReset -eq $receipt.en_window_sha256) 'EN_PRE_EXHAUSTION_RESET_MISMATCH'
  $script:inputPhase = 'EN_EXHAUSTION'
  $enSequence = @()
  for ($turn = 1; $turn -le 30; $turn++) {
    $key = if ($turn % 2 -eq 1) { '{RIGHT}' } else { '{LEFT}' }
    Press-Key $key $guiProcess.Id
    $enSequence += $(if ($turn % 2 -eq 1) { 'RIGHT' } else { 'LEFT' })
    $guiProcess.Refresh()
    Assert (-not $guiProcess.HasExited) 'EN_EXHAUSTION_PROCESS_EXITED'
    $current = $window.Current.BoundingRectangle
    Assert ($current.Left -ge $work.Left -and $current.Top -ge $work.Top -and
            $current.Right -le $work.Right -and $current.Bottom -le $work.Bottom) 'EN_EXHAUSTION_OUTSIDE_WORK_AREA'
    Assert ($window.Current.Name -eq 'Signal Sprint | EN') 'EN_EXHAUSTION_LANGUAGE_CHANGED'
    if ($turn -eq 29) {
      $receipt.en_pre_exhaustion_window_sha256 = Capture-Window 'signal-sprint-en-turn-29.png' $current
    }
  }
  $receipt.en_exhaustion_input_sequence = $enSequence
  $receipt.en_exhaustion_move_count = $enSequence.Count
  Assert ($receipt.en_exhaustion_move_count -eq 30) 'EN_MOVE_COUNT_WRONG'
  $receipt.en_exhausted_window_sha256 = Capture-Window 'signal-sprint-en-turn-30-expected-lost.png' $window.Current.BoundingRectangle
  Assert ($receipt.en_exhausted_window_sha256 -ne $receipt.en_pre_exhaustion_window_sha256) 'EN_LAST_MOVE_NO_PIXEL_CHANGE'
  # Persist the English LOST UIA tree before semantic checks; screenshots are not text proof.
  Capture-UIATree 'en-lost' $window
  try {
    $allText = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,
      [System.Windows.Automation.Condition]::TrueCondition)
    $names = @()
    foreach ($element in $allText) {
      try { if ($element.Current.Name) { $names += [string]$element.Current.Name } } catch {}
    }
    if (($names -join ' ') -match 'LOST' -and ($names -join ' ') -match 'Out of moves') {
      $receipt.en_lost_text_semantics = 'UIAUTOMATION_EN_LOST_TEXT_OBSERVED'
    } else {
      $receipt.en_lost_text_semantics = 'HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED'
    }
  } catch { $receipt.en_lost_text_semantics = 'HOLD_UIAUTOMATION_UNAVAILABLE' }
  $script:inputPhase = 'EN_LOST_RETRY'
  Press-Key 'r' $guiProcess.Id
  $receipt.en_post_exhaustion_restart_window_sha256 = Capture-Window 'signal-sprint-en-after-lost-restart.png' $window.Current.BoundingRectangle
  Assert ($receipt.en_post_exhaustion_restart_window_sha256 -eq $receipt.en_window_sha256) 'EN_R_DID_NOT_RESTORE_INITIAL_PIXELS'
  $script:inputPhase = 'EN_REPLAY'
  Press-Key '{RIGHT}' $guiProcess.Id
  $receipt.en_replay_window_sha256 = Capture-Window 'signal-sprint-en-after-lost-replay-right.png' $window.Current.BoundingRectangle
  Assert ($receipt.en_replay_window_sha256 -eq $receipt.en_after_input_window_sha256) 'EN_REPLAY_FIRST_MOVE_MISMATCH'
  $receipt.en_exhaustion_gui_check_only = 'REAL_EN_30_KEYS_RESTART_REPLAY_CHECK_ONLY'
  $receipt.language_matrix_status = 'REAL_JP_AND_EN_SAME_EXE_CHECK_ONLY'
  if ($TargetDpiPercent -eq 125) { $receipt.dpi_125 = 'REAL_OS_DPI_125_GUI_CHECK_ONLY' }
  if ($TargetDpiPercent -eq 150) { $receipt.dpi_150 = 'REAL_OS_DPI_150_GUI_CHECK_ONLY' }
  if ($TargetDpiPercent -ne 100) { $receipt.dpi_125_150 = 'HOLD_OTHER_DPI_NOT_TESTED' }
  # Visible pixels and bounds do not prove that all glyphs are legible.
  # UIAutomation may not expose Tk labels. Keep text clipping HOLD.
  # DPI 125/150 and actual JP/EN glyph clipping need separate real runs.
  # Never infer these PASS from 100% DPI or from synthetic geometry.
  $receipt.status = 'GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY'
  $receipt.reason = 'REAL_JP_EN_30_INPUTS_RESTART_REPLAY_CHECK_ONLY; UIA_TEXT_AND_GLYPH_CLIPPING_HOLD; OTHER_OS_DPI_NOT_INFERRED'
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
  # Diagnostic evidence is recorded even when the strict UIA gate fails.
  # Never turn missing controls or text into a PASS based on screenshots.
  $receipt.uia_gate_checks = [ordered]@{
    en_buttons = [ordered]@{ observed = $receipt.en_buttons_in_workarea; pass = ($receipt.en_buttons_in_workarea -eq 'REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY') }
    jp_buttons = [ordered]@{ observed = $receipt.jp_buttons_in_workarea; pass = ($receipt.jp_buttons_in_workarea -eq 'REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY') }
    jp_lost_text = [ordered]@{ observed = $receipt.lost_text_semantics; pass = ($receipt.lost_text_semantics -eq 'UIAUTOMATION_JP_LOST_TEXT_OBSERVED') }
    en_lost_text = [ordered]@{ observed = $receipt.en_lost_text_semantics; pass = ($receipt.en_lost_text_semantics -eq 'UIAUTOMATION_EN_LOST_TEXT_OBSERVED') }
  }
  $receipt.uia_gate_failed_checks = @($receipt.uia_gate_checks.Keys | Where-Object { -not $receipt.uia_gate_checks[$_].pass })
  if ($receipt.uia_gate_failed_checks.Count -gt 0) {
    Write-Warning ('STRICT_UIA_MISSING: ' + ($receipt.uia_gate_failed_checks -join ', '))
  }
  $receipt.focus_evidence = @($focusEvidence.ToArray())
  $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
  Write-Host ($receipt | ConvertTo-Json -Compress -Depth 8)
}
if ($receipt.status -ne 'GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY') { exit 2 }
if (@($receipt.focus_evidence).Count -lt 1 -or @($receipt.focus_evidence | Where-Object { -not $_.owned_before_input }).Count -gt 0) { exit 3 }
if ($receipt.en_buttons_in_workarea -ne 'REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY' -or $receipt.jp_buttons_in_workarea -ne 'REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY' -or $receipt.lost_text_semantics -ne 'UIAUTOMATION_JP_LOST_TEXT_OBSERVED' -or $receipt.en_lost_text_semantics -ne 'UIAUTOMATION_EN_LOST_TEXT_OBSERVED') { exit 4 }
exit 0

# Windows desktop UIA dynamic gate. Run in an INTERACTIVE Windows user session.
# This is deliberately fail-closed; CI without an unlocked desktop cannot certify UIA.
param([Parameter(Mandatory)][string]$ExePath,
      [Parameter(Mandatory)][string]$OutputPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$expected = @{
 EN = @('Start / Retry (R)','Undo (U)','Save (Ctrl+S)','Load (L)','日本語 (J)')
 JP = @('開始 / 再挑戦 (R)','1手戻す (U)','保存 (Ctrl+S)','読込 (L)','English (J)')
}
$receipt = [ordered]@{
 schema = 'signal-sprint-dynamic-uia-v1'
 source_head = '1a349faa41663c417c40710140a4d50c79b62b78'
 executable_sha256 = $null
 evidence = @()
 status = 'HOLD'
 errors = @()
}
$process = $null
try {
 if (-not [Environment]::UserInteractive) { throw 'NO_INTERACTIVE_WINDOWS_DESKTOP' }
 if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) { throw 'EXE_MISSING' }
 $receipt.executable_sha256 = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
 # Every action starts from an isolated process to prevent state leakage.
 foreach ($language in @('EN','JP')) {
  foreach ($targetName in $expected[$language]) {
   $process = Start-Process -FilePath (Resolve-Path $ExePath).Path -WorkingDirectory (Split-Path (Resolve-Path $ExePath).Path) -PassThru
   $window = $null
   for ($attempt=0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    $process.Refresh()
    if ($process.HasExited) { throw 'GUI_PROCESS_EXITED' }
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) {
     $window = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
     if ($window.Current.Name -eq 'Signal Sprint | EN') { break }
    }
   }
   if ($null -eq $window -or $window.Current.Name -ne 'Signal Sprint | EN') { throw 'EN_WINDOW_NOT_FOUND' }
   $condition = [System.Windows.Automation.PropertyCondition]::new(
      [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
      [System.Windows.Automation.ControlType]::Button)
   function Get-Buttons($w) {
     $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)
     $names = @($all | ForEach-Object { [string]$_.Current.Name })
     return [pscustomobject]@{ Controls=$all; Names=$names }
   }
   if ($language -eq 'JP') {
     $before = Get-Buttons $window
     $toggle = @($before.Controls | Where-Object { $_.Current.Name -ceq '日本語 (J)' })
     if ($toggle.Count -ne 1) { throw 'EN_TOGGLE_NOT_UNIQUE' }
     $p = $toggle[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
     $p.Invoke()
     Start-Sleep -Milliseconds 500
     if ($window.Current.Name -ne 'Signal Sprint | JP') { throw 'JP_TOGGLE_NO_STATE_TRANSITION' }
   }
   $buttons = Get-Buttons $window
   $observed = @($buttons.Names | Sort-Object)
   $wanted = @($expected[$language] | Sort-Object)
   if ($buttons.Controls.Count -ne 5 -or ($observed -join [char]0) -cne ($wanted -join [char]0)) {
     throw "BUTTON_EXACT_SET_MISMATCH:$language; observed=$($buttons.Names -join ',')"
   }
   $matches = @($buttons.Controls | Where-Object { $_.Current.Name -ceq $targetName })
   if ($matches.Count -ne 1) { throw "BUTTON_NOT_UNIQUE:$targetName" }
   $button = $matches[0]
   if ($button.Current.ControlType -ne [System.Windows.Automation.ControlType]::Button -or
       -not $button.Current.IsEnabled -or $button.Current.IsOffscreen) { throw "BUTTON_NOT_ACCESSIBLE:$targetName" }
   $pattern = $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
   $button.SetFocus()
   Start-Sleep -Milliseconds 100
   if (-not [System.Windows.Automation.AutomationElement]::FocusedElement.Equals($button)) { throw "FOCUS_FAILED:$targetName" }
   # Capture UIA-visible state before invoking; title alone is not game-state evidence.
   $beforeTitle = $window.Current.Name
   $beforeNodes = @($window.FindAll([System.Windows.Automation.TreeScope]::Descendants,
     [System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object {
       [string]$_.Current.ControlType.ProgrammaticName + ':' + [string]$_.Current.Name
     })
   $pattern.Invoke()
   Start-Sleep -Milliseconds 400
   $afterTitle = $window.Current.Name
   $afterNodes = @($window.FindAll([System.Windows.Automation.TreeScope]::Descendants,
     [System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object {
       [string]$_.Current.ControlType.ProgrammaticName + ':' + [string]$_.Current.Name
     })
   $transition = ($beforeTitle -cne $afterTitle)
   $uiaStateChanged = (($beforeNodes -join [char]0) -cne ($afterNodes -join [char]0))
   $lostNodes = @($afterNodes | Where-Object { $_ -match '(?i)(^|[^a-z])LOST([^a-z]|$)' })
   $receipt.evidence += [ordered]@{
     language=$language; name=$targetName; control_type='ControlType.Button'
     invoke_pattern=$true; focus=$true; invoked=$true
     title_before=$beforeTitle; title_after=$afterTitle
     title_transition=$transition; uia_tree_changed=$uiaStateChanged
     uia_before=$beforeNodes; uia_after=$afterNodes
     lost_uia_nodes=$lostNodes
     side_effect_verified=$false # Requires action-specific semantic assertion
   }
   # Only language toggle has an unconditional observable title transition.
   if ($targetName -in @('日本語 (J)','English (J)') -and -not $transition) {
     throw "LANGUAGE_INVOKE_NO_TRANSITION:$language"
   }
   Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
   $process = $null
  }
 }
 # Remaining actions require explicit game-state assertions, not mere Invoke success.
 throw 'INCOMPLETE_GAME_STATE_AND_LOST_ASSERTIONS'
} catch {
 $receipt.errors += [string]$_.Exception.Message
} finally {
 if ($null -ne $process) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
 $folder = Split-Path -Parent $OutputPath
 if ($folder) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
 $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
exit 4

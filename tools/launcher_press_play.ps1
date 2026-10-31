# Runs ON the hidden desktop next to the launcher: UI Automation sees only the windows of its own desktop.
# Lists the buttons of the launcher window and presses the play button once it is enabled.
param([int] $LauncherPid, [string] $Out, [int] $Seconds = 180)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$scope = [System.Windows.Automation.TreeScope]
$byPid = New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, $LauncherPid)
$isButton = New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
$log = New-Object System.Collections.Generic.List[string]
$deadline = (Get-Date).AddSeconds($Seconds)
$pressed = $false
$last = ''
while ((Get-Date) -lt $deadline -and -not $pressed) {
    try {
        foreach ($w in $A::RootElement.FindAll($scope::Children, $byPid)) {
            $buttons = @($w.FindAll($scope::Descendants, $isButton))
            $names = ($buttons | ForEach-Object { $_.Current.Name + $(if ($_.Current.IsEnabled) { '' } else { ' (off)' }) }) -join ' | '
            $line = "window '$($w.Current.Name)': $names"
            if ($line -ne $last) { $log.Add(('{0:HH:mm:ss} {1}' -f (Get-Date), $line)); $last = $line }
            foreach ($b in $buttons) {
                if ($b.Current.Name -in @('Играть', 'Play') -and $b.Current.IsEnabled -and -not $b.Current.IsOffscreen) {
                    $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
                    $log.Add(('{0:HH:mm:ss} pressed ''{1}''' -f (Get-Date), $b.Current.Name))
                    $pressed = $true
                    break
                }
            }
            if ($pressed) { break }
        }
    }
    catch { $log.Add(('{0:HH:mm:ss} {1}' -f (Get-Date), $_.Exception.Message)) }
    if (-not $pressed) { Start-Sleep -Seconds 2 }
}
if (-not $pressed) { $log.Add('play button not pressed') }
$log | Set-Content -LiteralPath $Out -Encoding UTF8
if ($pressed) { exit 0 } else { exit 1 }

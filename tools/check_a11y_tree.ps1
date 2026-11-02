# UI Automation accessibility tree check (NVDA substitute, v2.18)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$needle = [string]([char]0x9752) + [char]0x8349
$sig = @"
using System;
using System.Runtime.InteropServices;
public class WinEnum {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lp);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr hWnd, System.Text.StringBuilder sb, int n);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@
Add-Type -TypeDefinition $sig
$handles = New-Object System.Collections.ArrayList
$titles = New-Object System.Collections.ArrayList
$cb = [WinEnum+EnumProc]{
    param($h, $l)
    $sb = New-Object System.Text.StringBuilder 512
    [void][WinEnum]::GetWindowTextW($h, $sb, 512)
    $t = $sb.ToString()
    if ($t -and $t.Contains($needle) -and [WinEnum]::IsWindowVisible($h)) {
        [void]$handles.Add($h); [void]$titles.Add($t)
    }
    return $true
}
[void][WinEnum]::EnumWindows($cb, [IntPtr]::Zero)
Write-Output ("A11Y_WINDOWS=" + $handles.Count)
if ($handles.Count -eq 0) { Write-Output 'NO_WINDOW'; exit 1 }
$best = 0
for ($i = 0; $i -lt $handles.Count; $i++) { if ($titles[$i].Length -gt $titles[$best].Length) { $best = $i } }
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$handles[$best])
if ($null -eq $root) { Write-Output 'NO_UIA_ROOT'; exit 1 }
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$items = New-Object System.Collections.ArrayList
function Walk($el, $depth) {
    if ($null -eq $el -or $depth -gt 6 -or $items.Count -ge 400) { return }
    $name = $el.Current.Name
    $ctype = $el.Current.ControlType.ProgrammaticName
    if ($name -or $ctype) { [void]$items.Add([pscustomobject]@{Depth=$depth; Name=$name; Type=$ctype}) }
    $child = $walker.GetFirstChild($el)
    while ($null -ne $child) { Walk $child ($depth + 1); $child = $walker.GetNextSibling($child) }
}
Walk $root 0
Write-Output ("A11Y_ELEMENTS=" + $items.Count)
$named = ($items | Where-Object { $_.Name }).Count
Write-Output ("A11Y_NAMED=" + $named)
$items | Select-Object -First 25 | ForEach-Object { Write-Output ("{0}{1} [{2}]" -f ('  ' * $_.Depth), $_.Name, $_.Type) }
if ($named -ge 20) { Write-Output 'A11Y_PASS' } else { Write-Output 'A11Y_FAIL' }
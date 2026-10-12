param([string]$InitialPath, [Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$picker = New-Object System.Windows.Forms.FolderBrowserDialog
$picker.Description = 'Choose where to save your private mobile libraries. A subfolder is created for each game.'
$picker.ShowNewFolderButton = $true
if ($InitialPath -and (Test-Path -LiteralPath $InitialPath -PathType Container)) { $picker.SelectedPath = $InitialPath }
try {
    if ($picker.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        @{folder=$picker.SelectedPath} | ConvertTo-Json -Compress | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    }
} finally { $picker.Dispose() }

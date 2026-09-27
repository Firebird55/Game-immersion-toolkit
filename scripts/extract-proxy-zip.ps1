param(
    [string]$ZipPath = (Join-Path (Join-Path $env:USERPROFILE 'Downloads') 'gamesenteneminer-public-contents.zip')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$prefix = 'gamesenteneminer/'
$statusPath = Join-Path $root 'install-progress.json'
$archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)

try {
    $entries = @($archive.Entries)
    $totalBytes = [long](($entries | Measure-Object Length -Sum).Sum)
    $doneBytes = [long]0
    $doneEntries = 0
    $script:lastReportedPercent = -1
    $script:lastStatus = [DateTime]::MinValue
    $buffer = [byte[]]::new(1024 * 1024)

    function Update-Status([string]$phase) {
        $percent = if ($totalBytes -eq 0) { 100.0 } else { [Math]::Round(100.0 * $doneBytes / $totalBytes, 1) }
        [pscustomobject]@{
            phase = $phase
            percent = $percent
            bytesDone = $doneBytes
            bytesTotal = $totalBytes
            entriesDone = $doneEntries
            entriesTotal = $entries.Count
            updatedAt = (Get-Date).ToString('o')
        } | ConvertTo-Json -Compress | Set-Content -LiteralPath $statusPath -Encoding UTF8
        Write-Progress -Activity 'Extracting Proxy Transcript ZIP' -Status "$percent% by bytes; $doneEntries / $($entries.Count) entries" -PercentComplete ([Math]::Min(100, [int]$percent))
        if ([int]$percent -ge $script:lastReportedPercent + 5) {
            Write-Output "Extracted $percent% by bytes ($doneEntries / $($entries.Count) entries)"
            $script:lastReportedPercent = [int]$percent
        }
        $script:lastStatus = Get-Date
    }

    Update-Status 'extracting'
    foreach ($entry in $entries) {
        if (-not $entry.FullName.StartsWith($prefix, [StringComparison]::Ordinal)) {
            throw "Unexpected ZIP path: $($entry.FullName)"
        }
        $relative = $entry.FullName.Substring($prefix.Length).Replace('/', [IO.Path]::DirectorySeparatorChar)
        if (-not $relative) { $doneEntries++; continue }
        $destination = [IO.Path]::GetFullPath([IO.Path]::Combine($root, $relative))
        if (-not $destination.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "ZIP path escapes target: $($entry.FullName)"
        }
        if ($entry.FullName.EndsWith('/')) {
            [IO.Directory]::CreateDirectory($destination) | Out-Null
        }
        else {
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
            $inputStream = $entry.Open()
            $outputStream = [IO.File]::Open($destination, [IO.FileMode]::Create, [IO.FileAccess]::Write)
            try {
                while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $outputStream.Write($buffer, 0, $read)
                    $doneBytes += $read
                    if (((Get-Date) - $lastStatus).TotalSeconds -ge 2) { Update-Status 'extracting' }
                }
            }
            finally {
                $outputStream.Dispose()
                $inputStream.Dispose()
            }
            [IO.File]::SetLastWriteTime($destination, $entry.LastWriteTime.LocalDateTime)
        }
        $doneEntries++
        if (((Get-Date) - $lastStatus).TotalSeconds -ge 2) { Update-Status 'extracting' }
    }
    Update-Status 'complete'
    Write-Progress -Activity 'Extracting Proxy Transcript ZIP' -Completed
}
catch {
    [pscustomobject]@{
        phase = 'failed'
        percent = if ($totalBytes -gt 0) { [Math]::Round(100.0 * $doneBytes / $totalBytes, 1) } else { 0 }
        entriesDone = $doneEntries
        entriesTotal = $entries.Count
        error = $_.Exception.Message
        updatedAt = (Get-Date).ToString('o')
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $statusPath -Encoding UTF8
    throw
}
finally { $archive.Dispose() }

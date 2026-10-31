# Build-host probe support only. Include Windows Hidden/System entries and empty
# directories: a content-only or non-Force scan cannot prove no application writes.
function Get-R19RuntimeInventory([string]$Root) {
    return @(Get-ChildItem -LiteralPath $Root -Recurse -Force | Sort-Object FullName | ForEach-Object {
        $name = [IO.Path]::GetRelativePath($Root, $_.FullName).Replace('\', '/')
        if ($_.PSIsContainer) { 'directory:' + $name }
        else { 'file:' + $name + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
}

function Test-R19RuntimeInventory([string]$TemporaryRoot) {
    # Independently authored Windows attributes catch omission of hidden files,
    # hidden directory traversal and empty directories before any pass is emitted.
    $fixture = Join-Path $TemporaryRoot ('r19-inventory-fixture-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $fixture | Out-Null
    try {
        $folder = Join-Path $fixture 'hidden-folder'
        $empty = Join-Path $fixture 'hidden-empty'
        New-Item -ItemType Directory -Path $folder, $empty | Out-Null
        $file = Join-Path $fixture 'hidden.txt'
        $child = Join-Path $folder 'child.txt'
        [IO.File]::WriteAllText($file, 'owned inventory fixture', [Text.UTF8Encoding]::new($false))
        Copy-Item -LiteralPath $file -Destination $child
        foreach ($path in @($folder, $empty, $file)) {
            [IO.File]::SetAttributes($path, ([IO.File]::GetAttributes($path) -bor [IO.FileAttributes]::Hidden -bor [IO.FileAttributes]::System))
        }
        $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = @('directory:hidden-empty', 'directory:hidden-folder', ('file:hidden.txt:' + $hash), ('file:hidden-folder/child.txt:' + $hash))
        $before = @(Get-R19RuntimeInventory $fixture)
        if (@(Compare-Object $expected $before -CaseSensitive).Count) { throw 'Windows inventory omitted a hidden file, directory or descendant.' }
        # Windows refuses CREATE_ALWAYS for an existing Hidden/System file.
        # Open it in place so the mutation retains the attributes under test.
        $stream = [IO.File]::Open($file, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $changed = [Text.Encoding]::UTF8.GetBytes('changed owned fixture')
            $stream.SetLength(0)
            $stream.Write($changed, 0, $changed.Length)
        } finally { $stream.Dispose() }
        if (-not @(Compare-Object $before @(Get-R19RuntimeInventory $fixture) -CaseSensitive).Count) { throw 'Windows inventory failed to detect a hidden file content change.' }
    } finally {
        Remove-Item -LiteralPath $fixture -Recurse -Force
    }
}

#requires -Version 7.2

function Assert-AndroidNoLinks([string]$Path, [string]$Label='Android build input') {
    $candidatePath=[IO.Path]::GetFullPath($Path)
    while($candidatePath) {
        if((Test-Path -LiteralPath $candidatePath) -and ((Get-Item -LiteralPath $candidatePath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw ($Label+' cannot follow filesystem links.')
        }
        $candidatePath=[IO.Path]::GetDirectoryName($candidatePath)
    }
}

function Resolve-AndroidSupplierPath([string]$Path, [string]$Label, [string[]]$ProbeFiles) {
    # Read-only installed tools may have publisher/runner-managed aliases.
    # Resolve those aliases, verify identical supplier bytes, then apply the
    # ordinary no-reparse guard to the physical result. Never use this function
    # for writable build roots, user libraries or frontend/wheelhouse inputs.
    $originalPath=(Get-Item -LiteralPath $Path -Force -ErrorAction Stop).FullName
    $originalHashes=@{}
    foreach($relative in $ProbeFiles) {
        if([IO.Path]::IsPathRooted($relative) -or ($relative -split '[/\\]') -contains '..') {throw 'Unsafe supplier probe name.'}
        $probePath=if($relative){Join-Path $originalPath $relative}else{$originalPath}
        $originalHashes[$relative]=(Get-FileHash -LiteralPath $probePath -Algorithm SHA256 -ErrorAction Stop).Hash
    }
    $physicalPath=$originalPath
    for($attempt=0;$attempt -lt 32;$attempt++) {
        $candidatePath=$physicalPath
        $changed=$false
        while($candidatePath) {
            $item=Get-Item -LiteralPath $candidatePath -Force -ErrorAction Stop
            if($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                $target=$item.ResolveLinkTarget($true)
                if(-not $target){throw ($Label+' supplier alias has no physical target.')}
                $suffix=$physicalPath.Substring($candidatePath.Length).TrimStart([char[]]'\/')
                $physicalPath=if($suffix){Join-Path $target.FullName $suffix}else{$target.FullName}
                $physicalPath=[IO.Path]::GetFullPath($physicalPath)
                $changed=$true
                break
            }
            $candidatePath=[IO.Path]::GetDirectoryName($candidatePath)
        }
        if(-not $changed) {
            Assert-AndroidNoLinks $physicalPath $Label
            foreach($relative in $ProbeFiles) {
                $probePath=if($relative){Join-Path $physicalPath $relative}else{$physicalPath}
                Assert-AndroidNoLinks $probePath $Label
                if((Get-FileHash -LiteralPath $probePath -Algorithm SHA256).Hash -ne $originalHashes[$relative]) {
                    throw ($Label+' physical supplier differs from its installed alias.')
                }
            }
            return $physicalPath
        }
    }
    throw ($Label+' supplier aliases exceed the bounded resolution depth.')
}

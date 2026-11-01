param([Parameter(Mandatory = $true)][string]$OutputRoot)
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
$pin = Get-Content -LiteralPath (Join-Path $SourceRoot 'packaging/desktop/inno-setup.json') -Raw | ConvertFrom-Json
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw 'Choose a new compiler directory; existing tools are preserved.' }
$ancestor = [IO.DirectoryInfo]$OutputRoot
while ($null -ne $ancestor) {
    if ($ancestor.Exists -and (($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw 'Compiler path cannot traverse reparse points.' }
    $ancestor = $ancestor.Parent
}
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$archive = Join-Path $OutputRoot $pin.filename
Invoke-WebRequest -Uri $pin.url -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) { throw 'Installer compiler supplier hash mismatch.' }
$signature = Get-AuthenticodeSignature -LiteralPath $archive
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch ('(?:^|, )CN=' + [regex]::Escape($pin.publisher) + '(?:,|$)')) {
    throw 'Installer compiler signature/publisher verification failed.'
}
$destination = Join-Path $OutputRoot 'compiler'
$process = Start-Process -FilePath $archive -WindowStyle Hidden -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/CURRENTUSER','/NOICONS',('/DIR="' + $destination + '"')) -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Build-host installer compiler setup failed.' }
$compiler = Join-Path $destination 'ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'Installer compiler executable is missing.' }
Write-Output $compiler

param([Parameter(Mandatory=$true)][string]$IdentityRoot,[Parameter(Mandatory=$true)][string]$JavaHome)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'android-build-paths.ps1')
. (Join-Path $PSScriptRoot 'android-signing.ps1')
$JavaHome=Resolve-AndroidSupplierPath $JavaHome 'Signing Java' @('bin/keytool.exe')
Initialize-AndroidSigningIdentity $IdentityRoot $JavaHome | ConvertTo-Json

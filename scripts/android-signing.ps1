# Windows owner-host identity. Keys and DPAPI ciphertext never enter CI/source.
function Assert-AndroidSigningAcl([string]$Path) {
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $acl=Get-Acl -LiteralPath $Path
    if($acl.Owner -ne [Security.Principal.WindowsIdentity]::GetCurrent().Name -and $acl.Owner -ne $sid) {throw 'The Android signing identity has a different owner.'}
    foreach($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
        if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin @($sid,'S-1-5-18')) {
            throw 'The Android signing identity grants access outside its owner and SYSTEM.'
        }
    }
}
function Open-AndroidSigningIdentity([string]$Root) {
    if(-not $IsWindows){throw 'Owner signing identities require Windows CurrentUser protected storage.'}
    $Root=[IO.Path]::GetFullPath($Root)
    Assert-AndroidNoLinks $Root
    $repository=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\','/')
    if($Root -eq $repository -or $Root.StartsWith($repository+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'The signing identity must be outside the source checkout.'
    }
    Assert-AndroidSigningAcl $Root
    foreach($name in @('identity.json','owner.p12','password.dpapi','certificate.der')) {
        $file=Join-Path $Root $name
        Assert-AndroidNoLinks $file
        if(-not (Test-Path -LiteralPath $file -PathType Leaf)){throw 'The owner signing identity is incomplete.'}
        Assert-AndroidSigningAcl $file
    }
    return $Root
}
function Initialize-AndroidSigningIdentity([string]$Root,[string]$JavaHome) {
    if(-not $IsWindows){throw 'Owner signing identities require Windows CurrentUser protected storage.'}
    $Root=[IO.Path]::GetFullPath($Root)
    Assert-AndroidNoLinks $Root
    if(Test-Path -LiteralPath $Root){throw 'An existing signing identity is never overwritten.'}
    $repository=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\','/')
    if($Root -eq $repository -or $Root.StartsWith($repository+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Keep signing identities outside source.'}
    New-Item -ItemType Directory -Path $Root | Out-Null
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl=[Security.AccessControl.DirectorySecurity]::new();$acl.SetOwner($sid);$acl.SetAccessRuleProtection($true,$false)
    foreach($identity in @($sid,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
    }
    Set-Acl -LiteralPath $Root -AclObject $acl
    Assert-AndroidSigningAcl $Root
    $password=[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
    $previous=$env:TOOLKIT_OWNER_KEY_PASSWORD
    try {
        $env:TOOLKIT_OWNER_KEY_PASSWORD=$password
        $keytool=Join-Path $JavaHome 'bin/keytool.exe'
        & $keytool -genkeypair -alias toolkit-owner -keyalg RSA -keysize 3072 -validity 10000 -storetype PKCS12 -dname 'CN=Game Immersion Toolkit,O=Toolkit,C=NL' -storepass:env TOOLKIT_OWNER_KEY_PASSWORD -keypass:env TOOLKIT_OWNER_KEY_PASSWORD -keystore (Join-Path $Root 'owner.p12') 2>&1 | Out-Null
        if($LASTEXITCODE -ne 0){throw 'Could not initialize the owner signing key.'}
        & $keytool -exportcert -alias toolkit-owner -storepass:env TOOLKIT_OWNER_KEY_PASSWORD -keystore (Join-Path $Root 'owner.p12') -file (Join-Path $Root 'certificate.der') 2>&1 | Out-Null
        if($LASTEXITCODE -ne 0){throw 'Could not record the owner public certificate.'}
        $bytes=[Text.Encoding]::UTF8.GetBytes($password)
        try {$encrypted=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)}
        finally {[Array]::Clear($bytes,0,$bytes.Length)}
        [IO.File]::WriteAllBytes((Join-Path $Root 'password.dpapi'),$encrypted)
        $record=[ordered]@{schema='toolkit-android-owner-signing-v1';application_id='io.github.firebird55.gameimmersiontoolkit';alias='toolkit-owner';signing_certificate_sha256=(Get-FileHash -LiteralPath (Join-Path $Root 'certificate.der') -Algorithm SHA256).Hash.ToLowerInvariant();last_reserved_version_code=0}
        [IO.File]::WriteAllText((Join-Path $Root 'identity.json'),($record | ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))
        Open-AndroidSigningIdentity $Root | Out-Null
        return [pscustomobject]@{application_id=$record.application_id;signing_certificate_sha256=$record.signing_certificate_sha256}
    } finally {$env:TOOLKIT_OWNER_KEY_PASSWORD=$previous;$password=$null}
}
function Reserve-AndroidSigningVersion([string]$Root,[int]$VersionCode) {
    $Root=Open-AndroidSigningIdentity $Root
    Assert-AndroidNoLinks (Join-Path $Root 'build.lock')
    Assert-AndroidNoLinks (Join-Path $Root 'identity.pending')
    $lock=[IO.File]::Open((Join-Path $Root 'build.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try {
        $record=Get-Content -LiteralPath (Join-Path $Root 'identity.json') -Raw | ConvertFrom-Json
        if($record.schema -ne 'toolkit-android-owner-signing-v1' -or $record.application_id -ne 'io.github.firebird55.gameimmersiontoolkit' -or $record.alias -ne 'toolkit-owner' -or
            $record.signing_certificate_sha256 -notmatch '^[0-9a-f]{64}$' -or ($record.last_reserved_version_code -isnot [long] -and $record.last_reserved_version_code -isnot [int]) -or
            $record.last_reserved_version_code -lt 0 -or $VersionCode -le $record.last_reserved_version_code -or $VersionCode -gt 2100000000) {throw 'The owner identity or increasing Android version code is invalid.'}
        if((Get-FileHash -LiteralPath (Join-Path $Root 'certificate.der') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.signing_certificate_sha256){throw 'The owner public certificate changed.'}
        $bytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $Root 'password.dpapi')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        try {$password=[Text.Encoding]::UTF8.GetString($bytes)} finally {[Array]::Clear($bytes,0,$bytes.Length)}
        if($password.Length -ne 64){throw 'The protected signing password is invalid.'}
        $record.last_reserved_version_code=$VersionCode
        $pending=Join-Path $Root 'identity.pending'
        [IO.File]::WriteAllText($pending,($record | ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))
        [IO.File]::Move($pending,(Join-Path $Root 'identity.json'),$true)
        return [pscustomobject]@{root=$Root;password=$password;record=$record;lock=$lock}
    } catch {$lock.Dispose();throw}
}

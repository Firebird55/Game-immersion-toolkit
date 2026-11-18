param(
    [Parameter(Mandatory=$true)][string]$SdkRoot,
    [Parameter(Mandatory=$true)][string]$Wheelhouse,
    [Parameter(Mandatory=$true)][string]$Frontend,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$JavaHome,
    [Parameter(Mandatory=$true)][string]$NdkArchive,
    [Parameter(Mandatory=$true)][string]$PublisherCryptoSourceArchive,
    [string]$DecoderSourceArchive,
    [string]$GradleUserHome,
    [ValidateSet('debug','ownerCandidate')][string]$Variant='debug',
    [string]$SigningIdentityRoot,
    [int]$VersionCode=0,
    [switch]$DownloadGradle,
    [switch]$DownloadDecoderSource
)
function Read-AndroidBoundBaseReceipt([string]$Wheelhouse,$CompositeReceipt,[string]$BasePolicySha256) {
    if($CompositeReceipt.schema -ne 'toolkit-android-runtime-wheels-v2' -or $CompositeReceipt.base_receipt_sha256 -notmatch '^[0-9a-f]{64}$') {throw 'The verified composite base-receipt binding is missing.'}
    $basePath=Join-Path $Wheelhouse 'python-base-wheels-receipt.json'
    Assert-AndroidNoLinks $basePath
    if((Get-Item -LiteralPath $basePath).Length -gt 1048576){throw 'The bound Python base receipt exceeds its limit.'}
    $baseBytes=[IO.File]::ReadAllBytes($basePath)
    $baseDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($baseBytes)).ToLowerInvariant()
    if($baseDigest -ne $CompositeReceipt.base_receipt_sha256){throw 'The bound original Python receipt changed before native APK validation.'}
    $baseReceipt=[Text.Encoding]::UTF8.GetString($baseBytes) | ConvertFrom-Json
    if($baseReceipt.schema -ne 'toolkit-android-python-wheels-v1' -or $baseReceipt.policy_sha256 -ne $BasePolicySha256){throw 'The bound original Python receipt has an unexpected schema or policy.'}
    return $baseReceipt
}
$ErrorActionPreference='Stop'
$sourceRoot=Split-Path -Parent $PSScriptRoot
$policy=Get-Content -LiteralPath (Join-Path $sourceRoot 'packaging/android/build-inputs.json') -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot 'android-build-paths.ps1')
. (Join-Path $PSScriptRoot 'android-signing.ps1')
if($Variant -eq 'ownerCandidate' -and ($env:GITHUB_ACTIONS -eq 'true' -or -not $SigningIdentityRoot -or $VersionCode -lt 1)) {throw 'Owner candidates require a protected local identity and explicit increasing version code on the owner host.'}
if($Variant -eq 'debug' -and $SigningIdentityRoot){throw 'CI/debug candidates cannot use the owner signing identity.'}
if($VersionCode -eq 0){$VersionCode=1}
if($VersionCode -lt 1 -or $VersionCode -gt 2100000000){throw 'Invalid Android version code.'}
$SdkRoot=Resolve-AndroidSupplierPath $SdkRoot 'Android SDK' @("platforms/android-$($policy.compile_sdk)/android.jar","build-tools/$($policy.build_tools)/aapt2.exe","build-tools/$($policy.build_tools)/zipalign.exe")
$Python=Resolve-AndroidSupplierPath $Python 'Build Python' @('')
$JavaHome=Resolve-AndroidSupplierPath $JavaHome 'Build Java' @('bin/java.exe','bin/keytool.exe')
foreach($item in @($SdkRoot,$Wheelhouse,$Frontend,$BuildRoot,$Python,$JavaHome,$NdkArchive,$PublisherCryptoSourceArchive)) {Assert-AndroidNoLinks $item}
$BuildRoot=[IO.Path]::GetFullPath($BuildRoot)
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
foreach($name in @('temp','gradle-user','android-user','avd')) {New-Item -ItemType Directory -Path (Join-Path $BuildRoot $name) -Force | Out-Null}
$env:TEMP=Join-Path $BuildRoot 'temp';$env:TMP=$env:TEMP;$env:TMPDIR=$env:TEMP
$env:JAVA_HOME=$JavaHome
$env:JAVA_TOOL_OPTIONS='-Djava.io.tmpdir='+$env:TEMP.Replace('\','/')
$env:ANDROID_HOME=$SdkRoot;$env:ANDROID_SDK_ROOT=$SdkRoot
$env:ANDROID_USER_HOME=Join-Path $BuildRoot 'android-user'
$env:ANDROID_EMULATOR_HOME=$env:ANDROID_USER_HOME
$env:ANDROID_AVD_HOME=Join-Path $BuildRoot 'avd'
$env:GRADLE_USER_HOME=if($GradleUserHome){[IO.Path]::GetFullPath($GradleUserHome)}else{Join-Path $BuildRoot 'gradle-user'}
Assert-AndroidNoLinks $env:GRADLE_USER_HOME
$env:ANDROID_PYTHON_WHEELHOUSE=$Wheelhouse
$env:ANDROID_FRONTEND_DIR=$Frontend
$env:TOOLKIT_BUILD_PYTHON=$Python
$env:ANDROID_DEBUG_KEYSTORE=Join-Path $BuildRoot 'debug.keystore'
$decoderRoot=Join-Path $BuildRoot 'data-decoders'
if(-not $DecoderSourceArchive){$DecoderSourceArchive=Join-Path $decoderRoot 'capstone-5.0.7.tar.gz'}
Assert-AndroidNoLinks $DecoderSourceArchive
$decoderArgs=@((Join-Path $PSScriptRoot 'build-android-data-decoders.py'),'--work-dir',$decoderRoot,
    '--source-archive',$DecoderSourceArchive,'--ndk-root',(Join-Path $SdkRoot 'ndk/27.3.13750724'),'--ndk-archive',$NdkArchive)
if($DownloadDecoderSource){$decoderArgs+='--download'}
& $Python @decoderArgs
if($LASTEXITCODE -ne 0){throw 'The authenticated original-data decoder software build failed.'}
$env:ANDROID_DATA_DECODERS=$decoderRoot
$cryptoRoot=Join-Path $BuildRoot 'publisher-crypto'
& $Python (Join-Path $PSScriptRoot 'build-android-publisher-crypto.py') --work-dir $cryptoRoot --source-archive $PublisherCryptoSourceArchive --ndk-root (Join-Path $SdkRoot 'ndk/27.3.13750724') --ndk-archive $NdkArchive
if($LASTEXITCODE -ne 0){throw 'The authenticated publisher cryptography software build failed.'}
$env:ANDROID_PUBLISHER_CRYPTO=$cryptoRoot
$env:ANDROID_CRYPTO_FIXTURES=Join-Path $BuildRoot 'crypto-authored'
& $Python (Join-Path $PSScriptRoot 'prepare-publisher-crypto-probes.py') --work-dir $env:ANDROID_CRYPTO_FIXTURES --fixtures-only
if($LASTEXITCODE -ne 0){throw 'The bounded authored cryptography fixtures could not be prepared.'}
$env:ANDROID_WUWA_FIXTURE=Join-Path $BuildRoot 'wuwa-authored-bootstrap.json'
& $Python (Join-Path $PSScriptRoot 'prepare-android-wuwa-probe.py') --output $env:ANDROID_WUWA_FIXTURE
if($LASTEXITCODE -ne 0){throw 'The bounded authored publisher bootstrap fixture could not be prepared.'}
& $Python (Join-Path $PSScriptRoot 'prepare-android-runtime-wheels.py') --verify $Wheelhouse
if($LASTEXITCODE -ne 0){throw 'Compose the reviewed base and native-extension cohorts into a new Android runtime wheelhouse.'}
$receipt=Get-Content -LiteralPath (Join-Path $Wheelhouse 'python-wheels-receipt.json') -Raw | ConvertFrom-Json
$policyHash=(Get-FileHash -LiteralPath (Join-Path $sourceRoot 'packaging/android/python-dependencies.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$frontendManifest=Get-Content -LiteralPath (Join-Path $Frontend 'desktop-manifest.json') -Raw | ConvertFrom-Json
if($frontendManifest.runtime -ne 'static-local-no-node') {throw 'The actual shared desktop frontend is required.'}
Push-Location -LiteralPath $sourceRoot
try {
    & node --input-type=module -e 'import {verifyDesktopOutput} from "./scripts/build-desktop-frontend.mjs";const m=verifyDesktopOutput(process.argv[1]);console.log("Verified shared frontend",m.build_id)' $Frontend
    if($LASTEXITCODE -ne 0){throw 'The shared desktop frontend did not verify.'}
} finally {Pop-Location}
$archive=Join-Path $BuildRoot ('gradle-'+$policy.gradle.version+'-bin.zip')
if(-not (Test-Path -LiteralPath $archive)) {
    if(-not $DownloadGradle){throw 'Acquire the pinned original Gradle archive first.'}
    $http=[Net.Http.HttpClient]::new()
    try {
        $inputStream=$http.GetStreamAsync($policy.gradle.source).GetAwaiter().GetResult()
        $outputStream=[IO.File]::Create($archive)
        try {
            $block=[byte[]]::new(1024*1024);$total=0
            while(($read=$inputStream.Read($block,0,$block.Length)) -gt 0) {
                $total+=$read
                if($total -gt $policy.gradle.maximum_bytes){throw 'Gradle download exceeds its bound.'}
                $outputStream.Write($block,0,$read)
            }
        } finally {$outputStream.Dispose();$inputStream.Dispose()}
    } finally {$http.Dispose()}
}
if((Get-Item -LiteralPath $archive).Length -gt $policy.gradle.maximum_bytes -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $policy.gradle.sha256) {throw 'Gradle supplier checksum mismatch.'}
$gradleRoot=Join-Path $BuildRoot ('gradle-'+$policy.gradle.version)
if(-not (Test-Path -LiteralPath (Join-Path $gradleRoot 'bin/gradle.bat'))) {Expand-Archive -LiteralPath $archive -DestinationPath $BuildRoot}
if($Variant -eq 'debug' -and -not (Test-Path -LiteralPath $env:ANDROID_DEBUG_KEYSTORE)) {
    & (Join-Path $JavaHome 'bin/keytool.exe') -genkeypair -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Android Debug,O=Android,C=US' -storepass android -keypass android -keystore $env:ANDROID_DEBUG_KEYSTORE
    if($LASTEXITCODE -ne 0){throw 'Could not create the local authored-test signing identity.'}
}
$head=(& git -C $sourceRoot rev-parse HEAD).Trim()
$dirty=!!(& git -C $sourceRoot status --porcelain)
$identity=$null
$previousPassword=$env:TOOLKIT_OWNER_KEY_PASSWORD
$previousKeystore=$env:ANDROID_OWNER_KEYSTORE
$previousVersion=$env:ANDROID_VERSION_CODE
try {
if($Variant -eq 'ownerCandidate') {
    $identity=Reserve-AndroidSigningVersion $SigningIdentityRoot $VersionCode
    $env:TOOLKIT_OWNER_KEY_PASSWORD=$identity.password
    $env:ANDROID_OWNER_KEYSTORE=Join-Path $identity.root 'owner.p12'
} else {$env:TOOLKIT_OWNER_KEY_PASSWORD=$null;$env:ANDROID_OWNER_KEYSTORE=$null}
$env:ANDROID_VERSION_CODE=[string]$VersionCode
$task=if($Variant -eq 'debug'){'assembleDebug'}else{'assembleOwnerCandidate'}
& (Join-Path $gradleRoot 'bin/gradle.bat') --no-daemon -p (Join-Path $sourceRoot 'packaging/android') ":app:$task" --console=plain
if($LASTEXITCODE -ne 0){throw 'Android candidate compilation failed.'}
$apk=Join-Path $sourceRoot "packaging/android/app/build/outputs/apk/$Variant/app-$Variant.apk"
$audit=Join-Path $BuildRoot 'apk-audit.json'
& $Python (Join-Path $PSScriptRoot 'verify-android-apk.py') $apk --output $audit
if($LASTEXITCODE -ne 0){throw 'The Android APK failed its closed native/shared-core audit.'}
$nativeAudit=Get-Content -LiteralPath $audit -Raw | ConvertFrom-Json
$baseReceipt=Read-AndroidBoundBaseReceipt $Wheelhouse $receipt $policyHash
foreach($abi in $policy.abis) {
    $nativeReceipt=$baseReceipt.native.PSObject.Properties[$abi].Value
    $cores=@($nativeAudit.native_files.PSObject.Properties | Where-Object { $_.Name.StartsWith('assets/chaquopy/requirements-'+$abi+'.imy/pydantic_core/_pydantic_core') })
    if($cores.Count -ne 1 -or $cores[0].Value.sha256 -ne $nativeReceipt.native_sha256) {throw 'The packaged native core differs from its verified wheel.'}
    $rapid=$baseReceipt.rapidfuzz_native.PSObject.Properties[$abi].Value
    if(-not $rapid -or -not $rapid.modules) {throw 'The native RapidFuzz build receipt is missing.'}
    foreach($module in $rapid.modules.PSObject.Properties) {
        $name='assets/chaquopy/requirements-'+$abi+'.imy/'+$module.Name
        if($nativeAudit.native_files.PSObject.Properties[$name].Value.sha256 -ne $module.Value.sha256) {throw 'Packaged RapidFuzz differs from its verified source-built wheel.'}
    }
}
& (Join-Path $SdkRoot ('build-tools/'+$policy.build_tools+'/apksigner.bat')) verify --verbose --print-certs $apk > (Join-Path $BuildRoot 'apk-signature.txt')
if($LASTEXITCODE -ne 0){throw 'The APK signature is invalid.'}
$signature=Get-Content -LiteralPath (Join-Path $BuildRoot 'apk-signature.txt') -Raw
$certificates=[regex]::Matches($signature,'(?m)^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})\r?$')
if($certificates.Count -ne 1){throw 'An unambiguous APK signing certificate is required.'}
$certificate=$certificates[0].Groups[1].Value.ToLowerInvariant()
if($identity -and $certificate -ne $identity.record.signing_certificate_sha256){throw 'The APK does not use the protected owner signing identity.'}
$badging=& (Join-Path $SdkRoot ('build-tools/'+$policy.build_tools+'/aapt2.exe')) dump badging $apk
if($LASTEXITCODE -ne 0){throw 'Could not verify the installed Android identity.'}
$package=[regex]::Match(($badging -join "`n"),"(?m)^package: name='([^']+)' versionCode='([0-9]+)'")
$expectedApplication=if($Variant -eq 'debug'){'io.github.firebird55.gameimmersiontoolkit.debug'}else{$identity.record.application_id}
if(-not $package.Success -or $package.Groups[1].Value -ne $expectedApplication -or $package.Groups[2].Value -ne [string]$VersionCode){throw 'The packaged application identity/version differs from the requested candidate.'}
& (Join-Path $SdkRoot ('build-tools/'+$policy.build_tools+'/zipalign.exe')) -c -P 16 4 $apk
if($LASTEXITCODE -ne 0){throw 'The candidate APK is not aligned for the declared target.'}
& $Python (Join-Path $PSScriptRoot 'probe-android-closed-core.py') --apk $apk --work-dir (Join-Path $BuildRoot 'owned-package-work') --output (Join-Path $BuildRoot 'apk-owned-core-proof.json')
if($LASTEXITCODE -ne 0){throw 'The actual APK-owned Python package failed desktop reference closure; Android runtime acceptance remains separate.'}
if((& git -C $sourceRoot rev-parse HEAD).Trim() -ne $head){throw 'The source commit changed during the build.'}
$destination=Join-Path $BuildRoot "GameImmersionToolkit-android-$Variant.apk"
Copy-Item -LiteralPath $apk -Destination $destination -Force
$proof=[ordered]@{schema='toolkit-android-candidate-v1';source_commit=$head;source_dirty=$dirty;apk_sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant();frontend_build_id=$frontendManifest.build_id;python_wheels_policy_sha256=$policyHash;python_runtime_extensions_policy_sha256=$receipt.extension_policy_sha256;zstandard_receipt_sha256=$receipt.zstandard_receipt_sha256;native_decoder_manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $decoderRoot 'assets/native-decoder-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant();publisher_source_policy_sha256=(Get-FileHash -LiteralPath (Join-Path $sourceRoot 'packaging/android/publisher-sources.json') -Algorithm SHA256).Hash.ToLowerInvariant();application_id=$package.Groups[1].Value;version_code=$VersionCode;variant=$Variant;signing_certificate_sha256=$certificate;signing=if($identity){'owner-host-protected-reusable-identity'}else{'host-local-debug-candidate-only'};release_eligibility=$false;physical_device_acceptance='not-established'}
$proof.native_publisher_crypto_manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $cryptoRoot 'assets/publisher-crypto-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
$proof.publisher_crypto_authored_fixtures=$nativeAudit.native_publisher_crypto.authored_fixtures
$proof.wuwa_authored_fixture=$nativeAudit.wuwa_authored_fixture
[IO.File]::WriteAllText((Join-Path $BuildRoot 'ANDROID-PROVENANCE.json'),(ConvertTo-Json $proof -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'Built a verified Android candidate; release and physical acceptance remain separate.'
} finally {
    $env:TOOLKIT_OWNER_KEY_PASSWORD=$previousPassword
    $env:ANDROID_OWNER_KEYSTORE=$previousKeystore
    $env:ANDROID_VERSION_CODE=$previousVersion
    if($identity){$identity.password=$null;$identity.lock.Dispose()}
}

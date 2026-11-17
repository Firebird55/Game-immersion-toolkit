param(
    [Parameter(Mandatory=$true)][string]$SdkRoot,
    [Parameter(Mandatory=$true)][string]$Wheelhouse,
    [Parameter(Mandatory=$true)][string]$Frontend,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$JavaHome,
    [switch]$DownloadGradle
)
$ErrorActionPreference='Stop'
$sourceRoot=Split-Path -Parent $PSScriptRoot
$policy=Get-Content -LiteralPath (Join-Path $sourceRoot 'packaging/android/build-inputs.json') -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot 'android-build-paths.ps1')
$SdkRoot=Resolve-AndroidSupplierPath $SdkRoot 'Android SDK' @("platforms/android-$($policy.compile_sdk)/android.jar","build-tools/$($policy.build_tools)/aapt2.exe","build-tools/$($policy.build_tools)/zipalign.exe")
$Python=Resolve-AndroidSupplierPath $Python 'Build Python' @('')
$JavaHome=Resolve-AndroidSupplierPath $JavaHome 'Build Java' @('bin/java.exe','bin/keytool.exe')
foreach($item in @($SdkRoot,$Wheelhouse,$Frontend,$BuildRoot,$Python,$JavaHome)) {Assert-AndroidNoLinks $item}
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
$env:GRADLE_USER_HOME=Join-Path $BuildRoot 'gradle-user'
$env:ANDROID_PYTHON_WHEELHOUSE=$Wheelhouse
$env:ANDROID_FRONTEND_DIR=$Frontend
$env:TOOLKIT_BUILD_PYTHON=$Python
$env:ANDROID_DEBUG_KEYSTORE=Join-Path $BuildRoot 'debug.keystore'
$receipt=Get-Content -LiteralPath (Join-Path $Wheelhouse 'python-wheels-receipt.json') -Raw | ConvertFrom-Json
$policyHash=(Get-FileHash -LiteralPath (Join-Path $sourceRoot 'packaging/android/python-dependencies.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if($receipt.policy_sha256 -ne $policyHash -or $receipt.schema -ne 'toolkit-android-python-wheels-v1') {throw 'Android wheels do not match the source build policy.'}
foreach($file in $receipt.files.PSObject.Properties) {
    if([IO.Path]::GetFileName($file.Name) -ne $file.Name -or $file.Name -notlike '*.whl') {throw 'Unsafe wheel resource.'}
    $path=Join-Path $Wheelhouse $file.Name
    if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) {throw 'An Android Python wheel changed.'}
}
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
if(-not (Test-Path -LiteralPath $env:ANDROID_DEBUG_KEYSTORE)) {
    & (Join-Path $JavaHome 'bin/keytool.exe') -genkeypair -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=Android Debug,O=Android,C=US' -storepass android -keypass android -keystore $env:ANDROID_DEBUG_KEYSTORE
    if($LASTEXITCODE -ne 0){throw 'Could not create the local authored-test signing identity.'}
}
$head=(& git -C $sourceRoot rev-parse HEAD).Trim()
$dirty=!!(& git -C $sourceRoot status --porcelain)
& (Join-Path $gradleRoot 'bin/gradle.bat') -p (Join-Path $sourceRoot 'packaging/android') :app:assembleDebug --console=plain
if($LASTEXITCODE -ne 0){throw 'Android candidate compilation failed.'}
$apk=Join-Path $sourceRoot 'packaging/android/app/build/outputs/apk/debug/app-debug.apk'
$audit=Join-Path $BuildRoot 'apk-audit.json'
& $Python (Join-Path $PSScriptRoot 'verify-android-apk.py') $apk --output $audit
if($LASTEXITCODE -ne 0){throw 'The Android APK failed its closed native/shared-core audit.'}
$nativeAudit=Get-Content -LiteralPath $audit -Raw | ConvertFrom-Json
foreach($abi in $policy.abis) {
    $nativeReceipt=$receipt.native.PSObject.Properties[$abi].Value
    $cores=@($nativeAudit.native_files.PSObject.Properties | Where-Object { $_.Name.StartsWith('assets/chaquopy/requirements-'+$abi+'.imy/pydantic_core/_pydantic_core') })
    if($cores.Count -ne 1 -or $cores[0].Value.sha256 -ne $nativeReceipt.native_sha256) {throw 'The packaged native core differs from its verified wheel.'}
    $rapid=$receipt.rapidfuzz_native.PSObject.Properties[$abi].Value
    if(-not $rapid -or -not $rapid.modules) {throw 'The native RapidFuzz build receipt is missing.'}
    foreach($module in $rapid.modules.PSObject.Properties) {
        $name='assets/chaquopy/requirements-'+$abi+'.imy/'+$module.Name
        if($nativeAudit.native_files.PSObject.Properties[$name].Value.sha256 -ne $module.Value.sha256) {throw 'Packaged RapidFuzz differs from its verified source-built wheel.'}
    }
}
& (Join-Path $SdkRoot ('build-tools/'+$policy.build_tools+'/apksigner.bat')) verify --verbose --print-certs $apk > (Join-Path $BuildRoot 'apk-signature.txt')
if($LASTEXITCODE -ne 0){throw 'The APK signature is invalid.'}
& (Join-Path $SdkRoot ('build-tools/'+$policy.build_tools+'/zipalign.exe')) -c -P 16 4 $apk
if($LASTEXITCODE -ne 0){throw 'The candidate APK is not aligned for the declared target.'}
& $Python (Join-Path $PSScriptRoot 'probe-android-closed-core.py') --apk $apk --work-dir (Join-Path $BuildRoot 'owned-package-work') --output (Join-Path $BuildRoot 'apk-owned-core-proof.json')
if($LASTEXITCODE -ne 0){throw 'The actual APK-owned Python package failed desktop reference closure; Android runtime acceptance remains separate.'}
if((& git -C $sourceRoot rev-parse HEAD).Trim() -ne $head){throw 'The source commit changed during the build.'}
$destination=Join-Path $BuildRoot 'GameImmersionToolkit-android-debug.apk'
Copy-Item -LiteralPath $apk -Destination $destination -Force
$proof=[ordered]@{schema='toolkit-android-candidate-v1';source_commit=$head;source_dirty=$dirty;apk_sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant();frontend_build_id=$frontendManifest.build_id;python_wheels_policy_sha256=$policyHash;signing='host-local-debug-candidate-only';release_eligibility=$false;physical_device_acceptance='not-established'}
[IO.File]::WriteAllText((Join-Path $BuildRoot 'ANDROID-PROVENANCE.json'),(ConvertTo-Json $proof -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'Built a verified Android debug candidate; release and physical acceptance remain separate.'

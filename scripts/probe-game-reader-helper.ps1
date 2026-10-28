param([Parameter(Mandatory = $true)][string]$HelperRoot)
$ErrorActionPreference = 'Stop'
$output = Join-Path $env:GITHUB_WORKSPACE 'output/checks/r19-managed-helper.json'
if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output }
# Authored helper only: no installed game, account, recording or user profile.
$originalPath = $env:PATH
$originalDotnetRoot = $env:DOTNET_ROOT
$originalLookup = $env:DOTNET_MULTILEVEL_LOOKUP
$temporary = Join-Path $env:RUNNER_TEMP ('r19-managed-probe-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporary | Out-Null
$candidate = Join-Path $temporary 'Application space 漢字'
$process = $null
function Snapshot([string]$Root) {
  return @(Get-ChildItem -LiteralPath $Root -Recurse | Sort-Object FullName | ForEach-Object {
    $_.FullName.Substring($Root.Length) + ':' + $(if ($_.PSIsContainer) { 'directory' } else { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash })
  }) -join ','
}
function Invoke-OwnedProbe([string]$Root, [string]$Request) {
  $info = [Diagnostics.ProcessStartInfo]::new()
  $info.FileName = Join-Path $Root 'ToolkitReaderProbe.exe'
  $info.ArgumentList.Add('--probe')
  $info.WorkingDirectory = $temporary
  $info.UseShellExecute = $false
  $info.RedirectStandardInput = $true
  $info.RedirectStandardOutput = $true
  $info.RedirectStandardError = $true
  $info.Environment.Clear()
  foreach ($name in @('SystemRoot','WINDIR','TEMP','TMP')) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) { $info.Environment[$name] = $value }
  }
  # No startup hooks, profiler/COMPlus flags or additional dependency stores
  # may run before Main and invalidate the app-local runtime observation.
  $info.Environment['PATH'] = "$env:WINDIR/System32;$env:WINDIR"
  $info.Environment['DOTNET_ROOT'] = Join-Path $temporary 'absent-system-dotnet'
  $info.Environment['DOTNET_MULTILEVEL_LOOKUP'] = '0'
  $script:process = [Diagnostics.Process]::Start($info)
  $stdout = $script:process.StandardOutput.ReadToEndAsync()
  $stderr = $script:process.StandardError.ReadToEndAsync()
  $script:process.StandardInput.WriteLine($Request)
  $script:process.StandardInput.Close()
  if (-not $script:process.WaitForExit(10000)) {
    $script:process.Kill($true)
    $script:process.WaitForExit(10000) | Out-Null
    throw 'Authored helper exceeded its owned process deadline.'
  }
  return @{code=$script:process.ExitCode; stdout=$stdout.GetAwaiter().GetResult(); stderr=$stderr.GetAwaiter().GetResult()}
}
try {
  $HelperRoot = [IO.Path]::GetFullPath($HelperRoot)
  $ancestor = $HelperRoot
  while ($ancestor) {
    if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Authored helper input cannot follow a reparse point.' }
    $ancestor = [IO.Path]::GetDirectoryName($ancestor)
  }
  if (@(Get-ChildItem -LiteralPath $HelperRoot -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Authored helper tree contains a reparse point.' }
  Copy-Item -LiteralPath $HelperRoot -Destination $candidate -Recurse
  $manifestPath = Join-Path $candidate 'helper-manifest.json'
  $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
  if ($manifest.schema -ne 'proxy-prebuilt-dotnet-reader-v1' -or $manifest.kind -ne 'probe' -or $manifest.entry -ne 'ToolkitReaderProbe.exe' -or $manifest.source_commit -ne $env:GITHUB_SHA -or $manifest.sdk_version -ne '10.0.403' -or $manifest.runtime_version -ne '10.0.14' -or $manifest.platform -ne 'win-x64') { throw 'Only the matching fixed authored helper can enter this probe.' }
  if ($manifest.source_dirty -isnot [bool] -or $manifest.source_dirty) { throw 'Hosted source evidence requires a clean exact-commit helper build.' }
  $listed = @($manifest.files.PSObject.Properties)
  if ($listed.Count -lt 8 -or @(Get-ChildItem -LiteralPath $candidate -File -Recurse).Count -ne $listed.Count + 1) { throw 'The authored helper inventory is incomplete.' }
  foreach ($item in $listed) {
    $name = $item.Name
    if ($name.StartsWith('/') -or $name.Contains('\') -or $name.Contains(':') -or @($name.Split('/') | Where-Object { -not $_ -or $_ -in @('.','..') }).Count) { throw 'The helper manifest contains an unsafe path.' }
    $file = Get-Item -LiteralPath (Join-Path $candidate $name)
    if ($file.PSIsContainer -or $file.Length -ne $item.Value.bytes -or (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.Value.sha256) { throw 'The authored helper bytes differ from its manifest.' }
  }
  $before = Snapshot $candidate
  Get-ChildItem -LiteralPath $candidate -File -Recurse | ForEach-Object { $_.IsReadOnly = $true }
  $env:PATH = "$env:WINDIR/System32;$env:WINDIR"
  $env:DOTNET_ROOT = Join-Path $temporary 'absent-system-dotnet'
  $env:DOTNET_MULTILEVEL_LOOKUP = '0'
  if (Get-Command dotnet, csc, msbuild, npm, node -ErrorAction SilentlyContinue) { throw 'Developer tools remain discoverable.' }
  $request = @{schema='proxy-reader-probe-request-v1';nonce='authored-r19-probe-1'} | ConvertTo-Json -Compress
  $result = Invoke-OwnedProbe $candidate $request
  if ($result.code -ne 0) { throw 'Self-contained authored helper did not execute.' }
  $identity = $result.stdout | ConvertFrom-Json
  $expectedResource = (Get-FileHash -LiteralPath (Join-Path $candidate 'probe-resource.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($identity.schema -ne 'proxy-reader-probe-result-v1' -or $identity.nonce -ne 'authored-r19-probe-1' -or $identity.runtime_version -ne '10.0.14' -or $identity.runtime_origin -ne 'app-local' -or $identity.resource_sha256 -ne $expectedResource) { throw 'Authored helper output/runtime identity differs.' }
  $invalid = Invoke-OwnedProbe $candidate '{}'
  if ($invalid.code -ne 2) { throw 'Invalid authored input did not fail closed.' }
  if ((Snapshot $candidate) -ne $before) { throw 'Helper wrote to its immutable application files.' }
  $broken = Join-Path $temporary 'Broken resource 漢字'
  Copy-Item -LiteralPath $candidate -Destination $broken -Recurse
  $resource = Get-Item -LiteralPath (Join-Path $broken 'probe-resource.txt')
  $resource.IsReadOnly = $false
  Remove-Item -LiteralPath $resource.FullName
  $missing = Invoke-OwnedProbe $broken $request
  if ($missing.code -ne 3) { throw 'Missing authored resource did not fail closed.' }
  $receipt = @{schema='proxy-r19-managed-helper-probe-v1'; source_commit=$env:GITHUB_SHA; source_dirty=$false; status='passed'; helper_kind='authored-probe'; sdk_version='10.0.403'; runtime_version=$identity.runtime_version; runtime_origin=$identity.runtime_origin; developer_path='removed'; system_dotnet_root='absent'; readonly_files=$true; application_writes_observed=$false; malformed_input='rejected'; missing_resource='rejected'; real_games_accessed=$false; real_accounts_accessed=$false; helper_manifest_sha256=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant(); native_windows_11_acceptance='unavailable'; exact_output_redistribution='pending'; game_helpers='not-authorized-by-probe'; installer='not-built'; r19_complete=$false}
} finally {
  if ($process -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit(10000) | Out-Null }
  if ($process -and -not $process.HasExited) { throw 'Owned managed helper cleanup is unconfirmed.' }
  $env:PATH = $originalPath
  $env:DOTNET_ROOT = $originalDotnetRoot
  $env:DOTNET_MULTILEVEL_LOOKUP = $originalLookup
  Get-ChildItem -LiteralPath $temporary -File -Recurse | ForEach-Object { $_.IsReadOnly = $false }
  Remove-Item -LiteralPath $temporary -Recurse -Force
}
New-Item -ItemType Directory -Path (Split-Path $output) -Force | Out-Null
$receipt.owned_cleanup = 'passed'
$receipt | ConvertTo-Json | Set-Content -LiteralPath $output -Encoding utf8

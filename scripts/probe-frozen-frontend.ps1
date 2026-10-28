param([Parameter(Mandatory = $true)][string]$RuntimeRoot)
$ErrorActionPreference = 'Stop'
# Run only with the caller's developer PATH removed and synthetic root selection.
# No browser profile, game files, credential store or desktop capture is opened.
if (Get-Command node, npm, python, dotnet -ErrorAction SilentlyContinue) { throw 'Developer tools are still discoverable.' }
$client = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 3000)
try { $client.Start() } finally { $client.Stop() }
$exe = Join-Path $RuntimeRoot 'ProxyTranscriptRuntime.exe'
$manifest = Get-Content -LiteralPath (Join-Path $RuntimeRoot '_internal/desktop/desktop-manifest.json') -Raw | ConvertFrom-Json
$temporary = Join-Path $env:RUNNER_TEMP ('r19-frontend-probe-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporary | Out-Null
$process = $null
try {
  $process = Start-Process -FilePath $exe -ArgumentList @('--runtime-child', 'frontend', '--', '--port', '3000') -WorkingDirectory $temporary -RedirectStandardOutput (Join-Path $temporary 'stdout') -RedirectStandardError (Join-Path $temporary 'stderr') -PassThru
  $deadline = [DateTime]::UtcNow.AddSeconds(30)
  $ready = $false
  do {
    if ($process.HasExited) { throw 'Frozen frontend exited before readiness.' }
    try {
      $identity = Get-Content -LiteralPath (Join-Path $temporary 'stdout') -TotalCount 1 -ErrorAction Stop | ConvertFrom-Json
      $ready = $identity.ready -eq $true -and $identity.port -eq 3000 -and $identity.build_id -eq $manifest.build_id
    } catch { $ready = $false }
    if (-not $ready) { Start-Sleep -Milliseconds 200 }
  } until ($ready -or [DateTime]::UtcNow -ge $deadline)
  if (-not $ready) { throw 'Frozen frontend startup deadline expired.' }
  if ($process.HasExited) { throw 'Owned frontend exited after readiness.' }
  $paths = @('index.html', 'mobile-capture/ocr/core/tesseract-core.wasm', 'mobile-capture/library-worker.mjs')
  $paths += @($manifest.files.PSObject.Properties.Name | Where-Object { $_ -match '^assets/.+\.(js|css|ttf)$' })
  foreach ($name in $paths) {
    $destination = Join-Path $temporary 'response'
    $response = Invoke-WebRequest -Uri ('http://127.0.0.1:3000/' + $name) -OutFile $destination -PassThru -TimeoutSec 5
    $expected = $manifest.files.$name
    if ($response.StatusCode -ne 200 -or (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.sha256 -or [string]$response.Headers['Content-Type'] -ne $expected.mime) { throw 'Frozen served bytes or MIME differ from the candidate manifest.' }
  }
  $mobile = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/mobile-capture/?pc=1&game=zzz' -TimeoutSec 5
  if ($mobile.StatusCode -ne 200) { throw 'Mobile capture link is unavailable.' }
  $blocked = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/' -Headers @{Origin='https://example.test'} -SkipHttpErrorCheck -TimeoutSec 5
  if ($blocked.StatusCode -ne 403) { throw 'Foreign origin was accepted.' }
  $missing = Invoke-WebRequest -Uri 'http://127.0.0.1:3000/api/snapshot' -SkipHttpErrorCheck -TimeoutSec 5
  if ($missing.StatusCode -ne 404) { throw 'Static host unexpectedly exposes an API route.' }
  if ($process.HasExited) { throw 'Owned frontend exited during HTTP verification.' }
} finally {
  if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force; $process.WaitForExit(10000) | Out-Null }
  if ($process -and -not $process.HasExited) { throw 'Owned frontend process did not stop.' }
  Remove-Item -LiteralPath $temporary -Recurse -Force
}
# A passing receipt is possible only after all owned cleanup above succeeded.
$output = Join-Path $env:GITHUB_WORKSPACE 'output/checks/r19-frozen-frontend.json'
New-Item -ItemType Directory -Path (Split-Path $output) -Force | Out-Null
@{schema='proxy-r19-frozen-frontend-v1'; source_commit=$env:GITHUB_SHA; build_id=$manifest.build_id; status='passed'; owned_cleanup='passed'; developer_path='removed'; served_manifest_hashes='passed'; canonical_origin='http://127.0.0.1:3000'; frontend_only=$true; real_accounts_accessed=$false; native_windows_11_acceptance='unavailable'; redistribution_review='pending'; r19_complete=$false; installer='not-built'} | ConvertTo-Json | Set-Content -LiteralPath $output -Encoding utf8

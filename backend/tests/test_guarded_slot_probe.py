"""Source guardian contracts; real two-slot frozen execution remains separate."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def contract(tmp_path, body):
    if os.name != 'nt':
        pytest.skip('Windows guardian PowerShell/native lease contract')
    shell = shutil.which('pwsh')
    assert shell, 'Hosted guardian contracts require PowerShell 7'
    source = Path(__file__).resolve().parents[2]/'scripts/probe-frozen-slots.ps1'
    inventory = source.with_name('r19-runtime-inventory.ps1')
    script = tmp_path/'guardian-contract.ps1'
    script.write_text(r'''param([string]$Probe, [string]$Inventory, [string]$Fixture)
$ErrorActionPreference='Stop'
$slotSourceOperation=Join-Path (Split-Path $Probe) 'companion-runtime.ps1'
function Load-Definition([string]$Path,[string]$Name) {
    $tokens=$null; $parseErrors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors) { throw 'Guardian contract source parsing failed.' }
    $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $Name},$true)
    if (-not $definition) { throw 'Missing fixed guardian operation.' }
    return [scriptblock]::Create($definition.Extent.Text)
}
$script:phase='load-definitions'
try {
. (Load-Definition $Inventory 'Get-R19RuntimeInventory')
foreach ($name in @('Assert-SlotEntryName','Assert-SlotInventory','Invoke-SlotLeaseObservation','Stop-GuardedSlot')) {
    . (Load-Definition $Probe $name)
}
function Require([bool]$Condition) { if (-not $Condition) { throw 'Guardian authored contract failed.' } }
''' + body + r'''
Write-Output 'guarded-slot-contract-passed'
} catch {
    $allowed=@('load-definitions','lease-baseline','lease-blocked','lease-released','lease-refusal','inventory-match',
        'inventory-alias','unsafe-name','hidden-extra','modified-byte','cleanup-incomplete','cleanup-retry')
    $safe=if ($script:phase -in $allowed) {$script:phase} else {'unknown-phase'}
    [Console]::Out.WriteLine('guardian-contract-failure phase='+$safe)
    [Console]::Out.Flush()
    exit 1
}
''', encoding='utf-8')
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-File', str(script),
        '-Probe', str(source), '-Inventory', str(inventory), '-Fixture', str(tmp_path)],
        capture_output=True, text=True, timeout=45)
    if result.returncode != 0:
        allowed = {'load-definitions', 'lease-baseline', 'lease-blocked', 'lease-released', 'lease-refusal',
            'inventory-match', 'inventory-alias', 'unsafe-name', 'hidden-extra', 'modified-byte',
            'cleanup-incomplete', 'cleanup-retry', 'unknown-phase'}
        safe = 'no-safe-phase'
        for line in result.stdout.splitlines():
            if line.startswith('guardian-contract-failure phase=') and line[32:] in allowed:
                safe = line[32:]
        pytest.fail('Fixed authored guardian contract failed: ' + safe, pytrace=False)
    if result.stdout.strip() != 'guarded-slot-contract-passed':
        pytest.fail('Guardian contract returned unexpected output', pytrace=False)


def test_independent_exact_legacy_lease_is_held_until_explicit_release(tmp_path):
    contract(tmp_path, r'''
$script:phase='lease-baseline'
$sourceRoot=Join-Path $Fixture 'legacy space 漢字'
New-Item -ItemType Directory -Path (Join-Path $sourceRoot 'data') | Out-Null
$path=Join-Path $sourceRoot 'data/companion-operation.lock'
Require ((Invoke-SlotLeaseObservation $path) -eq 'open')
Require ((Invoke-SlotLeaseObservation $sourceRoot 'legacy-source') -eq 'open')
$lease=[IO.File]::Open($path,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
    $script:phase='lease-blocked'
    Require ((Invoke-SlotLeaseObservation $path) -eq 'blocked')
    Require ((Invoke-SlotLeaseObservation $sourceRoot 'legacy-source') -eq 'blocked')
    Require (-not $lease.SafeFileHandle.IsClosed)
} finally { $lease.Dispose() }
$script:phase='lease-released'
Require ((Invoke-SlotLeaseObservation $path) -eq 'open')
Require ((Invoke-SlotLeaseObservation $sourceRoot 'legacy-source') -eq 'open')
$script:phase='lease-refusal'
$unavailable=$false
try { $null=Invoke-SlotLeaseObservation $sourceRoot } catch { $unavailable=$true }
Require $unavailable
''')


def test_complete_candidate_inventory_refuses_tampering_aliases_and_hidden_extras(tmp_path):
    contract(tmp_path, r'''
$root=Join-Path $Fixture 'application'
New-Item -ItemType Directory -Path (Join-Path $root '_internal') | Out-Null
$identity=@{profile='runtime-experiment'; build_id='authored'; source_commit=('a'*40)}
$identity | ConvertTo-Json | Set-Content (Join-Path $root '_internal/runtime-manifest.json') -Encoding utf8NoBOM
[IO.File]::WriteAllText((Join-Path $root 'ProxyTranscriptRuntime.exe'),'authored bytes; never executed')
$files=@(Get-ChildItem -LiteralPath $root -File -Recurse -Force | ForEach-Object {
    @{path=[IO.Path]::GetRelativePath($root,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$proof=@{files=$files;directories=@('_internal');profile=$identity.profile;build_id=$identity.build_id;source_commit=$identity.source_commit}
$script:phase='inventory-match'
Assert-SlotInventory $root $proof
$script:phase='inventory-alias'
$proof.files += @{path='proxytranscriptruntime.exe'; bytes=$files[0].bytes; sha256=$files[0].sha256}
$refused=$false
try { Assert-SlotInventory $root $proof } catch { $refused=$true }
Require $refused
$proof.files=$files
$script:phase='unsafe-name'
foreach ($name in @('../escape','C:\escape','file:stream','CON.txt','trailing.','double//name')) {
    $refused=$false
    try { Assert-SlotEntryName $name } catch { $refused=$true }
    Require $refused
}
$script:phase='hidden-extra'
$extra=Join-Path $root 'hidden-extra'
[IO.File]::WriteAllText($extra,'unlisted authored fixture')
[IO.File]::SetAttributes($extra,[IO.FileAttributes]::Hidden -bor [IO.FileAttributes]::System)
$refused=$false
try { Assert-SlotInventory $root $proof } catch { $refused=$true }
Require $refused
Remove-Item -LiteralPath $extra -Force
$script:phase='modified-byte'
[IO.File]::WriteAllText((Join-Path $root 'ProxyTranscriptRuntime.exe'),'Authored bytes; never executed')
$refused=$false
try { Assert-SlotInventory $root $proof } catch { $refused=$true }
Require $refused
''')


def test_unconfirmed_child_exit_preserves_observer_context_and_does_not_free_ports(tmp_path):
    contract(tmp_path, r'''
$script:events=[Collections.Generic.List[string]]::new()
function Assert-SlotLeasesBlocked { $script:events.Add('leases-held') }
function Assert-SlotPortsFree { $script:events.Add('ports-checked') }
$process=[pscustomobject]@{Id=7;HasExited=$false}
$process | Add-Member -MemberType ScriptMethod -Name Kill -Value {$script:events.Add('host-killed'); $this.HasExited=$true}
$process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {param($timeout) $script:events.Add('host-signaled'); return $true}
$observer=[pscustomobject]@{ready=$false}
$observer | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {param($timeout) $script:events.Add('child-observed'); return $this.ready}
$tasks=@{7=@($null,[Threading.Tasks.Task]::CompletedTask)}
$context=[pscustomobject]@{process=$process;held=@($observer);closed=$false}
$script:phase='cleanup-incomplete'
$refused=$false
try { Stop-GuardedSlot $context 'crash' } catch { $refused=$true }
Require $refused
Require (-not $context.closed)
Require ($context.held[0] -eq $observer)
Require (-not $script:events.Contains('ports-checked'))
$script:phase='cleanup-retry'
$observer.ready=$true
Stop-GuardedSlot $context 'crash'
Require $context.closed
Require ($script:events[$script:events.Count-1] -eq 'ports-checked')
Require ($script:events.Contains('leases-held'))
''')

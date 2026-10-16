import {test} from 'node:test';import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';import {readFileSync} from 'node:fs';
test('installer contains contribution instructions and separate per-PC game picker',()=>{
 for(const file of ['INSTALL.md','INSTALL.html','CONTRIBUTING.md','scripts/install.ps1'])assert(readFileSync(file,'utf8').includes('AGENTS.md'));
 assert(readFileSync('Choose Game Folders.cmd','utf8').includes('select-game-folders.ps1'));
});
test('Windows installer scripts parse and instructions-only mode does not open dialogs',{skip:process.platform!=='win32'},()=>{
 const command="$ErrorActionPreference='Stop'; foreach ($file in @('scripts/install.ps1','scripts/select-game-folders.ps1','scripts/setup.ps1','scripts/companion-runtime.ps1','scripts/update-companion.ps1','scripts/retire-companion.ps1','scripts/start-companion.ps1')) { $tokens=$null; $errors=$null; [System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Get-Location) $file),[ref]$tokens,[ref]$errors) | Out-Null; if ($errors) { throw ($errors -join '; ') } }; & scripts/install.ps1 -InstructionsOnly; & scripts/select-game-folders.ps1 -InstructionsOnly";
 const output=execFileSync('powershell.exe',['-NoProfile','-Command',command],{encoding:'utf8'});assert(output.includes('CONTRIBUTING.md'));assert(output.includes('Cancel keeps existing settings'));
});

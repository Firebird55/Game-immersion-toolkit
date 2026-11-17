import assert from 'node:assert/strict';
import test from 'node:test';
import {authoredCredentialPath} from '../scripts/android-authored-account-ui.mjs';

const isolated = {platform: 'android', authored_account_fixture: true, protected_accounts: true, account_protocol: 'scoped-accounts-v1'};

test('credential corruption is bounded to the explicit isolated DEBUG root', () => {
  assert.equal(authoredCredentialPath('io.github.firebird55.gameimmersiontoolkit.debug', isolated), 'files/authored-account-ui/credentials/accounts.gcm');
  for (const packageName of ['io.github.firebird55.gameimmersiontoolkit', 'another.debug', undefined])
    assert.throws(() => authoredCredentialPath(packageName, isolated));
  for (const platform of [null, {...isolated, authored_account_fixture: false}, {...isolated, protected_accounts: false},
    {...isolated, platform: 'desktop'}, {...isolated, account_protocol: undefined}])
    assert.throws(() => authoredCredentialPath('io.github.firebird55.gameimmersiontoolkit.debug', platform));
});

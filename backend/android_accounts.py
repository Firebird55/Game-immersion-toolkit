"""Maintained account profiles with independent prepared capture ownership.

This is the platform/session boundary. Credential verification and storage remain
in AccountStore; matching, confirmation and history remain PreparedCaptureSession.
HTTP/UI capability is enabled separately after its complete request contract.
"""
from pathlib import Path
from dataclasses import dataclass
import re
import threading
import time

from .accounts import AccountStore
from .prepared_session import PreparedCaptureSession
from .lexirise import LexiriseService, LexiriseError
from .lexirise_settings import account_settings
from .languages import translation_language, study_language
from .runtime_readers import RuntimeReadingRegistry
from .line_presentation import translation_fields

ACCOUNT = re.compile(r'[0-9a-f]{24}')
MAX_LOCAL_LINE = 2**32
MAX_ACTIVATIONS = 2**20


class AndroidAccountConflict(ValueError):
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


@dataclass(frozen=True, repr=False)
class AndroidAccountRequest:
    owner: object
    session: object
    generation: int
    epoch: int
    identity: str
    service: object = None
    line: object = None

    def check(self):
        with self.owner.lock:
            if (self.owner.transitioning or self.owner.session is not self.session
                    or self.owner.accounts.generation != self.generation or self.owner.activation_epoch != self.epoch):
                raise AndroidAccountConflict('account_request_scope_changed', 'The account changed before this operation completed.')

    def reader(self):
        self.check()
        if self.line is None or self.service is None:
            raise ValueError('An account and original transcript line are required.')
        if not hasattr(self.service, '_settings_payload'):
            account_settings(self.service)
        self.check()
        target = translation_language(self.service._settings_payload, self.line.source_language)
        with self.owner.lock:
            registry = self.owner._readers[self.identity]
        with registry.lookup() as lookup:
            key = (self.service._scope(), self.line.source_language, target, self.service._settings_scope)
            return registry.get_or_create(lookup, key, self.service,
                source_language=self.line.source_language, translation_language=target)

    def presented_line(self):
        if self.line is None or self.service is None:
            raise ValueError('A pinned account transcript line is required.')
        if not hasattr(self.service, '_settings_payload'):
            account_settings(self.service)
        self.check()
        settings = self.service._settings_payload
        target = (translation_language(settings, self.line.source_language)
            if self.line.source_language in settings['languages'] else self.line.translation_locale)
        return self.line.model_copy(update=translation_fields(self.line.texts, self.line.english, self.line.chinese, target))


class AndroidAccountSessions:
    def __init__(self, root, *, protect, on_invalidate=lambda: None, transport=None,
            session_factory=PreparedCaptureSession):
        self.root = Path(root).absolute()
        self.lock = threading.RLock()
        self.accounts = AccountStore(self.root / 'credentials/accounts.gcm', protect=protect, transport=transport, trust_env=False)
        self.session_factory, self.on_invalidate = session_factory, on_invalidate
        self.activation_epoch = self.transition_revision = 0
        self.transitioning = False
        self._services, self._readers = {}, {}
        active = self.accounts.status()['active']
        self.session = self._prepare(active)
        self.runtime_id = self.session.runtime_id

    def _root_for(self, identity):
        if identity == 'legacy':
            return self.root
        if not isinstance(identity, str) or not ACCOUNT.fullmatch(identity):
            raise ValueError('Invalid protected account identity')
        return self.root / 'profiles' / identity

    def _prepare(self, identity):
        session = self.session_factory(self._root_for(identity), on_invalidate=self.on_invalidate)
        session.lock = self.lock
        return session

    def status(self):
        with self.lock:
            return self.accounts.status()

    def _expect(self, generation):
        if type(generation) is not int or generation != self.accounts.generation:
            raise AndroidAccountConflict('account_generation_changed', 'The account changed. Refresh before retrying this operation.')

    def pin(self, generation, *, line_id=None, language=None, remote=False):
        with self.lock:
            self._expect(generation)
            if self.transitioning:
                raise AndroidAccountConflict('account_selection_pending', 'Wait for the selected account to load.')
            identity = self.accounts.status()['active']
            line = None
            if line_id is not None:
                line = self.session.history.get(self.local_line(line_id))
                if line is None:
                    raise LookupError('Transcript line not found')
            service = None
            if remote:
                if identity == 'legacy' or not self.accounts.active_key():
                    raise LexiriseError('Choose a protected account saved on this device.')
                if identity not in self._services:
                    directory = self._root_for(identity) / 'lexirise'
                    self._services[identity] = LexiriseService(directory, accounts=self.accounts,
                        transport=self.accounts.transport, legacy_credentials=False, trust_env=False)
                    self._readers[identity] = RuntimeReadingRegistry(directory)
                service = self._services[identity].pin(language or (line.source_language if line else 'zh'))
            return AndroidAccountRequest(self, self.session, generation, self.activation_epoch, identity, service, line)

    def lexirise_status(self):
        with self.lock:
            identity = self.accounts.status()['active']
            if identity == 'legacy' or self.transitioning:
                return {'configured': False, 'sent': {}, 'account': identity}
            language = study_language(self.session.index.source_locale) if self.session.index else 'zh'
            pinned = self.pin(self.accounts.generation, remote=True, language=language)
            result = pinned.service.status()
            result['account'] = identity
            result['sent'] = {f'line:{self.activation_epoch * MAX_LOCAL_LINE + int(ref[5:])}': deck
                for ref, deck in result.get('sent', {}).items() if re.fullmatch(r'line:[1-9][0-9]*', ref)
                and int(ref[5:]) < MAX_LOCAL_LINE}
            return result

    def cached_preferences(self):
        with self.lock:
            if self.transitioning or self.accounts.status()['active'] == 'legacy':
                return None
            service = self.pin(self.accounts.generation, remote=True).service
            return getattr(service, '_settings_payload', None)

    def present_dto(self, value, settings):
        if settings is None:
            return value
        target = (translation_language(settings, value['source_language'])
            if value['source_language'] in settings['languages'] else value.get('translation_locale', ''))
        return {**value, **translation_fields(value.get('texts'), value.get('english', ''), value.get('chinese', ''), target)}

    def close(self):
        with self.lock:
            self.session.stop('The account runtime closed')
            readers = tuple(self._readers.values())
        deadline = time.monotonic() + 5
        for registry in readers:
            registry.shutdown(deadline)

    def select(self, identity, expected_generation):
        with self.lock:
            self._expect(expected_generation)
            status = self.accounts.status()
            if identity != 'legacy' and identity not in {item['id'] for item in status['profiles']}:
                raise ValueError('Choose an account saved on this device.')
            if self.activation_epoch >= MAX_ACTIVATIONS - 1:
                raise ValueError('Reopen the app before switching accounts again.')
            self._root_for(identity)
            self.transition_revision += 1
            ticket = self.transition_revision
            self.transitioning = True
            self.session.stop('Account selection changed; reconnect after it loads')
        try:
            # Index validation can take time. A later explicit selection must
            # remain able to win while this candidate is being prepared.
            staged = self._prepare(identity)
            with self.lock:
                if ticket != self.transition_revision:
                    raise AndroidAccountConflict('account_selection_superseded', 'A newer account selection already won.')
                self._expect(expected_generation)
                self.accounts.select(identity)
                staged.generation = self.session.generation + 1
                staged.state_version = self.session.state_version + 1
                staged.runtime_id = self.runtime_id
                self.activation_epoch += 1
                self.session = staged
                self.transitioning = False
                self.on_invalidate()
                return self.accounts.status()
        except Exception:
            with self.lock:
                if ticket == self.transition_revision:
                    self.transitioning = False
            raise

    def register(self, key, name, expected_generation):
        with self.lock:
            self._expect(expected_generation)
            self.transition_revision += 1
            ticket, active = self.transition_revision, self.accounts.status()['active']
            # A newer registration intent supersedes an in-flight selector too.
            # It does not expose a different account while verification runs.
            self.transitioning = False
        # Only GET /v1/me verifies credentials. Persist the verified profile
        # without allowing a delayed network response to steal selection.
        profile = self.accounts.add(key, name, select=False)
        with self.lock:
            self.session.stop('Saved account profiles changed; reconnect the screen source')
            if self.transition_revision != ticket or self.accounts.status()['active'] != active:
                raise AndroidAccountConflict('account_registration_not_selected',
                    'The verified account was saved. A newer selection was kept; reload saved accounts.')
            generation = self.accounts.generation
        return self.select(profile['id'], generation)

    def qualify_line(self, value):
        with self.lock:
            if type(value.get('id')) is not int or not 0 < value['id'] < MAX_LOCAL_LINE:
                raise ValueError('The stored line ID exceeds the native transport bound.')
            return {**value, 'id': self.activation_epoch * MAX_LOCAL_LINE + value['id']}

    def local_line(self, identity):
        with self.lock:
            if (type(identity) is not int or identity <= 0 or identity >= 2**53
                    or identity // MAX_LOCAL_LINE != self.activation_epoch or not identity % MAX_LOCAL_LINE):
                raise AndroidAccountConflict('account_line_scope_changed', 'This line belongs to an earlier account selection.')
            return identity % MAX_LOCAL_LINE

    def guard_import(self, session, generation):
        # Invoke inside the same session/publication lock at final pointer
        # replacement. A→B→A is fenced even when the old session's path matches.
        if self.transitioning or self.session is not session or generation != self.accounts.generation:
            raise AndroidAccountConflict('account_import_scope_changed', 'The account changed before the library could be activated.')

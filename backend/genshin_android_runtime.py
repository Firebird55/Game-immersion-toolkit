"""Explicit primary-source profile reading from the installed Android data decoder."""
import hashlib
import json
import re

from .genshin_reader_identity import PROFILE_IMPLEMENTATION, SEED_IMPLEMENTATION, implementation_identity


_ANDROID_IMPLEMENTATION = tuple(dict.fromkeys((
    'genshin_android_runtime', 'genshin_reader_identity', 'android_x64_decoder', 'android_x64_fixtures',
    *SEED_IMPLEMENTATION, *PROFILE_IMPLEMENTATION,
)))
_ANDROID_DIGESTS = ('source_sha256', 'library_sha256', 'manifest_sha256', 'authored_contract_sha256')
_ANDROID_PROOF_FIELDS = (
    'schema', 'version', 'abi', 'pointer_bits', 'api_major', 'api_minor', *_ANDROID_DIGESTS,
    'apk_entry_verified', 'licenses_verified', 'system_fallback', 'original_client_execution',
    'authored_contract_cases', 'large_integer_exact', 'register_contract_exact', 'groups_access_exact',
)


class AndroidGenshinRuntime:
    """Explicit original-data profile runtime using the Android host's installed decoder."""

    def __init__(self, installed_decoder):
        from .genshin_blb_portable import PortableHelper
        self._decoder = installed_decoder
        self._portable = PortableHelper()
        self._identity = self._digest(self._provenance())

    @staticmethod
    def _digest(provenance):
        canonical = json.dumps(provenance, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        return hashlib.sha256(canonical).hexdigest()

    def _provenance(self):
        from .genshin_native_x64 import require_android_decoder
        require_android_decoder(self._decoder)
        proof = self._decoder.proof()
        if (any(key not in proof for key in _ANDROID_PROOF_FIELDS)
                or type(proof.get('authored_contract_cases')) is not int or proof['authored_contract_cases'] != 15
                or any(not isinstance(proof.get(key), str) or not re.fullmatch('[a-f0-9]{64}', proof[key])
                       for key in _ANDROID_DIGESTS)
                or any(proof.get(key) is not True for key in ('apk_entry_verified', 'licenses_verified',
                    'large_integer_exact', 'register_contract_exact', 'groups_access_exact'))
                or proof['system_fallback'] is not False
                or proof['original_client_execution'] is not False):
            raise ValueError('The installed Android decoder lacks its verified data contract.')
        return {'schema': 'genshin-android-channel-profile-runtime-v1',
                'decoder': {key: proof[key] for key in _ANDROID_PROOF_FIELDS},
                'portable_blb_sha256': self._portable.identity,
                'implementation_sha256': implementation_identity(_ANDROID_IMPLEMENTATION)}

    def _verified_provenance(self):
        provenance = self._provenance()
        if self._digest(provenance) != self._identity:
            raise ValueError('The Android Genshin runtime changed during original-data preparation.')
        return provenance

    @property
    def identity(self):
        self._verified_provenance()
        return self._identity

    def decode(self, source, parameters, destination, *, work):
        self._verified_provenance()
        self._portable.decode(source, parameters, destination, work=work)

    def initial_seed(self, executable, metadata, *, expected_owner):
        from .genshin_native_channel import read_bootstrap_inputs
        self._verified_provenance()
        result = read_bootstrap_inputs(executable, metadata, expected_owner=expected_owner)
        self._verified_provenance()
        return result

    def channel_profile(self, executable, source, source_receipt, contract, *, directory, check_cancel):
        from .genshin_original_bootstrap import prepare_profile
        self._verified_provenance()
        result = prepare_profile(executable, source, source_receipt, contract, self,
                                 directory=directory, check_cancel=check_cancel)
        result.proof['runtime_provenance'] = self._verified_provenance()
        return result

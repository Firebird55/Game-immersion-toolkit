"""Platform adapter for the maintained account store; no desktop fallback."""
import base64


class AndroidProtectedStorageError(ValueError):
    pass


class AndroidProtectedBlobs:
    def __init__(self, native):
        self.native = native

    def protect(self, value: bytes, decrypt: bool = False) -> bytes:
        if type(value) is not bytes or type(decrypt) is not bool or len(value) > 1024**2 + 64:
            raise AndroidProtectedStorageError('Invalid protected account blob.')
        try:
            result = self.native.protect(base64.b64encode(value).decode('ascii'), decrypt)
            if result is None:
                raise ValueError()
            encoded = str(result)
            if len(encoded) > 1400000:
                raise ValueError()
            return base64.b64decode(encoded, validate=True)
        except Exception:
            raise AndroidProtectedStorageError('Protected Android account storage could not be accessed. Existing data was kept.') from None

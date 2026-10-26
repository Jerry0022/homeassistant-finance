"""In-memory stand-ins for HA Store / credential manager (no hass needed)."""

from __future__ import annotations

import copy

from cryptography.fernet import Fernet, MultiFernet


class FakeStore:
    """Plain HA-Store substitute."""

    def __init__(self, *args, **kwargs):
        self._data = None
        self.removed = False

    async def async_load(self):
        return copy.deepcopy(self._data)

    async def async_save(self, data):
        self._data = copy.deepcopy(data)

    async def async_remove(self):
        self._data = None
        self.removed = True


class FakeEncryptedStore(FakeStore):
    """EncryptedStore substitute holding plaintext in memory."""


class FakeCred:
    """Credential-manager subset needed by the data layer, with real Fernet."""

    def __init__(self):
        self._fernet = MultiFernet([Fernet(Fernet.generate_key())])

    def encrypt_json(self, payload):
        import json

        return self._fernet.encrypt(json.dumps(payload).encode()).decode()

    def decrypt_json(self, token):
        import json

        return json.loads(self._fernet.decrypt(token.encode()))

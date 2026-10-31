"""Transport boundary for the Walgreens API.

``WalgreensClient`` depends on a ``Transport``, not on
``requests`` directly. The production implementation wraps a
``requests.Session``; tests and future async variants provide their
own implementation instead of subclassing a real session. Uploads
to cloud storage (see ``upload.py``) are a separate PUT path and
are deliberately not routed through this transport.
"""

from typing import Protocol, runtime_checkable

import requests


@runtime_checkable
class HttpResponse(Protocol):
    status_code: int
    headers: object
    text: str

    def json(self): ...


@runtime_checkable
class Transport(Protocol):
    def post(self, url, headers, json, timeout): ...

    def close(self): ...


class RequestsTransport:
    """A ``Transport`` backed by a ``requests.Session``.

    A session passed in belongs to the caller and is never closed
    here; a session created here is closed by ``close()``.
    """

    def __init__(self, session=None):
        self._owns_session = session is None
        self._session = session or requests.Session()

    def post(self, url, headers, json, timeout):
        return self._session.post(url, headers=headers, json=json, timeout=timeout)

    def close(self):
        if self._owns_session:
            self._session.close()

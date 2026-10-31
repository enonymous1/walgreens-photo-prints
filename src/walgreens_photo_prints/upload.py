"""Image upload to Walgreens cloud storage via a SAS token.

The flow is: fetch upload credentials once, turn the ``sasKeyToken``
into an upload URL, then PUT the image to that URL. Uploaded files are
not accessible afterwards, per the API reference.

``build_upload_url`` carries a fail-loud invariant: the SAS token must
split into exactly a container part and a signature part on ``?``.
A token that does not is rejected instead of producing a silently
wrong URL.
"""

import mimetypes
import os
import uuid

import requests

from .errors import WalgreensApiError


def build_upload_url(sas_key_token, aff_id, *, image_name=None):
    """Build an upload URL from a SAS key token.

    Splits the token on the first ``?`` into blob container and
    signature, then returns ``<container>/<imageName>?<signature>``
    where the image name defaults to ``Image-<affId>-<uuid>.jpg``.
    """
    if not aff_id or not str(aff_id).strip():
        raise ValueError("aff_id is required to build an upload URL.")
    if not sas_key_token:
        raise ValueError("sas_key_token is required to build an upload URL.")
    container, sep, signature = str(sas_key_token).partition("?")
    if not sep or not container or not signature:
        raise ValueError(
            "sas_key_token must contain a '?' separating the blob container from the signature."
        )
    if "?" in signature:
        raise ValueError("sas_key_token must contain exactly one '?'.")
    name = image_name or f"Image-{aff_id}-{uuid.uuid4()}.jpg"
    # An unsanitised name could change the URL path or break the
    # query string, so only a bare filename is accepted.
    if not name.strip() or name.strip() != name or "/" in name or "\\" in name or "?" in name:
        raise ValueError(f"Invalid image_name: {image_name!r}.")
    return f"{container}/{name}?{signature}"


def upload_image(
    upload_url, image_path, *, request_id=None, timeout=30.0, session=None, content_type=None
):
    """PUT an image file to an upload URL.

    Returns the HTTP status code. Raises ``FileNotFoundError`` for a
    missing file and ``WalgreensApiError`` for a failed upload.
    The ``x-ms-client-request-id`` defaults to a fresh UUID; the
    original code used a fixed placeholder containing non-hex
    characters, which this replaces. ``x-ms-blob-type: BlockBlob``
    is the Azure blob type the API's storage expects, and
    ``Content-Length`` is sent explicitly because the body is a
    file stream. A session passed in is never closed here; a
    session created here is always closed.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    owns_session = session is None
    http = session or requests.Session()
    guessed_type = mimetypes.guess_type(image_path)[0]
    headers = {
        "Content-Length": str(os.path.getsize(image_path)),
        "Content-Type": content_type or guessed_type or "image/jpeg",
        "x-ms-blob-type": "BlockBlob",
        "x-ms-client-request-id": request_id or str(uuid.uuid4()),
    }
    try:
        with open(image_path, "rb") as image_file:
            response = http.put(upload_url, headers=headers, data=image_file, timeout=timeout)
    except requests.RequestException as exc:
        raise WalgreensApiError(f"Image upload failed: {exc}") from exc
    finally:
        if owns_session:
            http.close()
    if not 200 <= response.status_code < 300:
        raise WalgreensApiError(
            f"Image upload returned HTTP {response.status_code}.",
            status_code=response.status_code,
        )
    return response.status_code


def upload_image_for_credentials(client, image_path, *, timeout=30.0, session=None):
    """Fetch credentials once, build an upload URL, and upload.

    Returns ``(upload_url, status_code)``. This replaces the original
    two-step flow, which fetched credentials on import in one module
    and again when generating the token in another.
    """
    credentials = client.fetch_upload_credentials()
    if not credentials.sas_key_token:
        raise WalgreensApiError("Upload credentials response contained no sasKeyToken.")
    upload_url = build_upload_url(credentials.sas_key_token, client.config.aff_id)
    status_code = upload_image(upload_url, image_path, timeout=timeout, session=session)
    return upload_url, status_code

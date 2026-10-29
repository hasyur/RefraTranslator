"""TLS configuration for managed artifact downloads."""

from __future__ import annotations

import os
import ssl

import certifi


def create_download_ssl_context() -> ssl.SSLContext:
    """Trust Windows' certificate store and certifi for managed downloads.

    Honor the standard OpenSSL override variables as explicit replacements,
    with SSL_CERT_FILE taking precedence over SSL_CERT_DIR as in HTTPX.
    """
    cafile = os.environ.get("SSL_CERT_FILE")
    capath = os.environ.get("SSL_CERT_DIR")
    if cafile:
        return ssl.create_default_context(cafile=cafile)
    if capath:
        return ssl.create_default_context(capath=capath)

    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context

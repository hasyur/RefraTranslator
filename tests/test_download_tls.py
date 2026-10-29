from __future__ import annotations

import ssl
from pathlib import Path
from types import SimpleNamespace

import pytest

from game_screen_translator import download_tls


def test_download_tls_adds_certifi_to_the_platform_trust_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    certifi_bundle = tmp_path / "certifi.pem"
    context = SimpleNamespace(calls=[])
    context.load_verify_locations = lambda **kwargs: context.calls.append(kwargs)
    default_context_calls: list[dict[str, str | None]] = []
    monkeypatch.setattr(
        download_tls.ssl,
        "create_default_context",
        lambda **kwargs: (default_context_calls.append(kwargs) or context),
    )
    monkeypatch.setattr(download_tls.certifi, "where", lambda: str(certifi_bundle))

    result = download_tls.create_download_ssl_context()

    assert result is context
    assert default_context_calls == [{}]
    assert context.calls == [{"cafile": str(certifi_bundle)}]


@pytest.mark.parametrize(
    ("file_override", "dir_override", "expected_options"),
    [
        (True, False, "file"),
        (False, True, "dir"),
        (True, True, "file"),
    ],
)
def test_download_tls_honors_explicit_openssl_ca_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_override: bool,
    dir_override: bool,
    expected_options: str,
) -> None:
    cert_file = str(tmp_path / "custom.pem")
    cert_dir = str(tmp_path / "custom-certs")
    if file_override:
        monkeypatch.setenv("SSL_CERT_FILE", cert_file)
    else:
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    if dir_override:
        monkeypatch.setenv("SSL_CERT_DIR", cert_dir)
    else:
        monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    calls: list[dict[str, str | None]] = []
    monkeypatch.setattr(
        download_tls.ssl,
        "create_default_context",
        lambda **kwargs: (calls.append(kwargs) or context),
    )
    monkeypatch.setattr(
        download_tls.certifi,
        "where",
        lambda: pytest.fail("certifi must not override an explicit CA setting"),
    )

    assert download_tls.create_download_ssl_context() is context
    if expected_options == "file":
        assert calls == [{"cafile": cert_file}]
    else:
        assert calls == [{"capath": cert_dir}]


def test_download_tls_keeps_certificate_and_hostname_verification_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    context = download_tls.create_download_ssl_context()

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.get_ca_certs()

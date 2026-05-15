from cryptography.fernet import Fernet

from app.core import crypto as crypto_module


def _enable_encryption(monkeypatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    settings = crypto_module.settings
    monkeypatch.setattr(settings, "ENCRYPT_DATA", True)
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", key)
    return key


def test_get_fernet_returns_none_when_disabled(monkeypatch):
    settings = crypto_module.settings
    monkeypatch.setattr(settings, "ENCRYPT_DATA", False)
    assert crypto_module._get_fernet() is None


def test_get_fernet_returns_none_when_no_key(monkeypatch):
    settings = crypto_module.settings
    monkeypatch.setattr(settings, "ENCRYPT_DATA", True)
    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", "")
    assert crypto_module._get_fernet() is None


def test_get_fernet_returns_instance_when_configured(monkeypatch):
    _enable_encryption(monkeypatch)
    fernet = crypto_module._get_fernet()
    assert fernet is not None
    encrypted = fernet.encrypt(b"hello").decode("utf-8")
    assert fernet.decrypt(encrypted.encode("utf-8")) == b"hello"


def test_encrypted_text_passthrough_when_disabled(monkeypatch):
    settings = crypto_module.settings
    monkeypatch.setattr(settings, "ENCRYPT_DATA", False)
    col = crypto_module.EncryptedText()
    assert col.process_bind_param("plain", dialect=None) == "plain"
    assert col.process_result_value("plain", dialect=None) == "plain"


def test_encrypted_text_handles_none(monkeypatch):
    _enable_encryption(monkeypatch)
    col = crypto_module.EncryptedText()
    assert col.process_bind_param(None, dialect=None) is None
    assert col.process_result_value(None, dialect=None) is None


def test_encrypted_text_round_trip(monkeypatch):
    _enable_encryption(monkeypatch)
    col = crypto_module.EncryptedText()
    token = col.process_bind_param("secret payload", dialect=None)
    assert isinstance(token, str)
    assert token != "secret payload"
    decrypted = col.process_result_value(token, dialect=None)
    assert decrypted == "secret payload"


def test_encrypted_text_bind_passes_through_non_string(monkeypatch):
    _enable_encryption(monkeypatch)
    col = crypto_module.EncryptedText()
    assert col.process_bind_param(42, dialect=None) == 42


def test_encrypted_text_returns_raw_when_token_invalid(monkeypatch):
    _enable_encryption(monkeypatch)
    col = crypto_module.EncryptedText()
    raw = "not-a-real-fernet-token"
    assert col.process_result_value(raw, dialect=None) == raw

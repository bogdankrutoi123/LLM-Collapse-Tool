from sqlalchemy.types import TypeDecorator, Text
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import get_settings

settings = get_settings()


def _get_fernet() -> Fernet | None:
    if not settings.ENCRYPT_DATA:
        return None
    if not settings.DATA_ENCRYPTION_KEY:
        return None
    return Fernet(settings.DATA_ENCRYPTION_KEY.encode("utf-8"))


class EncryptedText(TypeDecorator):
    """Encrypt/decrypt text transparently if ENCRYPT_DATA is enabled."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        fernet = _get_fernet()
        if not fernet:
            return value
        if isinstance(value, str):
            token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
            return token
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        fernet = _get_fernet()
        if not fernet:
            return value
        try:
            return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError):
            return value

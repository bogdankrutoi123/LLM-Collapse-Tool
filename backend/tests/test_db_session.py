import pytest

from app.db import session as db_session_module


def test_get_db_yields_session_and_closes(session_factory, monkeypatch):
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)
    gen = db_session_module.get_db()
    db = next(gen)
    assert db.execute.__call__ is not None
    with pytest.raises(StopIteration):
        next(gen)
    db.close()


def test_get_db_closes_on_exception(session_factory, monkeypatch):
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)
    gen = db_session_module.get_db()
    db = next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("simulated handler failure"))
    db.close()

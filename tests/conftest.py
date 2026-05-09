"""Shared pytest fixtures for all test suites."""

import pytest
import db


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """
    Provides a fresh, isolated SQLite database for each test.
    Patches db.DB_FILE to a temp path, initializes the schema,
    and tears down automatically after the test.
    """
    db_path = str(tmp_path / "test_history.db")
    monkeypatch.setattr(db, "DB_FILE", db_path)
    db.init_db()
    return db_path

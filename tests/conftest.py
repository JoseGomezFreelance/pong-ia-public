"""Fixtures compartidos para pytest."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture(scope="session", autouse=True)
def headless_env() -> Generator[None, None, None]:
    """Configura SDL en modo headless para toda la sesion de tests."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    yield


@pytest.fixture()
def game_harness() -> Generator[object, None, None]:
    """Crea un GameHarness con context manager."""
    from pong.harness import GameHarness

    with GameHarness.create() as h:
        yield h


@pytest.fixture()
def tmp_save_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige save_manager a un directorio temporal."""
    import pong.save_manager as sm

    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    save_file = save_dir / "game_history.json"
    monkeypatch.setattr(sm, "SAVE_DIR", save_dir)
    monkeypatch.setattr(sm, "SAVE_FILE", save_file)
    return save_dir

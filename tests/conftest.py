"""Pytest fixtures for pybravia tests."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any, cast

import pytest
from aioresponses import aioresponses

from pybravia import BraviaClient

TEST_HOST = "192.168.1.100"
TEST_MAC = "AA:BB:CC:DD:EE:FF"
TEST_PSK = "test_psk"
TEST_PIN = "1234"
TEST_CLIENTID = "test_client"
TEST_NICKNAME = "test_nickname"


@pytest.fixture
async def client() -> AsyncGenerator[BraviaClient]:
    """Create a BraviaClient instance and cleanup after test."""
    _client = BraviaClient(host=TEST_HOST, mac=TEST_MAC)
    yield _client
    await _client.disconnect()


@pytest.fixture
def mock_aioresponse() -> Generator[aioresponses]:
    """Create aioresponses context."""
    with aioresponses() as mock:
        yield mock


@pytest.fixture
def system_info() -> dict[str, list[dict[str, Any]]]:
    """Return system info data from the fixture file."""
    with Path("tests/fixtures/system_info.json").open(encoding="utf-8") as file:
        return cast(dict[str, list[dict[str, str]]], json.load(file))

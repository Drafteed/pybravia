"""Tests for BraviaClient."""

from __future__ import annotations

from unittest.mock import MagicMock

from aiohttp import ClientSession
from aioresponses import aioresponses

from pybravia import BraviaClient
from pybravia.const import SERVICE_SYSTEM

from .conftest import TEST_HOST, TEST_MAC, TEST_PSK


def test_client_init() -> None:
    """Test client initialization with defaults."""
    client = BraviaClient(host=TEST_HOST)

    assert client.host == TEST_HOST
    assert client.mac is None
    assert client._session is None
    assert str(client._base_url) == f"http://{TEST_HOST}"
    assert client._ssl_verify is False
    assert client._auth is None
    assert client._psk is None
    assert client._commands == {}


def test_client_init_with_mac() -> None:
    """Test client initialization with MAC address."""
    client = BraviaClient(host=TEST_HOST, mac=TEST_MAC)

    assert client.mac == TEST_MAC


def test_client_init_with_ssl() -> None:
    """Test client initialization with SSL enabled."""
    client = BraviaClient(host=TEST_HOST, ssl=True, ssl_verify=True)

    assert str(client._base_url) == f"https://{TEST_HOST}"
    assert client._ssl_verify is True


def test_client_init_with_session() -> None:
    """Test client initialization with existing session."""
    session = MagicMock(spec=ClientSession)
    client = BraviaClient(host=TEST_HOST, session=session)

    assert client._session is session


async def test_connect_with_psk(
    client: BraviaClient, mock_aioresponse: aioresponses
) -> None:
    """Test connection with PSK."""
    system_info = {
        "result": [
            {
                "product": "TV",
                "region": "XEU",
                "language": "pol",
                "model": "KD-55XF8596",
                "serial": "1112233",
                "macAddr": TEST_MAC,
                "name": "BRAVIA",
                "generation": "5.4.0",
                "area": "POL",
                "cid": "xyzabc123",
            }
        ]
    }
    mock_aioresponse.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload=system_info,
    )

    await client.connect(psk=TEST_PSK)

    assert client._psk == TEST_PSK

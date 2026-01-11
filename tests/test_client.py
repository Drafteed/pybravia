"""Tests for BraviaClient."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from pybravia import BraviaClient
from pybravia.const import SERVICE_ACCESS_CONTROL, SERVICE_SYSTEM
from pybravia.exceptions import (
    BraviaAuthError,
    BraviaConnectionError,
    BraviaConnectionTimeout,
    BraviaNotFound,
    BraviaNotSupported,
)

from .conftest import (
    TEST_CLIENTID,
    TEST_HOST,
    TEST_MAC,
    TEST_NICKNAME,
    TEST_PIN,
    TEST_PSK,
)


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
    client: BraviaClient,
    mock_aioresponse: aioresponses,
    system_info: dict[str, list[dict[str, object]]],
) -> None:
    """Test connection with PSK."""
    mock_aioresponse.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload=system_info,
    )

    await client.connect(psk=TEST_PSK)

    assert client._psk == TEST_PSK


async def test_connect_with_pin(
    client: BraviaClient,
    mock_aioresponse: aioresponses,
    system_info: dict[str, list[dict[str, object]]],
) -> None:
    """Test connection with PIN."""
    mock_aioresponse.post(
        f"http://{TEST_HOST}/sony/{SERVICE_ACCESS_CONTROL}",
        payload={"result": []},
    )
    mock_aioresponse.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload=system_info,
    )

    await client.connect(pin=TEST_PIN, clientid=TEST_CLIENTID, nickname=TEST_NICKNAME)

    assert client._auth.password == TEST_PIN
    assert client._psk is None


async def test_connect_not_supported(
    client: BraviaClient, mock_aioresponse: aioresponses
) -> None:
    """Test connection failure when device is not supported."""
    mock_aioresponse.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload={"result": [{}]},
    )

    with pytest.raises(BraviaNotSupported):
        await client.connect(psk=TEST_PSK)


async def test_send_wol_req_success(client: BraviaClient) -> None:
    """Test WOL request sends packet."""
    with patch.object(client, "_send_wol_packet") as mock_send:
        result = await client.send_wol_req()

    assert result is True
    mock_send.assert_called_once()


async def test_send_wol_req_no_mac() -> None:
    """Test WOL request without MAC returns False."""
    client = BraviaClient(host=TEST_HOST)

    result = await client.send_wol_req()

    assert result is False


def test_send_wol_packet(client: BraviaClient) -> None:
    """Test WOL packet is sent via socket."""
    packet = b"\xff" * 6 + b"\xaa\xbb\xcc\xdd\xee\xff" * 16

    with patch("socket.socket") as mock_socket:
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        client._send_wol_packet(packet)

        mock_sock.setsockopt.assert_called_once()
        mock_sock.sendto.assert_called_once_with(packet, ("<broadcast>", 9))


@pytest.mark.asyncio
async def test_pair(client: BraviaClient, mock_aioresponse: aioresponses) -> None:
    """Test pairing process."""
    mock_aioresponse.post(
        f"http://{TEST_HOST}/sony/{SERVICE_ACCESS_CONTROL}",
        payload={"result": []},
    )

    await client.pair(TEST_CLIENTID, TEST_NICKNAME)

    kwargs = list(mock_aioresponse.requests.values())[0][0].kwargs
    assert kwargs["json"]["method"] == "actRegister"
    assert kwargs["json"]["params"] == [
        {"clientid": TEST_CLIENTID, "nickname": TEST_NICKNAME, "level": "private"},
        [{"function": "WOL", "value": "yes"}],
    ]


async def test_send_req_json_response(
    client: BraviaClient, mock_aioresponse: aioresponses
) -> None:
    """Test send_req returns JSON response."""
    expected = {"result": [{"key": "value"}]}
    mock_aioresponse.post(
        f"http://{TEST_HOST}/test",
        payload=expected,
    )

    result = await client.send_req(client._base_url / "test", json=True)

    assert result == expected


async def test_send_req_non_json(
    client: BraviaClient, mock_aioresponse: aioresponses
) -> None:
    """Test send_req returns True for non-JSON success."""
    mock_aioresponse.post(
        f"http://{TEST_HOST}/test",
        body="OK",
        status=200,
    )

    result = await client.send_req(client._base_url / "test", json=False)

    assert result is True


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (HTTPStatus.NOT_FOUND, BraviaNotFound),
        (HTTPStatus.UNAUTHORIZED, BraviaAuthError),
        (HTTPStatus.FORBIDDEN, BraviaAuthError),
    ],
)
async def test_send_req_status(
    client: BraviaClient,
    mock_aioresponse: aioresponses,
    status: HTTPStatus,
    exc: Exception,
) -> None:
    """Test send_req raises an exception."""
    mock_aioresponse.post(
        f"http://{TEST_HOST}/test",
        status=status,
    )

    with pytest.raises(exc):
        await client.send_req(client._base_url / "test")


@pytest.mark.parametrize(
    ("exc", "bravia_exc"),
    [
        (asyncio.TimeoutError, BraviaConnectionTimeout),
        (ConnectionError, BraviaConnectionError),
    ],
)
async def test_send_req_exc(
    client: BraviaClient,
    mock_aioresponse: aioresponses,
    exc: Exception,
    bravia_exc: Exception,
) -> None:
    """Test send_req raises BraviaConnectionTimeout on timeout."""
    mock_aioresponse.post(
        f"http://{TEST_HOST}/test",
        exception=exc,
    )

    with pytest.raises(bravia_exc):
        await client.send_req(client._base_url / "test")

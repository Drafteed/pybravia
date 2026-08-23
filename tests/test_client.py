"""Tests for BraviaClient."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientSession, encode_basic_auth
from aiointercept import aiointercept

from pybravia import BraviaClient
from pybravia.const import (
    CODE_POWER_ON,
    SERVICE_ACCESS_CONTROL,
    SERVICE_APP_CONTROL,
    SERVICE_SYSTEM,
)
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
    assert client._auth_header is None
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
    mock_http: aiointercept,
    system_info: dict[str, list[dict[str, object]]],
) -> None:
    """Test connection with PSK."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload=system_info,
    )

    await client.connect(psk=TEST_PSK)

    assert client._psk == TEST_PSK


async def test_connect_with_pin(
    client: BraviaClient,
    mock_http: aiointercept,
    system_info: dict[str, list[dict[str, object]]],
) -> None:
    """Test connection with PIN."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_ACCESS_CONTROL}",
        payload={"result": []},
    )
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload=system_info,
    )

    await client.connect(pin=TEST_PIN, clientid=TEST_CLIENTID, nickname=TEST_NICKNAME)

    assert client._auth_header == encode_basic_auth("", TEST_PIN)
    assert client._psk is None


async def test_connect_not_supported(
    client: BraviaClient, mock_http: aiointercept
) -> None:
    """Test connection failure when device is not supported."""
    mock_http.post(
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
async def test_pair(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test pairing process."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_ACCESS_CONTROL}",
        payload={"result": []},
    )

    await client.pair(TEST_CLIENTID, TEST_NICKNAME)

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "actRegister"
    assert payload["params"] == [
        {"clientid": TEST_CLIENTID, "nickname": TEST_NICKNAME, "level": "private"},
        [{"function": "WOL", "value": "yes"}],
    ]


async def test_send_req_json_response(
    client: BraviaClient, mock_http: aiointercept
) -> None:
    """Test send_req returns JSON response."""
    expected = {"result": [{"key": "value"}]}
    mock_http.post(
        f"http://{TEST_HOST}/test",
        payload=expected,
    )

    result = await client.send_req(client._base_url / "test", json=True)

    assert result == expected


async def test_send_req_non_json(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test send_req returns True for non-JSON success."""
    mock_http.post(
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
    mock_http: aiointercept,
    status: HTTPStatus,
    exc: Exception,
) -> None:
    """Test send_req raises an exception."""
    mock_http.post(
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
    exc: type[Exception],
    bravia_exc: type[Exception],
) -> None:
    """Test send_req raises BraviaConnectionTimeout on timeout."""
    with (
        patch("aiohttp.ClientSession.post", side_effect=exc),
        pytest.raises(bravia_exc),
    ):
        await client.send_req(client._base_url / "test")


@pytest.mark.parametrize(
    ("cmd", "method"),
    [
        ("Pause", "pause"),
        ("Play", "play"),
        ("Next", "next_track"),
        ("Prev", "previous_track"),
        ("ChannelUp", "channel_up"),
        ("ChannelDown", "channel_down"),
    ],
)
async def test_playback_control(
    client: BraviaClient, mock_http: aiointercept, cmd: str, method: str
) -> None:
    """Test playback control command."""
    client._commands = {cmd: f"test_{method}"}

    with patch.object(client, "send_ircc_req", return_value=True) as mock_send_ircc_req:
        method_func = getattr(client, method)
        result = await method_func()

    assert result is True

    mock_send_ircc_req.assert_called_with(f"test_{method}")


async def test_stop(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test stop command when the list of available commands is empty."""
    test_code = "test_stop_code"
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload={
            "result": [
                {"bundled": True, "type": "IR_REMOTE_BUNDLE_TYPE_RESERVED01"},
                [{"name": "Stop", "value": test_code}],
            ],
            "id": 1,
        },
    )

    with patch.object(client, "send_ircc_req", return_value=True) as mock_send_ircc_req:
        result = await client.stop()

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "getRemoteControllerInfo"
    assert payload["params"] == []

    mock_send_ircc_req.assert_called_with(test_code)


async def test_reboot(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test reboot sends command."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload={"result": []},
    )

    result = await client.reboot()

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "requestReboot"
    assert payload["params"] == []


async def test_terminate_apps(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test terminate_apps sends command."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_APP_CONTROL}",
        payload={"result": []},
    )

    result = await client.terminate_apps()

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "terminateApps"
    assert payload["params"] == []


async def test_set_text_form(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test set_text_form sends text input."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_APP_CONTROL}",
        payload={"result": []},
    )

    result = await client.set_text_form("test text")

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "setTextForm"
    assert payload["params"] == ["test text"]


@pytest.mark.parametrize(
    ("method", "step", "expected_param"),
    [
        ("volume_up", 2, "+2"),
        ("volume_down", 3, "-3"),
    ],
)
async def test_volume_up_down(
    client: BraviaClient,
    mock_http: aiointercept,
    method: str,
    step: int,
    expected_param: str,
) -> None:
    """Test volume_up and volume_down methods."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/audio",
        payload={"result": []},
    )

    method_func = getattr(client, method)
    result = await method_func(step=step)

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "setAudioVolume"
    assert payload["params"] == [{"target": "speaker", "volume": expected_param}]


async def test_volume_level(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test volume_level sets absolute volume."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/audio",
        payload={"result": []},
    )

    result = await client.volume_level(level=25)

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "setAudioVolume"
    assert payload["params"] == [{"target": "speaker", "volume": "25"}]


async def test_volume_level_with_ui_mode(
    client: BraviaClient, mock_http: aiointercept
) -> None:
    """Test volume_level with UI mode parameter."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/audio",
        payload={"result": []},
    )

    result = await client.volume_level(level=30, ui_mode="on")

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "setAudioVolume"
    assert payload["params"] == [{"target": "speaker", "volume": "30", "ui": "on"}]


async def test_volume_mute_explicit(
    client: BraviaClient, mock_http: aiointercept
) -> None:
    """Test volume_mute with explicit mute value."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/audio",
        payload={"result": []},
    )

    result = await client.volume_mute(mute=True)

    assert result is True

    payload = await next(iter(mock_http.requests.values()))[0].json()
    assert payload["method"] == "setAudioMute"
    assert payload["params"] == [{"status": True}]


async def test_volume_mute_toggle(
    client: BraviaClient, mock_http: aiointercept
) -> None:
    """Test volume_mute toggles mute status."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/audio",
        payload={
            "result": [
                [
                    {
                        "target": "speaker",
                        "volume": 20,
                        "mute": False,
                        "maxVolume": 100,
                        "minVolume": 0,
                    }
                ]
            ]
        },
    )
    mock_http.post(
        f"http://{TEST_HOST}/sony/audio",
        payload={"result": []},
    )

    result = await client.volume_mute()

    assert result is True

    requests = list(mock_http.requests.values())
    payload = await requests[0][0].json()
    assert payload["method"] == "getVolumeInformation"

    payload = await requests[0][1].json()
    assert payload["method"] == "setAudioMute"
    assert payload["params"] == [{"status": True}]


async def test_turn_on(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test turn_on sends WOL and power commands."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload={"result": [{"status": "standby"}], "id": 1},
    )
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload={"result": [], "id": 1},
    )
    mock_http.post(
        f"http://{TEST_HOST}/sony/IRCC",
        body="OK",
        status=200,
    )
    mock_http.post(
        f"http://{TEST_HOST}/sony/IRCC",
        body="OK",
        status=200,
    )

    with patch.object(client, "send_wol_req", return_value=True) as mock_wol:
        result = await client.turn_on()

    assert result is True
    mock_wol.assert_called_once()

    requests = list(mock_http.requests.values())

    payload = await requests[0][0].json()
    assert payload["method"] == "getPowerStatus"

    payload = await requests[0][1].json()
    assert payload["method"] == "setPowerStatus"
    assert payload["params"] == [{"status": True}]

    # Empty request to 'wake up' the API
    body = requests[1][0].captured_body.decode()
    assert "<IRCCCode></IRCCCode>" in body

    body = requests[1][1].captured_body.decode()
    assert f"<IRCCCode>{CODE_POWER_ON}</IRCCCode>" in body


async def test_turn_off(client: BraviaClient, mock_http: aiointercept) -> None:
    """Test turn_off sends power off command."""
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload={"result": [], "id": 1},
    )
    mock_http.post(
        f"http://{TEST_HOST}/sony/{SERVICE_SYSTEM}",
        payload={"error": [400, "not power-on"], "id": 1},
    )

    result = await client.turn_off()
    already_off_result = await client.turn_off()

    assert result is True
    assert already_off_result is True

    requests = next(iter(mock_http.requests.values()))
    assert len(requests) == 2

    payload = await requests[0].json()
    assert payload["method"] == "setPowerStatus"
    assert payload["params"] == [{"status": False}]

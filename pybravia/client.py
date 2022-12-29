"""Python library for remote control of Sony Bravia TV."""
from __future__ import annotations

import asyncio
import logging
import socket
from contextlib import suppress
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any

from aiohttp import BasicAuth, ClientError, ClientSession, CookieJar

from .const import (
    CODE_POWER_ON,
    DEFAULT_AUDIO_TARGET,
    DEFAULT_TIMEOUT,
    DEFAULT_VERSION,
    PAIR_PIN,
    SERVICE_ACCESS_CONTROL,
    SERVICE_APP_CONTROL,
    SERVICE_AUDIO,
    SERVICE_AV_CONTENT,
    SERVICE_GUIDE,
    SERVICE_SYSTEM,
)
from .exceptions import (
    BraviaTVAuthError,
    BraviaTVConnectionError,
    BraviaTVConnectionTimeout,
    BraviaTVError,
    BraviaTVNotFound,
    BraviaTVNotSupported,
    BraviaTVTurnedOff,
)
from .util import normalize_cookies

_LOGGER = logging.getLogger(__name__)


class BraviaTV:
    """Represent a BraviaTV client."""

    def __init__(
        self, host: str, mac: str | None = None, session: ClientSession | None = None
    ) -> None:
        """Initialize the device."""
        self.host = host
        self.mac = mac
        self._session = session
        self._auth: BasicAuth | None = None
        self._psk: str | None = None
        self._send_ircc_time: datetime | None = None
        self._commands: dict[str, str] = {}

    async def connect(
        self,
        pin: str | None = None,
        psk: str | None = None,
        clientid: str | None = None,
        nickname: str | None = None,
    ) -> None:
        """Connect to device with PIN or PSK."""
        self._psk = pin[4:] if pin and pin[:4] == "psk:" else psk

        _LOGGER.debug(
            "Connect with pin: %s, psk: %s, clientid: %s, nickname: %s",
            pin,
            self._psk,
            clientid,
            nickname,
        )

        if self._psk is None:
            assert pin is not None
            assert clientid is not None
            assert nickname is not None
            await self.register(pin, clientid, nickname)
        else:
            if self._session is not None:
                self._auth = None
                self._session.cookie_jar.clear()

        system_info = await self.get_system_info()
        if not system_info:
            raise BraviaTVNotSupported

        if self._psk:
            _LOGGER.debug("Connected with PSK")
        else:
            _LOGGER.debug(
                "Connected with PIN, cookie len: %s", len(self._session._cookie_jar)
            )

    async def register(self, pin: str, clientid: str, nickname: str) -> None:
        """Register the device with PIN."""
        self._auth = BasicAuth("", pin)
        params = [
            {"clientid": clientid, "nickname": nickname, "level": "private"},
            [{"value": "yes", "function": "WOL"}],
        ]
        await self.send_rest_req(
            SERVICE_ACCESS_CONTROL,
            "actRegister",
            params,
        )

    async def pair(self, clientid: str, nickname: str) -> None:
        """Register with PIN "0000" to start the pairing process on the TV."""
        with suppress(BraviaTVAuthError):
            await self.register(PAIR_PIN, clientid, nickname)

    async def disconnect(self) -> None:
        """Close connection."""
        if self._session:
            await self._session.close()
        self._auth = None
        self._psk = None
        self._session = None

    async def send_wol_req(self) -> bool:
        """Send WOL packet to device."""
        if self.mac is None:
            return False
        mac = self.mac.replace(":", "")
        packet = bytes.fromhex("F" * 12 + mac * 16)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, ("<broadcast>", 9))
        return True

    async def send_req(
        self,
        url: str,
        data: Any = None,
        headers: dict[str, Any] | None = None,
        json: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Any:
        """Send HTTP request."""
        result = {} if json else False

        if self._session is None:
            self._session = ClientSession(
                cookie_jar=CookieJar(unsafe=True, quote_cookie=False)
            )

        if headers is None:
            headers = {}

        if self._psk:
            headers["X-Auth-PSK"] = self._psk

        headers["Cache-Control"] = "no-cache"
        headers["Connection"] = "keep-alive"

        _LOGGER.debug("Request %s, data: %s, headers: %s", url, data, headers)

        try:
            if json:
                response = await self._session.post(
                    url, json=data, headers=headers, timeout=timeout, auth=self._auth
                )
            else:
                response = await self._session.post(
                    url, data=data, headers=headers, timeout=timeout, auth=self._auth
                )

            _LOGGER.debug("Response status: %s", response.status)

            # Normalize non RFC-compliant cookie
            # https://github.com/Drafteed/pybravia/issues/1#issuecomment-1237452709
            cookies = response.headers.getall("set-cookie", None)
            if cookies:
                normalized_cookies = normalize_cookies(cookies)
                self._session.cookie_jar.update_cookies(normalized_cookies)

            if response.status == 200:
                result = await response.json() if json else True
                _LOGGER.debug("Response result: %s", result)
                if isinstance(result, dict) and "not power-on" in result.get(
                    "error", []
                ):
                    raise BraviaTVTurnedOff
            if response.status == 404:
                raise BraviaTVNotFound
            if response.status in [401, 403]:
                raise BraviaTVAuthError
        except ClientError as err:
            _LOGGER.debug("Request error %s", err)
            raise BraviaTVConnectionError from err
        except ConnectionError as err:
            _LOGGER.debug("Connection error %s", err)
            raise BraviaTVConnectionError from err
        except asyncio.exceptions.TimeoutError as err:
            _LOGGER.debug("Request timeout %s", err)
            raise BraviaTVConnectionTimeout from err

        return result

    async def send_ircc_req(self, code: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
        """Send IRCC request to device."""

        # After about 13 minutes of inactivity, some TV`s
        # ignores the first command without giving any error.
        # This make an empty request to 'wake up' the api.
        if code != "":
            time = datetime.now()
            if self._send_ircc_time is None or (
                time - self._send_ircc_time
            ) > timedelta(minutes=10):
                with suppress(BraviaTVError):
                    await self.send_ircc_req("")
            self._send_ircc_time = time

        url = f"http://{self.host}/sony/ircc"
        headers = {
            "SOAPACTION": '"urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"',
            "Content-Type": "text/xml; charset=UTF-8",
        }
        data = (
            "<s:Envelope"
            ' xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            '<u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">'
            f"<IRCCCode>{code}</IRCCCode>"
            "</u:X_SendIRCC>"
            "</s:Body>"
            "</s:Envelope>"
        )

        return await self.send_req(
            url=url, data=data, headers=headers, json=False, timeout=timeout
        )

    async def send_rest_req(
        self,
        service: str,
        method: str,
        params: Any = None,
        headers: dict[str, Any] | None = None,
        version: str = DEFAULT_VERSION,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Any:
        """Send REST request to device."""
        url = f"http://{self.host}/sony/{service}"
        params = params if isinstance(params, list) else [params] if params else []
        data = {
            "method": method,
            "params": params,
            "id": 1,
            "version": version,
        }

        return await self.send_req(
            url=url, data=data, headers=headers, json=True, timeout=timeout
        )

    async def send_rest_quick(self, *args: Any, **kwargs: Any) -> bool:
        """Send and quick check REST request to device."""
        resp = await self.send_rest_req(*args, **kwargs)
        return "result" in resp

    async def send_command(self, command: str) -> bool:
        """Send IRCC command to device."""
        code = await self.get_command_code(command)
        if code is None:
            return False
        return await self.send_ircc_req(code)

    async def get_power_status(self) -> str:
        """Get current power status."""
        resp = await self.send_rest_req(SERVICE_SYSTEM, "getPowerStatus", timeout=5)
        result = resp.get("result", [{}])[0]
        return result.get("status", "off")

    async def get_power_saving_mode(self) -> str:
        """Get current power saving mode."""
        resp = await self.send_rest_req(SERVICE_SYSTEM, "getPowerSavingMode")
        result = resp.get("result", [{}])[0]
        return result.get("mode", "")

    async def get_system_info(self) -> dict[str, str]:
        """Get general information of the device."""
        resp = await self.send_rest_req(SERVICE_SYSTEM, "getSystemInformation")
        result = resp.get("result", [{}])[0]
        self.mac = result.get("macAddr", self.mac)
        return result

    async def get_api_info(self, services: list[str]) -> list[dict[str, Any]]:
        """Get supported services and their information."""
        resp = await self.send_rest_req(
            SERVICE_GUIDE,
            "getSupportedApiInfo",
            {"services": services},
        )
        result = resp.get("result", [[]])[0]
        return result

    async def get_wol_mode(self) -> bool:
        """Get information on the device's WOL mode settings."""
        resp = await self.send_rest_req(SERVICE_SYSTEM, "getWolMode")
        result = resp.get("result", [{}])[0]
        return result.get("enabled", False)

    async def get_led_status(self) -> dict[str, str]:
        """Get the LED Indicator mode and status."""
        resp = await self.send_rest_req(SERVICE_SYSTEM, "getLEDIndicatorStatus")
        result = resp.get("result", [{}])[0]
        return result

    async def get_remote_info(self) -> list[Any]:
        """Get information of the device's remote controller."""
        resp = await self.send_rest_req(SERVICE_SYSTEM, "getRemoteControllerInfo")
        result = resp.get("result", [{}, []])
        return result

    async def get_command_list(self) -> dict[str, str]:
        """Get list of all IRCC commands."""
        result = await self.get_remote_info()
        return {x["name"]: x["value"] for x in result[1]}

    async def get_command_code(self, command: str) -> str | None:
        """Get IRCC command code by name."""
        if not self._commands:
            self._commands = await self.get_command_list()
        return self._commands.get(command)

    async def get_volume_info(
        self, target: str = DEFAULT_AUDIO_TARGET
    ) -> dict[str, Any]:
        """Get the sound volume information with preferred target."""
        result = await self.get_volume_info_full()
        value = {}
        for output in result:
            value = output
            if target == output.get("target"):
                break
        return value

    async def get_volume_info_full(self) -> list[dict[str, Any]]:
        """Get information about the sound volume and mute status."""
        resp = await self.send_rest_req(SERVICE_AUDIO, "getVolumeInformation")
        result = resp.get("result", [[]])[0]
        return result

    async def get_app_list(self) -> list[dict[str, str]]:
        """Get list of applications."""
        resp = await self.send_rest_req(SERVICE_APP_CONTROL, "getApplicationList")
        result = resp.get("result", [[]])[0]
        return result

    async def get_scheme_list(self) -> list[str]:
        """Get list of schemes that the device can handle."""
        resp = await self.send_rest_req(SERVICE_AV_CONTENT, "getSchemeList")
        result = resp.get("result", [[]])[0]
        return [d["scheme"] for d in result if "scheme" in d]

    async def get_source_list(self, scheme: str) -> list[str]:
        """Get list of sources in the scheme."""
        resp = await self.send_rest_req(
            SERVICE_AV_CONTENT,
            "getSourceList",
            {"scheme": scheme},
        )
        result = resp.get("result", [[]])[0]
        return [d["source"] for d in result if "source" in d]

    async def get_content_count(self, source: str) -> int:
        """Get count of contents in the source."""
        resp = await self.send_rest_req(
            SERVICE_AV_CONTENT,
            "getContentCount",
            {"source": source},
        )
        result = resp.get("result", [{}])[0]
        return result.get("count", 0)

    async def get_content_list(
        self, source: str, index: int = 0, count: int = 50
    ) -> list[dict[str, Any]]:
        """Get list of contents in the source."""
        resp = await self.send_rest_req(
            SERVICE_AV_CONTENT,
            "getContentList",
            {"source": source, "stIdx": index, "cnt": count},
        )
        result = resp.get("result", [[]])[0]
        return result

    async def get_content_list_full(self, source: str) -> list[dict[str, Any]]:
        """Get full list of contents in the source."""
        result = []
        total = await self.get_content_count(source)
        for index in range(0, total, 50):
            count = min(50, total - index)
            resp = await self.get_content_list(source, index, count)
            result.extend(resp)
        return result

    async def get_content_list_all(self, scheme: str) -> list[dict[str, Any]]:
        """Get full list of contents in the scheme."""
        result = []
        sources = await self.get_source_list(scheme)
        for source in sources:
            resp = await self.get_content_list_full(source)
            result.extend(resp)
        return result

    async def get_external_status(
        self, version: str = DEFAULT_VERSION
    ) -> list[dict[str, Any]]:
        """Get information of all external input sources."""
        resp = await self.send_rest_req(
            SERVICE_AV_CONTENT,
            "getCurrentExternalInputsStatus",
            version=version,
        )
        result = resp.get("result", [[]])[0]
        return result

    async def get_playing_info(self) -> dict[str, Any]:
        """Get information of the currently playing content."""
        resp = await self.send_rest_req(SERVICE_AV_CONTENT, "getPlayingContentInfo")
        result = resp.get("result", [{}])[0]
        return result

    async def set_wol_mode(self, mode: bool) -> bool:
        """Set WOL mode settings of the device."""
        return await self.send_rest_quick(
            SERVICE_SYSTEM, "setWolMode", {"enabled": mode}
        )

    async def set_led_status(self, mode: str, status: str | None = None) -> bool:
        """Set the LED Indicator mode and status."""
        return await self.send_rest_quick(
            SERVICE_SYSTEM,
            "setLEDIndicatorStatus",
            {"mode": mode, "status": status},
            version="1.1",
        )

    async def set_active_app(self, uri: str) -> bool:
        """Launch an application by URI."""
        return await self.send_rest_quick(
            SERVICE_APP_CONTROL, "setActiveApp", {"uri": uri}
        )

    async def set_play_content(self, uri: str) -> bool:
        """Play content by URI."""
        return await self.send_rest_quick(
            SERVICE_AV_CONTENT, "setPlayContent", {"uri": uri}
        )

    async def set_power_status(self, status: bool) -> bool:
        """Change the current power status of the device."""
        return await self.send_rest_quick(
            SERVICE_SYSTEM, "setPowerStatus", {"status": status}
        )

    async def set_power_saving_mode(self, mode: str) -> bool:
        """Change the setting of the power saving mode."""
        return await self.send_rest_quick(
            SERVICE_SYSTEM, "setPowerSavingMode", {"mode": mode}
        )

    async def set_text_form(self, text: str) -> bool:
        """Input text on the field of the software keyboard."""
        return await self.send_rest_quick(SERVICE_APP_CONTROL, "setTextForm", text)

    async def turn_on(self) -> bool:
        """Turn on the device."""
        await self.send_wol_req()
        if await self.get_power_status() != "active":
            with suppress(BraviaTVError):
                await self.set_power_status(True)
            with suppress(BraviaTVError):
                await self.send_ircc_req(CODE_POWER_ON)
        return True

    async def turn_off(self) -> bool:
        """Turn off the device."""
        return await self.set_power_status(False)

    async def volume_up(self, step: int = 1, **kwargs: str) -> bool:
        """Increase the volume."""
        level = f"+{step}"
        return await self.volume_level(level, **kwargs)

    async def volume_down(self, step: int = 1, **kwargs: str) -> bool:
        """Decrease the volume."""
        level = f"-{step}"
        return await self.volume_level(level, **kwargs)

    async def volume_level(
        self,
        level: int | str,
        target: str = DEFAULT_AUDIO_TARGET,
        ui_mode: str | None = None,
        version: str = DEFAULT_VERSION,
    ) -> bool:
        """Change the audio volume level."""
        params = {"target": target, "volume": str(level)}
        if ui_mode is not None:
            params["ui"] = ui_mode
        return await self.send_rest_quick(
            SERVICE_AUDIO, "setAudioVolume", params, version=version
        )

    async def volume_mute(self, mute: bool | None = None) -> bool:
        """Change the audio mute status."""
        if mute is None:
            volume_info = await self.get_volume_info()
            mute = not volume_info.get("mute")
        return await self.send_rest_quick(
            SERVICE_AUDIO, "setAudioMute", {"status": mute}
        )

    async def play(self) -> bool:
        """Send play command."""
        return await self.send_command("Play")

    async def pause(self) -> bool:
        """Send pause command."""
        return await self.send_command("Pause")

    async def stop(self) -> bool:
        """Send stop command."""
        return await self.send_command("Stop")

    async def next_track(self) -> bool:
        """Send next track command."""
        return await self.send_command("Next")

    async def previous_track(self) -> bool:
        """Send previous track command."""
        return await self.send_command("Prev")

    async def channel_up(self) -> bool:
        """Send next channel command."""
        return await self.send_command("ChannelUp")

    async def channel_down(self) -> bool:
        """Send previous channel command."""
        return await self.send_command("ChannelDown")

    async def terminate_apps(self) -> bool:
        """Terminate all opened applications."""
        return await self.send_rest_quick(SERVICE_APP_CONTROL, "terminateApps")

    async def reboot(self) -> bool:
        """Send command to reboot the device."""
        return await self.send_rest_quick(SERVICE_SYSTEM, "requestReboot")

    async def __aenter__(self) -> BraviaTV:
        """Connect the client with context manager."""
        return self

    async def __aexit__(
        self, exc_type: Exception, exc_value: str, traceback: TracebackType
    ) -> None:
        """Disconnect from context manager."""
        await self.disconnect()

import asyncio
import socket
from base64 import b64encode
from datetime import datetime, timedelta

import aiohttp


class BraviaTV:
    """Represent a Bravia TV client."""

    def __init__(self, host, mac=None, session=None):
        """Initialize the device."""
        self.host = host
        self.mac = mac
        self.connected = False
        self._wol = False
        self._psk = None
        self._send_ircc_time = None
        self._status = None
        self._session = session
        self._commands = {}

    async def connect(self, pin=None, psk=False, clientid=None, nickname=None):
        """Connect to device with PIN or PSK."""
        self.connected = False
        self._psk = pin[4:] if pin and pin[:4] == "psk:" else psk

        if self._psk:
            self.connected = True
        else:
            self.connected = await self.register(pin, clientid, nickname)

        if self.connected and self._wol is False:
            self.connected = await self.set_wol_mode(True)
            self._wol = True

        return self.connected

    async def register(self, pin, clientid, nickname):
        """Register the device with PIN."""
        b64pin = b64encode(f":{pin}".encode()).decode()
        headers = {"Authorization": f"Basic {b64pin}", "Connection": "keep-alive"}
        params = [
            {"clientid": clientid, "nickname": nickname, "level": "private"},
            [{"value": "yes", "function": "WOL"}],
        ]
        return await self.send_rest_quick(
            "accessControl", "actRegister", params, headers
        )

    async def pair(self, clientid=None, nickname=None):
        """Register with PIN "0000" to start the pairing process on the TV."""
        await self.register("0000", clientid, nickname)
        return self._status == 200 or self._status == 401

    async def disconnect(self):
        """Close connection."""
        self.connected = False
        if self._session:
            await self._session.close()

    async def send_wol_req(self):
        """Send WOL packet to device."""
        if self.mac is None:
            return False
        mac = self.mac.replace(":", "")
        packet = bytes.fromhex("F" * 12 + mac * 16)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, ("<broadcast>", 9))
        return True

    async def send_req(self, url, data, headers=None, timeout=10, format="json"):
        """Send HTTP request."""
        result = {} if format == "json" else False

        if not self._session:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )

        if not headers:
            headers = {}

        if self._psk:
            headers["X-Auth-PSK"] = self._psk

        try:
            if format == "json":
                response = await self._session.post(
                    url, json=data, headers=headers, timeout=timeout
                )
                if response.status == 200:
                    result = await response.json()
            else:
                response = await self._session.post(
                    url, data=data, headers=headers, timeout=timeout
                )
                if response.status == 200:
                    result = True
            self._status = response.status
        except aiohttp.ClientError:
            pass
        except asyncio.exceptions.TimeoutError:
            pass

        return result

    async def send_ircc_req(self, code, timeout=10):
        """Send IRCC request to device."""

        # After about 13 minutes of inactivity, some TV`s
        # ignores the first command without giving any error.
        # This make an empty request to 'wake up' the api.
        if code != "":
            time = datetime.now()
            if self._send_ircc_time is None or (
                time - self._send_ircc_time
            ) > timedelta(minutes=10):
                await self.send_ircc_req("")
            self._send_ircc_time = time

        url = f"http://{self.host}/sony/IRCC"
        headers = {"SOAPACTION": '"urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"'}
        data = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body><u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1">'
            "<IRCCCode>" + code + "</IRCCCode></u:X_SendIRCC></s:Body></s:Envelope>"
        ).encode("UTF-8")

        return await self.send_req(url, data, headers, timeout, "xml")

    async def send_rest_req(
        self, service, method, params=None, headers=None, timeout=10, version="1.0"
    ):
        """Send REST request to device."""
        url = f"http://{self.host}/sony/{service}"
        params = params if isinstance(params, list) else [params] if params else []
        data = {
            "method": method,
            "params": params,
            "id": 1,
            "version": version,
        }

        return await self.send_req(url, data, headers, timeout, "json")

    async def send_rest_quick(
        self, service, method, params=None, headers=None, timeout=10, version="1.0"
    ):
        """Send and quick check REST request to device."""
        resp = await self.send_rest_req(
            service, method, params, headers, timeout, version
        )
        return "result" in resp

    async def send_command(self, command):
        """Send IRCC command to device."""
        code = await self.get_command_code(command)
        if code is not None:
            return await self.send_ircc_req(code)
        return False

    async def get_power_status(self):
        """Get current power status: off, active, standby"""
        resp = await self.send_rest_req("system", "getPowerStatus", timeout=3)
        result = resp.get("result", [{"status": "off"}])[0]
        return result.get("status")

    async def get_system_info(self):
        """Get general information of the device."""
        resp = await self.send_rest_req("system", "getSystemInformation")
        result = resp.get("result", [{}])[0]
        self.mac = result.get("macAddr")
        return result

    async def get_api_info(self, services):
        """Get supported services and their information."""
        resp = await self.send_rest_req(
            "guide", "getSupportedApiInfo", {"services": services}
        )
        result = resp.get("result", [{}])[0]
        return result

    async def get_wol_mode(self):
        """Get information on the device's WOL mode settings."""
        resp = await self.send_rest_req("system", "getWolMode")
        result = resp.get("result", [{}])[0]
        return result.get("enabled")

    async def get_led_status(self):
        """Get the LED Indicator mode and status."""
        resp = await self.send_rest_req("system", "getLEDIndicatorStatus")
        result = resp.get("result", [{}])[0]
        return result

    async def get_command_list(self):
        """Get list of all IRCC commands."""
        resp = await self.send_rest_req("system", "getRemoteControllerInfo")
        result = resp.get("result", [{}, {}])[1]
        return {x["name"]: x["value"] for x in result}

    async def get_command_code(self, command):
        """Get IRCC command code by name."""
        if not self._commands:
            self._commands = await self.get_command_list()
        return self._commands.get(command)

    async def get_volume_info(self, target="speaker"):
        """Get information about the sound volume and mute status."""
        resp = await self.send_rest_req("audio", "getVolumeInformation")
        value = {}
        for output in resp.get("result", [{}])[0]:
            value = output
            if target in output.get("target"):
                break
        return value

    async def get_app_list(self):
        """Get list of applications."""
        resp = await self.send_rest_req("appControl", "getApplicationList")
        result = resp.get("result", [[]])[0]
        return result

    async def get_scheme_list(self):
        """Get list of schemes that the device can handle."""
        resp = await self.send_rest_req("avContent", "getSchemeList")
        result = resp.get("result", [[]])[0]
        return [d["scheme"] for d in result if "scheme" in d]

    async def get_source_list(self, scheme="extInput"):
        """Get list of sources in the scheme."""
        resp = await self.send_rest_req(
            "avContent", "getSourceList", {"scheme": scheme}
        )
        result = resp.get("result", [[]])[0]
        return [d["source"] for d in result if "source" in d]

    async def get_content_count(self, source):
        """Get count of contents in the source."""
        resp = await self.send_rest_req(
            "avContent", "getContentCount", {"source": source}
        )
        result = resp.get("result", [{}])[0]
        return result.get("count", 0)

    async def get_content_list(self, source, index=0, count=50):
        """Get list of contents in the source."""
        resp = await self.send_rest_req(
            "avContent",
            "getContentList",
            {"source": source, "stIdx": index, "cnt": count},
        )
        result = resp.get("result", [[]])[0]
        return result

    async def get_content_list_full(self, source):
        """Get full list of contents in the source."""
        result = []
        total = await self.get_content_count(source)
        for index in range(0, total, 50):
            count = min(50, total - index)
            resp = await self.get_content_list(source, index, count)
            result.extend(resp)
        return result

    async def get_content_list_all(self, scheme):
        """Get full list of contents in the scheme."""
        result = []
        sources = await self.get_source_list(scheme)
        for source in sources:
            resp = await self.get_content_list_full(source)
            result.extend(resp)
        return result

    async def get_external_status(self):
        """Get information of all external input sources."""
        resp = await self.send_rest_req("avContent", "getCurrentExternalInputsStatus")
        result = resp.get("result", [[]])[0]
        return result

    async def get_playing_info(self):
        """Get information of the currently playing content."""
        resp = await self.send_rest_req("avContent", "getPlayingContentInfo")
        result = resp.get("result", [{}])[0]
        return result

    async def set_wol_mode(self, mode):
        """Set WOL mode settings of the device."""
        return await self.send_rest_quick("system", "setWolMode", {"enabled": mode})

    async def set_led_status(self, mode, status=None):
        """Set the LED Indicator mode and status."""
        return await self.send_rest_quick(
            "system",
            "setLEDIndicatorStatus",
            {"mode": mode, "status": status},
            version="1.1",
        )

    async def set_active_app(self, uri):
        """Launch an application by URI."""
        return await self.send_rest_quick("appControl", "setActiveApp", {"uri": uri})

    async def set_play_content(self, uri):
        """Play content by URI."""
        return await self.send_rest_quick("avContent", "setPlayContent", {"uri": uri})

    async def turn_on(self):
        """Turn on the device."""
        await self.send_wol_req()
        if await self.get_power_status() != "active":
            await self.send_ircc_req("AAAAAQAAAAEAAAAuAw==")
            return await self.send_rest_quick(
                "system", "setPowerStatus", {"status": True}
            )
        else:
            return True

    async def turn_off(self):
        """Turn off the device."""
        return await self.send_rest_quick("system", "setPowerStatus", {"status": False})

    async def volume_up(self, target="speaker", step=1):
        """Increase the volume."""
        return await self.send_rest_quick(
            "audio", "setAudioVolume", {"target": target, "volume": f"+{step}"}
        )

    async def volume_down(self, target="speaker", step=1):
        """Decrease the volume."""
        return await self.send_rest_quick(
            "audio", "setAudioVolume", {"target": target, "volume": f"-{step}"}
        )

    async def volume_level(self, level, target="speaker"):
        """Change the audio volume level."""
        return await self.send_rest_quick(
            "audio", "setAudioVolume", {"target": target, "volume": str(level)}
        )

    async def volume_mute(self, mute=None):
        """Change the audio mute status."""
        if mute is None:
            volume_info = await self.get_volume_info()
            mute = not volume_info.get("mute")
        return await self.send_rest_quick("audio", "setAudioMute", {"status": mute})

    async def play(self):
        """Send play command."""
        return await self.send_command("Play")

    async def pause(self):
        """Send pause command."""
        return await self.send_command("Pause")

    async def stop(self):
        """Send stop command."""
        return await self.send_command("Stop")

    async def next_track(self):
        """Send next track command."""
        return await self.send_command("Next")

    async def previous_track(self):
        """Send previous track command."""
        return await self.send_command("Prev")

    async def channel_up(self):
        """Send next channel command."""
        return await self.send_command("ChannelUp")

    async def channel_down(self):
        """Send previous channel command."""
        return await self.send_command("ChannelDown")

    async def terminate_apps(self):
        """Terminate all opened applications."""
        return await self.send_rest_quick("appControl", "terminateApps")

    async def reboot(self):
        """Send command to reboot the device."""
        return await self.send_rest_quick("system", "requestReboot")

    async def __aenter__(self):
        """Connect to the transport."""
        return self

    async def __aexit__(self, *_exc_info):
        """Disconnect from the transport."""
        await self.disconnect()

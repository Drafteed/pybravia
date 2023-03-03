# pybravia

<a href="https://pypi.org/project/pybravia/"><img src="https://img.shields.io/pypi/v/pybravia" alt="PyPi release"></a> <img src="https://img.shields.io/github/actions/workflow/status/Drafteed/pybravia/ci.yml?branch=master" alt="GitHub Workflow Status"> <img src="https://img.shields.io/github/license/Drafteed/pybravia" alt="MIT License"> <img src="https://img.shields.io/badge/code%20style-black-black" alt="Code style">

Python Bravia provides an easy-to-use async interface for controlling of Sony Bravia TVs 2013 and newer.

This library primarily being developed with the intent of supporting [Home Assistant](https://www.home-assistant.io/integrations/braviatv/).

For more information, take a look at [BRAVIA Professional Display Knowledge Center](https://pro-bravia.sony.net/develop/).

## Requirements

This library supports Python 3.8 and higher.

## Installation

```sh
pip install pybravia
```

## Connect and API usage

### With PSK (recommended)

```py
import asyncio
import logging

from pybravia import BraviaClient, BraviaError

HOST = "192.168.1.20"
PSK = "sony"

logging.basicConfig(level=logging.DEBUG)


async def main():
    """Example of connect with PSK."""
    async with BraviaClient(HOST) as client:
        try:
            connected = await client.connect(psk=PSK)
            info = await client.get_system_info()

            print(info)

            await client.volume_up()
        except BraviaError:
            print("Could not connect")


loop = asyncio.new_event_loop()
loop.run_until_complete(main())
loop.close()
```

### With PIN code

#### Start pairing process and display PIN on the TV

```py
import asyncio
import logging

from pybravia import BraviaClient, BraviaError

HOST = "192.168.1.20"
CLIENTID = "MyClientID"
NICKNAME = "MyNicknameID"

logging.basicConfig(level=logging.DEBUG)


async def main():
    """Pairing process initialization example."""
    async with BraviaClient(HOST) as client:
        try:
            await client.pair(CLIENTID, NICKNAME)
        except BraviaError:
            print("Could not connect")


loop = asyncio.new_event_loop()
loop.run_until_complete(main())
loop.close()
```

#### Connect and usage

```py
import asyncio
import logging

from pybravia import BraviaClient, BraviaError

HOST = "192.168.1.20"
CLIENTID = "MyClientID"
NICKNAME = "MyNicknameID"
PIN = "2170"

logging.basicConfig(level=logging.DEBUG)


async def main():
    """Example of connect with PIN."""
    async with BraviaClient(HOST) as client:
        try:
            connected = await client.connect(PIN, CLIENTID, NICKNAME)
            info = await client.get_system_info()

            print(info)

            await client.volume_up()
        except BraviaError:
            print("Could not connect")


loop = asyncio.new_event_loop()
loop.run_until_complete(main())
loop.close()
```

## Contributing

See an issue? Have something to add? Issues and pull requests are accepted in this repository.

## License

This project is released under the MIT License. Refer to the LICENSE file for details.

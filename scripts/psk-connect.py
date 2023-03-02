from pybravia import BraviaClient, BraviaError
import asyncio
import os
import json

ip_address = os.getenv("IP_ADDRESS")
if ip_address is None:
    input('What is the IP address of the Bravia TV?\n')

psk = os.getenv("PSK")
if psk is None:
    input('What is the Pre-Shared Key?\n')

async def test():
    async with BraviaClient(ip_address) as client:
        try:
            connected = await client.connect(psk=psk)

            info = await client.get_picture_setting("brightness")

            print(json.dumps(info))

            await client.set_picture_setting("brightness", "50")
        except BraviaError:
            print("could not connect")
            raise BraviaError

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
    loop.close()

if __name__ == '__main__':
    main()
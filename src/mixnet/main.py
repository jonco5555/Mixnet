import asyncio
import os
from typing import List

import yaml

from mixnet.client import Client
from mixnet.models import Config
from mixnet.server import MixServer


async def main():
    config_path = "config/local-config.yaml"
    output_dir = "output"
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    config = Config(**data)

    servers: List[MixServer] = []
    for server in config.mix_servers:
        port = int(server.address.split(":")[1])
        servers.append(
            MixServer(
                server.id,
                port,
                config.messages_per_round,
                [client.address for client in config.clients],
                config_dir=os.path.dirname(config_path),
                output_dir=output_dir,
                round_duration=config.round_duration,
            )
        )

    # Start servers asynchronously
    await asyncio.gather(*(server.start() for server in servers))
    print("Servers started successfully")

    mix_addrs = []
    mix_pubkeys = []
    for server in config.mix_servers:
        mix_addrs.append(server.address)
        pubkey_path = os.path.join(os.path.dirname(config_path), f"{server.id}.key")
        with open(pubkey_path, "rb") as f:
            mix_pubkeys.append(f.read())

    clients: List[Client] = []
    for client in config.clients:
        port = int(client.address.split(":")[1])
        clients.append(
            Client(
                client.id,
                client.address,
                port,
                config_dir=os.path.dirname(config_path),
                mix_pubkeys=mix_pubkeys,
                mix_addrs=mix_addrs,
                dummy_payload=config.dummy_payload,
            )
        )

    client_1 = clients[0]
    client_2 = clients[1]

    client_1_pubkey_path = os.path.join(
        os.path.dirname(config_path), f"{client_1._id}.key"
    )
    with open(client_1_pubkey_path, "rb") as f:
        client_1_pubkey = f.read()
    client_2_pubkey_path = os.path.join(
        os.path.dirname(config_path), f"{client_2._id}.key"
    )
    with open(client_2_pubkey_path, "rb") as f:
        client_2_pubkey = f.read()

    await asyncio.gather(client_1.start(), client_2.start())
    await asyncio.sleep(1)

    await asyncio.gather(
        client_1._prepare_message(
            "Hello, client2!",
            client_2_pubkey,
            client_2._addr,
        ),
        client_2._prepare_message(
            "Hello, client1!",
            client_1_pubkey,
            client_1._addr,
        ),
    )
    await asyncio.sleep(3)
    await asyncio.gather(*(client.stop() for client in clients))
    await asyncio.sleep(1)
    messages = await asyncio.gather(
        client_1._poll_messages(config.mix_servers[2].address),
        client_2._poll_messages(config.mix_servers[2].address),
    )
    print(messages[0])
    print(messages[1])
    await asyncio.sleep(1)
    await asyncio.gather(*(server.stop() for server in servers))
    print("Servers and clients stopped successfully.")


if __name__ == "__main__":
    asyncio.run(main())

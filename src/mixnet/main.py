import asyncio
import os
from typing import List

import yaml

from mixnet.client import Client
from mixnet.models import Config
from mixnet.server import MixServer


async def main():
    config_path = "config/config.yaml"
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
                [client.id for client in config.clients],
                config_dir=os.path.dirname(config_path),
                output_dir=output_dir,
            )
        )

    # Start servers asynchronously
    await asyncio.gather(*(server.start() for server in servers))
    print("Servers started successfully")

    clients: List[Client] = []
    for client in config.clients:
        clients.append(
            Client(
                client.id,
                config_dir=os.path.dirname(config_path),
            )
        )

    client_1 = clients[0]
    client_1_id = config.clients[0].id
    client_2 = clients[1]
    client_2_id = config.clients[1].id

    client_1_pubkey_path = os.path.join(
        os.path.dirname(config_path), f"{client_1_id}.key"
    )
    with open(client_1_pubkey_path, "rb") as f:
        client_1_pubkey = f.read()
    client_2_pubkey_path = os.path.join(
        os.path.dirname(config_path), f"{client_2_id}.key"
    )
    with open(client_2_pubkey_path, "rb") as f:
        client_2_pubkey = f.read()
    mix_addrs = []
    mix_pubkeys = []
    for server in config.mix_servers:
        mix_addrs.append(server.address)
        pubkey_path = os.path.join(os.path.dirname(config_path), f"{server.id}.key")
        with open(pubkey_path, "rb") as f:
            mix_pubkeys.append(f.read())

    await asyncio.gather(
        client_1.prepare_message(
            "Hello, client2!",
            client_2_pubkey,
            client_2_id,
            mix_pubkeys,
            mix_addrs,
            0,
        ),
        client_2.prepare_message(
            "Hello, client1!",
            client_1_pubkey,
            client_1_id,
            mix_pubkeys,
            mix_addrs,
            0,
        ),
    )
    await asyncio.sleep(1)
    messages = await asyncio.gather(
        client_1.poll_messages(config.mix_servers[0].address),
        client_2.poll_messages(config.mix_servers[0].address),
    )
    print(messages[0])
    print(messages[1])
    await asyncio.gather(*(server.stop() for server in servers))
    print("Servers started and stopped successfully.")


if __name__ == "__main__":
    asyncio.run(main())

    # s1 = MixServer("server1", 50051, 2, ["localhost:50055", "localhost:50054"])
    # s2 = MixServer("server2", 50052, 2, ["localhost:50055", "localhost:50054"])
    # s3 = MixServer("server3", 50053, 2, ["localhost:50055", "localhost:50054"])
    # c1 = Client("client1", 50055)
    # c2 = Client("client2", 50054)
    # s1.start()
    # s2.start()
    # s3.start()
    # c1.prepare_message(
    #     "Hello, client2!",
    #     "localhost:50054",
    #     ["localhost:50051", "localhost:50052", "localhost:50053"],
    #     0,
    # )
    # c2.prepare_message(
    #     "Hello, client1!",
    #     "localhost:50055",
    #     ["localhost:50051", "localhost:50052", "localhost:50053"],
    #     0,
    # )
    # time.sleep(1)
    # print(c1.poll_messages("localhost:50051"))
    # print(c2.poll_messages("localhost:50051"))
    # s1.stop()
    # s2.stop()
    # s3.stop()
    # print("Finished")

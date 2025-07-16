import asyncio
import os
import time
from typing import List

import matplotlib.pyplot as plt
import pandas as pd

from mixnet.client import Client
from mixnet.models import Client as ClientConfig
from mixnet.models import Config, Server
from mixnet.server import MixServer


def generate_config(num_clients: int, message_size: int = 10) -> Config:
    num_mix_servers = 3
    dummy_payload = message_size * "x"

    mix_servers = [
        Server(id=f"server_{i + 1}", address=f"localhost:{50051 + i}")
        for i in range(num_mix_servers)
    ]
    clients = [
        ClientConfig(id=f"client_{i + 1}", address=f"localhost:{50101 + i}")
        for i in range(num_clients)
    ]

    return Config(
        mix_servers=mix_servers,
        clients=clients,
        messages_per_round=num_clients,
        dummy_payload=dummy_payload,
        round_duration=0.1,
    )


async def main():
    results = []
    num_clients_list = list(range(2, 11))
    message_sizes = [10, 100, 1000, 10000, 100000, 1000000]
    for num_clients in num_clients_list:
        for message_size in message_sizes:
            print(f"Testing with {num_clients} clients and message size {message_size}")
            E2E_time, prepare_time, mix_latency = await test(num_clients, message_size)
            results.append(
                {
                    "num_clients": num_clients,
                    "message_size": message_size,
                    "E2E_time": E2E_time,
                    "prepare_time": prepare_time,
                    "mix_latency": mix_latency,
                }
            )

    df = pd.DataFrame(results)

    # Plot metrics vs num_clients for each message size
    plt.figure(figsize=(15, 5))
    for metric in ["E2E_time", "prepare_time", "mix_latency"]:
        plt.subplot(1, 3, ["E2E_time", "prepare_time", "mix_latency"].index(metric) + 1)
        for message_size in message_sizes:
            subset = df[df["message_size"] == message_size]
            plt.plot(
                subset["num_clients"], subset[metric], label=f"msg_size={message_size}"
            )
        plt.xlabel("Number of Clients")
        plt.ylabel(f"{metric} (s)")
        plt.title(f"{metric} (s) vs Number of Clients")
        plt.legend()
    plt.tight_layout()
    plt.show()

    # Plot metrics vs message_size for each num_clients (logarithmic x-axis)
    plt.figure(figsize=(15, 5))
    for metric in ["E2E_time", "prepare_time", "mix_latency"]:
        plt.subplot(1, 3, ["E2E_time", "prepare_time", "mix_latency"].index(metric) + 1)
        for num_clients in num_clients_list:
            subset = df[df["num_clients"] == num_clients]
            plt.plot(
                subset["message_size"], subset[metric], label=f"clients={num_clients}"
            )
        plt.xlabel("Message Size")
        plt.xscale("log")
        plt.ylabel(f"{metric} (s)")
        plt.title(f"{metric} (s) vs Message Size (log scale)")
        plt.legend()
    plt.tight_layout()
    plt.show()


async def test(num_clients: int, message_size: int):
    config = generate_config(num_clients=num_clients, message_size=message_size)
    config_dir = "config"
    output_dir = "output"
    metrics = {}

    # Create servers
    servers: List[MixServer] = []
    for server in config.mix_servers:
        port = int(server.address.split(":")[1])
        servers.append(
            MixServer(
                server.id,
                port,
                config.messages_per_round,
                [client.address for client in config.clients],
                config_dir=config_dir,
                output_dir=output_dir,
                round_duration=config.round_duration,
                enable_metrics=True,
                metrics=metrics,
            )
        )
        metrics[server.id] = {}
    # Start servers asynchronously
    await asyncio.gather(*(server.start() for server in servers))
    print("Servers started successfully")

    # Collect mix addresses and public keys
    mix_addrs = []
    mix_pubkeys = []
    for server in config.mix_servers:
        mix_addrs.append(server.address)
        pubkey_path = os.path.join(config_dir, f"{server.id}.key")
        with open(pubkey_path, "rb") as f:
            mix_pubkeys.append(f.read())

    # Create clients
    clients: List[Client] = []
    for client in config.clients:
        port = int(client.address.split(":")[1])
        clients.append(
            Client(
                client.id,
                client.address,
                port,
                config_dir=config_dir,
                mix_pubkeys=mix_pubkeys,
                mix_addrs=mix_addrs,
                dummy_payload=config.dummy_payload,
                enable_metrics=True,
                metrics=metrics,
            )
        )
        metrics[client.id] = {}
    await asyncio.gather(*(client.start() for client in clients))

    # get two clients
    client_1 = clients[0]
    client_2 = clients[1]
    client_2_pubkey_path = os.path.join(config_dir, f"{client_2._id}.key")
    with open(client_2_pubkey_path, "rb") as f:
        client_2_pubkey = f.read()

    start_time = time.perf_counter_ns()
    await client_1._prepare_message(
        message_size * "y",
        client_2_pubkey,
        client_2._addr,
    )
    messages = []
    while not messages:
        await asyncio.sleep(0.1)
        messages = await client_2._poll_messages(config.mix_servers[2].address)
    end_time = time.perf_counter_ns()
    await asyncio.gather(*(client.stop() for client in clients))
    await asyncio.sleep(1)
    await asyncio.gather(*(server.stop() for server in servers))
    print("Servers and clients stopped successfully.")
    E2E_time = (end_time - start_time) / 1_000_000_000
    prepare_time = (
        metrics[client_1._id]["prepare_end_time"]
        - metrics[client_1._id]["prepare_start_time"]
    ) / 1_000_000_000
    mix_latency = (
        metrics[servers[2]._id]["round_end_time"]
        - metrics[servers[0]._id]["round_start_time"]
    ) / 1_000_000_000
    print(f"{E2E_time=}, {prepare_time=}, {mix_latency=}")
    return E2E_time, prepare_time, mix_latency


if __name__ == "__main__":
    asyncio.run(main())

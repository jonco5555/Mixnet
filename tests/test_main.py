import asyncio
import os

import pytest
import pytest_asyncio
import yaml

from mixnet.client import Client
from mixnet.models import Config
from mixnet.server import MixServer


@pytest.fixture
def config(tmp_path_factory):
    # Create a minimal config.yaml and dummy key files in a temp dir
    temp_dir = tmp_path_factory.mktemp("test_config")
    temp_config_dir = os.path.join(temp_dir, "config")
    temp_output_dir = os.path.join(temp_dir, "output")
    os.makedirs(temp_config_dir, exist_ok=True)
    os.makedirs(temp_output_dir, exist_ok=True)
    # Example config data (adjust as needed for your schema)
    config_data = {
        "mix_servers": [
            {"id": "server_1", "address": "localhost:50051"},
            {"id": "server_2", "address": "localhost:50052"},
            {"id": "server_3", "address": "localhost:50053"},
        ],
        "clients": [
            {"id": "client_1", "address": "localhost:50061"},
            {"id": "client_2", "address": "localhost:50062"},
        ],
        "messages_per_round": 2,
        "round_duration": 1,
        "dummy_payload": "dummy",
    }
    config_path = os.path.join(temp_config_dir, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f)
    # Create dummy key files for servers and clients
    for server in config_data["mix_servers"]:
        with open(os.path.join(temp_config_dir, f"{server['id']}.key"), "wb") as f:
            f.write(b"dummy_server_key")
    for client in config_data["clients"]:
        with open(os.path.join(temp_config_dir, f"{client['id']}.key"), "wb") as f:
            f.write(b"dummy_client_key")
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cfg = Config(**data)
    cfg._temp_config_dir = temp_config_dir  # Attach for later use
    cfg._temp_output_dir = temp_output_dir  # Attach for later use
    return cfg


@pytest_asyncio.fixture
async def servers_setup(config: Config):
    servers = []
    mix_addrs = []
    mix_pubkeys = []
    for server_config in config.mix_servers:
        port = int(server_config.address.split(":")[1])
        server = MixServer(
            server_config.id,
            port,
            config.messages_per_round,
            [client.address for client in config.clients],
            config_dir=config._temp_config_dir,
            output_dir=config._temp_output_dir,
            round_duration=config.round_duration,
        )
        servers.append(server)
        mix_addrs.append(server_config.address)
        mix_pubkeys.append(server._pubkey_b64)
    await asyncio.gather(*(server.start() for server in servers))
    yield mix_addrs, mix_pubkeys
    await asyncio.gather(*(server.stop() for server in servers))


@pytest_asyncio.fixture
async def clients_setup(config: Config, servers_setup):
    mix_addrs, mix_pubkeys = servers_setup
    clients = []
    clients_addrs = []
    clients_pubkeys = []
    for client_config in config.clients:
        port = int(client_config.address.split(":")[1])
        client = Client(
            client_config.id,
            client_config.address,
            port,
            config_dir=config._temp_config_dir,
            mix_pubkeys=mix_pubkeys,
            mix_addrs=mix_addrs,
            dummy_payload=config.dummy_payload,
        )
        clients.append(client)
        clients_addrs.append(client_config.address)
        clients_pubkeys.append(client._pubkey_b64)
    await asyncio.gather(*(client.start() for client in clients))
    yield clients, clients_addrs, clients_pubkeys


@pytest.mark.asyncio
async def test_message_exchange(clients_setup, config):
    clients, clients_addrs, clients_pubkeys = clients_setup
    client_1 = clients[0]
    client_1_addr = clients_addrs[0]
    client_1_pubkey = clients_pubkeys[0]
    client_2 = clients[1]
    client_2_addr = clients_addrs[1]
    client_2_pubkey = clients_pubkeys[1]

    await asyncio.gather(
        client_1._prepare_message("Hello, client2!", client_2_pubkey, client_2_addr),
        client_2._prepare_message("Hello, client1!", client_1_pubkey, client_1_addr),
    )
    await asyncio.sleep(1)
    await asyncio.gather(*(client.stop() for client in clients))
    await asyncio.sleep(1)
    messages = await asyncio.gather(
        client_1._poll_messages(config.mix_servers[2].address),
        client_2._poll_messages(config.mix_servers[2].address),
    )
    assert "Hello, client2!" in messages[1]
    assert "Hello, client1!" in messages[0]

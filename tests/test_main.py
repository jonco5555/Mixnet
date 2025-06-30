import os
import time

import pytest
import yaml

from mixnet.client import Client
from mixnet.models import Config
from mixnet.server import MixServer


@pytest.fixture
def config(tmp_path_factory):
    # Create a minimal config.yaml and dummy key files in a temp dir
    temp_dir = tmp_path_factory.mktemp("test_config")
    temp_config_dir = os.path.join(temp_dir, "config")
    os.makedirs(temp_config_dir, exist_ok=True)
    # Example config data (adjust as needed for your schema)
    config_data = {
        "mix_servers": [
            {"id": "server_1", "address": "localhost:50051"},
            {"id": "server_2", "address": "localhost:50052"},
            {"id": "server_3", "address": "localhost:50053"},
        ],
        "clients": [
            {"id": "client_1"},
            {"id": "client_2"},
        ],
        "messages_per_round": 2,
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
    return cfg


@pytest.fixture
def servers(config):
    servers = []
    for server in config.mix_servers:
        port = int(server.address.split(":")[1])
        servers.append(
            MixServer(
                server.id,
                port,
                config.messages_per_round,
                [client.id for client in config.clients],
                config_dir=config._temp_config_dir,
            )
        )
    yield servers
    for server in servers:
        server.stop()


@pytest.fixture
def clients(config):
    clients = []
    for client in config.clients:
        clients.append(
            Client(
                client.id,
                config_dir=config._temp_config_dir,
            )
        )
    return clients


def test_message_exchange(servers, clients, config):
    [server.start() for server in servers]
    client_1 = clients[0]
    client_1_id = config.clients[0].id
    client_2 = clients[1]
    client_2_id = config.clients[1].id

    client_1_pubkey_path = os.path.join(config._temp_config_dir, f"{client_1_id}.key")
    with open(client_1_pubkey_path, "rb") as f:
        client_1_pubkey = f.read()
    client_2_pubkey_path = os.path.join(config._temp_config_dir, f"{client_2_id}.key")
    with open(client_2_pubkey_path, "rb") as f:
        client_2_pubkey = f.read()
    mix_addrs = []
    mix_pubkeys = []
    for server in config.mix_servers:
        mix_addrs.append(server.address)
        pubkey_path = os.path.join(config._temp_config_dir, f"{server.id}.key")
        with open(pubkey_path, "rb") as f:
            mix_pubkeys.append(f.read())

    client_1.prepare_message(
        "Hello, client2!",
        client_2_pubkey,
        client_2_id,
        mix_pubkeys,
        mix_addrs,
        0,
    )
    client_2.prepare_message(
        "Hello, client1!",
        client_1_pubkey,
        client_1_id,
        mix_pubkeys,
        mix_addrs,
        0,
    )
    time.sleep(1)
    msg1 = client_1.poll_messages(config.mix_servers[0].address)
    msg2 = client_2.poll_messages(config.mix_servers[0].address)
    assert "Hello, client2!" in str(msg2) or "Hello, client2!" in str(msg1)
    assert "Hello, client1!" in str(msg1) or "Hello, client1!" in str(msg2)

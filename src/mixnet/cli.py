import asyncio
import os
import signal

import typer
import yaml
from typing_extensions import Annotated

from mixnet.client import Client
from mixnet.models import Config
from mixnet.server import MixServer

app = typer.Typer()


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Config(**data)


async def start_peer(peer: MixServer | Client):
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        print(f"Received stop signal. Shutting down server {server._id}")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Signal are not be available on Windows

    await peer.start()
    print(f"{peer.__class__.__name__} {peer._id} started successfully")
    try:
        await stop_event.wait()
    except Exception as e:
        print(f"Error during server operation: {e}")
    finally:
        await peer.stop()


@app.command()
def server(
    id: Annotated[str, typer.Option(help="Server ID")],
    config_path: Annotated[str, typer.Option("--config", help="Path to config file")],
    output_dir: Annotated[
        str, typer.Option(help="Output directory for last server logs")
    ],
):
    config = load_config(config_path)
    server_config = next((s for s in config.mix_servers if s.id == id), None)
    if not server_config:
        typer.echo(f"Server with id '{id}' not found in config.")
        raise typer.Exit(code=1)
    server = MixServer(
        id,
        int(server_config.address.split(":")[1]),
        config.messages_per_round,
        [client.id for client in config.clients],
        config_dir=os.path.dirname(config_path),
        output_dir=output_dir,
    )
    asyncio.run(start_peer(server))


def servers_data(config_path: str, config: Config):
    mix_addrs = []
    mix_pubkeys = []
    for server in config.mix_servers:
        mix_addrs.append(server.address)
        pubkey_path = os.path.join(os.path.dirname(config_path), f"{server.id}.key")
        with open(pubkey_path, "rb") as f:
            mix_pubkeys.append(f.read())
    return mix_addrs, mix_pubkeys


@app.command()
def client(
    id: Annotated[str, typer.Option(help="Client ID")],
    config_path: Annotated[str, typer.Option("--config", help="Path to config file")],
):
    config = load_config(config_path)
    client_config = next((c for c in config.clients if c.id == id), None)
    if not client_config:
        typer.echo(f"Client with id '{id}' not found in config.")
        raise typer.Exit(code=1)
    mix_addrs, mix_pubkeys = servers_data(config_path, config)
    client = Client(
        client_config.id,
        config_dir=os.path.dirname(config_path),
        mix_pubkeys=mix_pubkeys,
        mix_addrs=mix_addrs,
    )
    asyncio.run(start_peer(client))


if __name__ == "__main__":
    app()

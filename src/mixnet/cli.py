import asyncio
import logging
import os
import signal
import time

import grpc
import typer
import yaml
from typing_extensions import Annotated

import mixnet.mixnet_pb2 as pb2
from mixnet.client import Client
from mixnet.mixnet_pb2_grpc import ClientStub
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
        logging.warning("Received stop signal. Shutting down server")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Signal are not be available on Windows

    await peer.start()
    try:
        await stop_event.wait()
    except Exception as e:
        logging.exception(f"Error during server operation: {e}")
    finally:
        await peer.stop()


@app.command()
def server(
    id: Annotated[str, typer.Option(envvar="SERVER_ID", help="Server ID")],
    config_path: Annotated[
        str, typer.Option("--config", envvar="CONFIG_PATH", help="Path to config file")
    ],
    output_dir: Annotated[
        str,
        typer.Option(envvar="OUTPUT_DIR", help="Output directory for last server logs"),
    ],
):
    config = load_config(config_path)
    server_config = next((s for s in config.mix_servers if s.id == id), None)
    if not server_config:
        typer.echo(f"Server with id '{id}' not found in config.")
        raise typer.Exit(code=1)
    # Use round_duration from config if present, else fallback to CLI arg
    round_duration = config.round_duration
    server = MixServer(
        id=id,
        port=int(server_config.address.split(":")[1]),
        messages_per_round=config.messages_per_round,
        clients_addrs=[client.address for client in config.clients],
        config_dir=os.path.dirname(config_path),
        output_dir=output_dir,
        round_duration=round_duration,
    )
    asyncio.run(start_peer(server))


def servers_data(config_path: str, config: Config):
    mix_addrs = []
    mix_pubkeys = []

    for server in config.mix_servers:
        mix_addrs.append(server.address)
        pubkey_path = os.path.join(os.path.dirname(config_path), f"{server.id}.key")
        for attempt in range(5):
            if os.path.exists(pubkey_path):
                with open(pubkey_path, "rb") as f:
                    mix_pubkeys.append(f.read())
                break
            else:
                time.sleep(1)
        else:
            raise FileNotFoundError(
                f"Public key file not found after 5 attempts: {pubkey_path}"
            )
    return mix_addrs, mix_pubkeys


@app.command()
def client(
    id: Annotated[str, typer.Option(envvar="CLIENT_ID", help="Client ID")],
    config_path: Annotated[
        str, typer.Option("--config", envvar="CONFIG_PATH", help="Path to config file")
    ],
):
    config = load_config(config_path)
    client_config = next((c for c in config.clients if c.id == id), None)
    if not client_config:
        typer.echo(f"Client with id '{id}' not found in config.")
        raise typer.Exit(code=1)
    mix_addrs, mix_pubkeys = servers_data(config_path, config)
    client = Client(
        id=client_config.id,
        addr=client_config.address,
        port=int(client_config.address.split(":")[1]),
        config_dir=os.path.dirname(config_path),
        mix_pubkeys=mix_pubkeys,
        mix_addrs=mix_addrs,
        dummy_payload=config.dummy_payload,
    )
    asyncio.run(start_peer(client))


async def call_client_prepare_message(sender: Client, request):
    async with grpc.aio.insecure_channel(sender.address) as channel:
        stub = ClientStub(channel)
        return await stub.PrepareMessage(request)


@app.command()
def prepare_message(
    message: Annotated[str, typer.Option(help="Message to send")],
    sender_id: Annotated[
        str, typer.Option(envvar="CLIENT_ID", help="Sender client ID")
    ],
    recipient_id: Annotated[str, typer.Option(help="Recipient client ID")],
    config_path: Annotated[
        str, typer.Option("--config", envvar="CONFIG_PATH", help="Path to config file")
    ],
):
    config = load_config(config_path)
    recipient = next((c for c in config.clients if c.id == recipient_id), None)
    sender = next((c for c in config.clients if c.id == sender_id), None)
    if not recipient:
        typer.echo(f"Recipient client with id '{recipient_id}' not found in config.")
        raise typer.Exit(code=1)

    pubkey_path = os.path.join(os.path.dirname(config_path), f"{recipient_id}.key")
    try:
        with open(pubkey_path, "rb") as f:
            recipient_pubkey = f.read()
    except FileNotFoundError:
        typer.echo(
            f"Public key for recipient '{recipient_id}' not found at {pubkey_path}."
        )
        raise typer.Exit(code=1)

    # Prepare gRPC request
    request = pb2.PrepareMessageRequest(
        message=message,
        recipient_pubkey=recipient_pubkey,
        recipient_addr=recipient.address,
    )
    try:
        response = asyncio.run(call_client_prepare_message(sender, request))
        if response.status:
            typer.echo("Message prepared successfully.")
        else:
            typer.echo("Failed to prepare message.")
    except Exception as e:
        typer.echo(f"Failed to send message: {e}")


async def call_client_poll_messages(client: Client, request):
    async with grpc.aio.insecure_channel(client.address) as channel:
        stub = ClientStub(channel)
        return await stub.PollMessages(request)


@app.command()
def poll_messages(
    client_id: Annotated[
        str, typer.Option(envvar="CLIENT_ID", help="Client ID to poll messages for")
    ],
    config_path: Annotated[
        str, typer.Option("--config", envvar="CONFIG_PATH", help="Path to config file")
    ],
):
    config = load_config(config_path)
    client = next((c for c in config.clients if c.id == client_id), None)
    if not client:
        typer.echo(f"Client with id '{client_id}' not found in config.")
        raise typer.Exit(code=1)

    # Prepare gRPC request
    request = pb2.ClientPollMessagesRequest()
    try:
        response = asyncio.run(call_client_poll_messages(client, request))
        typer.echo(f"Polled message: {response.messages}")
    except Exception as e:
        typer.echo(f"Failed to send message: {e}")


if __name__ == "__main__":
    app()

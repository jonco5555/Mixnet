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


@app.command()
async def server(
    config: Annotated[str, typer.Argument(help="Path to config file")],
    id: Annotated[str, typer.Argument(help="Server ID")],
):
    """Run as server using the given config file and server id."""
    config_obj = load_config(config)
    server_entity = next((s for s in config_obj.mix_servers if s.id == id), None)
    if not server_entity:
        typer.echo(f"Server with id '{id}' not found in config.")
        raise typer.Exit(code=1)
    client_addresses = [f"{c.ip}:{c.port}" for c in config_obj.clients]
    s = MixServer(
        server_entity.id,
        server_entity.port,
        config_obj.messages_per_round,
        client_addresses,
    )
    s.start()
    typer.echo(f"Server '{id}' started. Press Ctrl+C to stop.")
    try:
        while True:
            pass
    except KeyboardInterrupt:
        s.stop()
        typer.echo(f"Server '{id}' stopped.")


@app.command()
def client(config: str, client_id: str):
    """Run as client using the given config file and client id."""
    config_obj = load_config(config)
    client_entity = next((c for c in config_obj.clients if c.id == client_id), None)
    if not client_entity:
        typer.echo(f"Client with id '{client_id}' not found in config.")
        raise typer.Exit(code=1)
    _ = Client(client_entity.id, client_entity.port)
    typer.echo(
        f"Client '{client_id}' ready. Implement message sending logic as needed."
    )


if __name__ == "__main__":
    app()

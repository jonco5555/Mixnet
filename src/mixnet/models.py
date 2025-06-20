from typing import List

from pydantic import BaseModel


class Message(BaseModel):
    payload: bytes
    address: str


class Entity(BaseModel):
    id: str
    ip: str
    port: int
    private_key_path: str
    public_key_path: str


class Config(BaseModel):
    messages_per_round: int
    mix_servers: List[Entity]
    clients: List[Entity]

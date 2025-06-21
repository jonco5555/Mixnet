import base64
from typing import List

from pydantic import BaseModel, field_serializer


class Message(BaseModel):
    payload: bytes
    address: str

    # @field_validator("payload", mode="before")
    # def decode_base64(cls, v):
    #     return base64.b64decode(v)

    @field_serializer("payload")
    def encode_base64(self, v: bytes, _info):
        return base64.b64encode(v).decode()


class Server(BaseModel):
    id: str
    address: str


class Client(BaseModel):
    id: str


class Entity(BaseModel):
    id: str
    ip: str
    port: int
    private_key: str
    public_key: str


class Config(BaseModel):
    messages_per_round: int
    mix_servers: List[Server]
    clients: List[Client]

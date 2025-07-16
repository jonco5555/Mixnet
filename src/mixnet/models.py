import base64
from typing import List

from pydantic import BaseModel, field_serializer, field_validator


class Message(BaseModel):
    payload: bytes
    address: str

    @field_validator("payload", mode="before")
    def decode_base64(cls, v):
        if isinstance(v, str):
            return base64.b64decode(v)
        return v

    @field_serializer("payload")
    def encode_base64(self, v: bytes, _info):
        return base64.b64encode(v).decode()


class Server(BaseModel):
    id: str
    address: str


class Client(BaseModel):
    id: str
    address: str


class Config(BaseModel):
    messages_per_round: int
    round_duration: int = 1
    dummy_payload: str = "dummy"
    mix_servers: List[Server]
    clients: List[Client]

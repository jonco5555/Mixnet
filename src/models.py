from pydantic import BaseModel


class Message(BaseModel):
    payload: bytes
    address: str

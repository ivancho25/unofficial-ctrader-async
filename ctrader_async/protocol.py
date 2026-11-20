import asyncio
import struct
from ctrader_async.proto import OpenApiCommonMessages_pb2 as common

HEADER_SIZE = 4

async def read_message(reader: asyncio.StreamReader) -> bytes:
    header = await reader.readexactly(HEADER_SIZE)
    length = struct.unpack('>I', header)[0]
    return await reader.readexactly(length)

async def write_message(writer: asyncio.StreamWriter, envelope: common.ProtoMessage) -> None:
    data = envelope.SerializeToString()
    writer.write(struct.pack('>I', len(data)) + data)
    await writer.drain()

def wrap(payload_type: int, payload_bytes: bytes) -> common.ProtoMessage:
    envelope = common.ProtoMessage()
    envelope.payloadType = payload_type
    envelope.payload = payload_bytes
    return envelope

def unwrap(data: bytes) -> common.ProtoMessage:
    envelope = common.ProtoMessage()
    envelope.ParseFromString(data)
    return envelope

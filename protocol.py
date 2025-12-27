from __future__ import annotations

import json
import struct
import socket
from dataclasses import dataclass
from typing import Any, Dict, Optional

from config import HEADER_TYPE_BYTES, HEADER_LEN_BYTES, MAX_PAYLOAD, ENCODING

# Simple app-level message types
MSG_HELLO = 0x01
MSG_TEXT  = 0x02
MSG_DM_TEXT = 0x03
MSG_ERROR = 0x7F
MSG_CONTACT_ADD = 0x10
MSG_CONTACT_REMOVE = 0x11
MSG_CONTACT_LIST = 0x12
MSG_FILE_META = 0x20
MSG_FILE_CHUNK = 0x21
MSG_FILE_DONE = 0x22



@dataclass
class Message:
    mtype: int
    payload: bytes

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes or raise ConnectionError."""
    chunks = []
    received = 0
    while received < n:
        chunk = sock.recv(n - received)
        if not chunk:
            raise ConnectionError("Socket closed while receiving data.")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)

def send_message(sock: socket.socket, mtype: int, payload: bytes) -> None:
    if not (0 <= mtype <= 255):
        raise ValueError("mtype must be 0..255")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"Payload too large: {len(payload)} > {MAX_PAYLOAD}")

    header = struct.pack("!BI", mtype, len(payload))  # 1 byte type, 4 byte length
    sock.sendall(header + payload)

def recv_message(sock: socket.socket) -> Message:
    header = _recv_exact(sock, HEADER_TYPE_BYTES + HEADER_LEN_BYTES)
    mtype, length = struct.unpack("!BI", header)

    if length > MAX_PAYLOAD:
        raise ValueError(f"Incoming payload too large: {length} > {MAX_PAYLOAD}")

    payload = _recv_exact(sock, length) if length else b""
    return Message(mtype=mtype, payload=payload)

def send_json(sock: socket.socket, mtype: int, obj: Dict[str, Any]) -> None:
    payload = json.dumps(obj, ensure_ascii=False).encode(ENCODING)
    send_message(sock, mtype, payload)

def recv_json(sock: socket.socket) -> Dict[str, Any]:
    msg = recv_message(sock)
    try:
        obj = json.loads(msg.payload.decode(ENCODING))
    except Exception as e:
        raise ValueError(f"Invalid JSON payload: {e}") from e
    obj["_mtype"] = msg.mtype
    return obj

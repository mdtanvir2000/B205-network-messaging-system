from __future__ import annotations

import base64
import os
import socket
import threading
import uuid
from typing import Dict, Any

from config import HOST, PORT
from logger import make_logger
from protocol import (
    send_json,
    recv_json,
    MSG_HELLO,
    MSG_TEXT,
    MSG_DM_TEXT,
    MSG_CONTACT_ADD,
    MSG_CONTACT_REMOVE,
    MSG_CONTACT_LIST,
    MSG_FILE_META,
    MSG_FILE_CHUNK,
    MSG_FILE_DONE,
)

log = make_logger("client")

DOWNLOAD_DIR = "downloads"
CHUNK_SIZE = 64 * 1024  # 64KB chunks

# Tracks incoming transfers by file_id
incoming_files: Dict[str, Dict[str, Any]] = {}


def listener(sock: socket.socket) -> None:
    try:
        while True:
            msg = recv_json(sock)
            mtype = msg.get("_mtype")

            if mtype == MSG_TEXT:
                print(f"\n[{msg.get('from', '?')}] {msg.get('text', '')}")

            elif mtype == MSG_FILE_META:
                # msg: {"from","file_id","filename","size"}
                file_id = str(msg.get("file_id", "")).strip()
                filename = str(msg.get("filename", "")).strip()
                size = int(msg.get("size", 0))
                sender = str(msg.get("from", "?"))

                if not file_id or not filename or size <= 0:
                    print(f"\n[file] Invalid FILE_META received: {msg}")
                    continue

                os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                save_path = os.path.join(DOWNLOAD_DIR, f"{file_id}_{filename}")

                try:
                    fh = open(save_path, "wb")
                except Exception as e:
                    print(f"\n[file] Could not open file for writing: {save_path}. Error: {e}")
                    continue

                incoming_files[file_id] = {
                    "path": save_path,
                    "expected": size,
                    "received": 0,
                    "fh": fh,
                    "from": sender,
                    "filename": filename,
                }

                print(f"\n[file] Incoming from {sender}: {filename} ({size} bytes)")
                print(f"[file] Saving to: {save_path}")

            elif mtype == MSG_FILE_CHUNK:
                # msg: {"from","file_id","chunk_b64"}
                file_id = str(msg.get("file_id", "")).strip()
                chunk_b64 = str(msg.get("chunk_b64", ""))

                info = incoming_files.get(file_id)
                if not info:
                    print(f"\n[file] Received chunk for unknown file_id={file_id}")
                    continue

                try:
                    data = base64.b64decode(chunk_b64.encode("ascii"))
                except Exception as e:
                    print(f"\n[file] Base64 decode error for file_id={file_id}: {e}")
                    continue

                try:
                    info["fh"].write(data)
                    info["received"] += len(data)
                except Exception as e:
                    print(f"\n[file] Write error for file_id={file_id}: {e}")
                    continue

            elif mtype == MSG_FILE_DONE:
                # msg: {"from","file_id"}
                file_id = str(msg.get("file_id", "")).strip()

                info = incoming_files.get(file_id)
                if not info:
                    print(f"\n[file] DONE for unknown file_id={file_id}")
                    continue

                try:
                    info["fh"].close()
                except Exception:
                    pass

                sender = info.get("from", "?")
                filename = info.get("filename", "?")
                rec = int(info.get("received", 0))
                exp = int(info.get("expected", 0))
                path = info.get("path", "")

                incoming_files.pop(file_id, None)

                print(f"\n[file] Completed from {sender}: {filename} ({rec}/{exp} bytes)")
                print(f"[file] Saved at: {path}")

            else:
                # show all other server responses
                print(f"\n[server] {msg}")

    except ConnectionError:
        print("\nDisconnected from server.")
    except Exception as e:
        log.exception(f"Listener error: {e}")


def main() -> None:
    name = input("Enter your name: ").strip() or "user"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    # Start listener thread
    t = threading.Thread(target=listener, args=(sock,), daemon=True)
    t.start()

    # HELLO handshake
    send_json(sock, MSG_HELLO, {"name": name})

    print("Commands:")
    print("  /add <username>                 Add a contact")
    print("  /remove <username>              Remove a contact")
    print("  /contacts                       List contacts")
    print("  /dm <username> <message>        Send a direct message")
    print('  /sendfile <username> "<path>"   Send a file (quote path if spaces)')
    print("Ctrl+C to exit.\n")

    try:
        while True:
            raw = input("> ").strip()
            if not raw:
                continue

            if raw.startswith("/add "):
                parts = raw.split(" ", 1)
                contact = parts[1].strip() if len(parts) == 2 else ""
                if not contact:
                    print("Usage: /add <username>")
                    continue
                send_json(sock, MSG_CONTACT_ADD, {"contact": contact})

            elif raw.startswith("/remove "):
                parts = raw.split(" ", 1)
                contact = parts[1].strip() if len(parts) == 2 else ""
                if not contact:
                    print("Usage: /remove <username>")
                    continue
                send_json(sock, MSG_CONTACT_REMOVE, {"contact": contact})

            elif raw == "/contacts":
                send_json(sock, MSG_CONTACT_LIST, {})

            elif raw.startswith("/sendfile "):
                # Usage: /sendfile Bob "C:\path\file.jpg"  OR /sendfile Bob /home/me/file.jpg
                parts = raw.split(" ", 2)
                if len(parts) < 3:
                    print('Usage: /sendfile <username> "<path>"')
                    continue

                to_user = parts[1].strip()
                path = parts[2].strip().strip('"')

                if not to_user:
                    print("Error: username cannot be empty.")
                    continue

                if not os.path.isfile(path):
                    print(f"File not found: {path}")
                    continue

                file_id = uuid.uuid4().hex
                filename = os.path.basename(path)
                size = os.path.getsize(path)

                # Send metadata first
                send_json(
                    sock,
                    MSG_FILE_META,
                    {"to": to_user, "file_id": file_id, "filename": filename, "size": size},
                )

                # Send file in base64 chunks
                sent = 0
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        chunk_b64 = base64.b64encode(chunk).decode("ascii")
                        send_json(
                            sock,
                            MSG_FILE_CHUNK,
                            {"to": to_user, "file_id": file_id, "chunk_b64": chunk_b64},
                        )
                        sent += len(chunk)

                send_json(sock, MSG_FILE_DONE, {"to": to_user, "file_id": file_id})
                print(f"Sent file to {to_user}: {filename} ({sent}/{size} bytes)")

            elif raw.startswith("/dm "):
                parts = raw.split(" ", 2)
                if len(parts) < 3:
                    print("Usage: /dm <username> <message>")
                    continue

                to_user = parts[1].strip()
                text = parts[2]

                if not to_user:
                    print("Error: username cannot be empty.")
                    continue
                if not text:
                    print("Error: message cannot be empty.")
                    continue

                send_json(sock, MSG_DM_TEXT, {"to": to_user, "text": text})

            else:
                # normal message (server will show help)
                send_json(sock, MSG_TEXT, {"text": raw})

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        # Close any open incoming file handles
        for _, info in list(incoming_files.items()):
            try:
                info["fh"].close()
            except Exception:
                pass
        incoming_files.clear()

        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

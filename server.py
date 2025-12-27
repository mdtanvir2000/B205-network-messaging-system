from __future__ import annotations

import socket
import threading
from typing import Dict, Tuple

from config import HOST, PORT
from logger import make_logger
from protocol import (
    recv_json,
    send_json,
    MSG_HELLO,
    MSG_TEXT,
    MSG_DM_TEXT,
    MSG_CONTACT_ADD,
    MSG_CONTACT_REMOVE,
    MSG_CONTACT_LIST,
    MSG_FILE_META,
    MSG_FILE_CHUNK,
    MSG_FILE_DONE,
    MSG_ERROR,
)
from contacts_store import add_contact, remove_contact, list_contacts, is_contact

log = make_logger("server")

clients_lock = threading.Lock()

# Track connections (useful for debugging / cleanup)
addr_to_sock: Dict[Tuple[str, int], socket.socket] = {}

# User registry for routing
user_to_sock: Dict[str, socket.socket] = {}
sock_to_user: Dict[socket.socket, str] = {}

# Set to False if you want to allow DM/file to anyone (not only contacts)
ENFORCE_CONTACTS_FOR_DM = True


def handle_client(conn: socket.socket, addr: Tuple[str, int]) -> None:
    log.info(f"Client connected: {addr}")

    with clients_lock:
        addr_to_sock[addr] = conn

    username: str | None = None

    try:
        # --- Handshake: expect HELLO with {"name": "..."} ---
        data = recv_json(conn)
        if data.get("_mtype") != MSG_HELLO or "name" not in data:
            send_json(conn, MSG_ERROR, {"error": "Expected HELLO with {name}."})
            return

        candidate = str(data["name"]).strip()
        if not candidate:
            send_json(conn, MSG_ERROR, {"error": "Name cannot be empty."})
            return

        # Register username (must be unique)
        with clients_lock:
            if candidate in user_to_sock:
                send_json(conn, MSG_ERROR, {"error": "Name already in use. Choose another."})
                return
            user_to_sock[candidate] = conn
            sock_to_user[conn] = candidate
            username = candidate

        send_json(conn, MSG_HELLO, {"msg": f"Hello, {username}. You are connected.", "addr": str(addr)})

        # --- Main loop ---
        while True:
            msg = recv_json(conn)
            mtype = msg.get("_mtype")

            # -----------------------------
            # Direct Message routing
            # -----------------------------
            if mtype == MSG_DM_TEXT:
                to_user = str(msg.get("to", "")).strip()
                text = str(msg.get("text", ""))

                if not to_user or not text:
                    send_json(conn, MSG_ERROR, {"error": "DM_TEXT requires 'to' and 'text'."})
                    continue

                if to_user == username:
                    send_json(conn, MSG_ERROR, {"error": "You cannot DM yourself."})
                    continue

                if ENFORCE_CONTACTS_FOR_DM and not is_contact(username, to_user):
                    send_json(conn, MSG_ERROR, {"error": f"'{to_user}' is not in your contacts. Add them first."})
                    continue

                with clients_lock:
                    target_sock = user_to_sock.get(to_user)

                if not target_sock:
                    send_json(conn, MSG_ERROR, {"error": f"User '{to_user}' is not online."})
                    continue

                send_json(target_sock, MSG_TEXT, {"from": username, "text": text})
                send_json(conn, MSG_TEXT, {"from": "server", "text": f"delivered to {to_user}"})

            # -----------------------------
            # Contact management (ADD)
            # payload: {"contact": "<username>"}
            # -----------------------------
            elif mtype == MSG_CONTACT_ADD:
                contact = str(msg.get("contact", "")).strip()
                if not contact:
                    send_json(conn, MSG_ERROR, {"error": "CONTACT_ADD requires 'contact'."})
                    continue
                if contact == username:
                    send_json(conn, MSG_ERROR, {"error": "You cannot add yourself as a contact."})
                    continue

                add_contact(username, contact)
                send_json(conn, MSG_TEXT, {"from": "server", "text": f"Added contact: {contact}"})

            # -----------------------------
            # Contact management (REMOVE)
            # payload: {"contact": "<username>"}
            # -----------------------------
            elif mtype == MSG_CONTACT_REMOVE:
                contact = str(msg.get("contact", "")).strip()
                if not contact:
                    send_json(conn, MSG_ERROR, {"error": "CONTACT_REMOVE requires 'contact'."})
                    continue

                remove_contact(username, contact)
                send_json(conn, MSG_TEXT, {"from": "server", "text": f"Removed contact: {contact}"})

            # -----------------------------
            # Contact management (LIST)
            # payload: {}
            # -----------------------------
            elif mtype == MSG_CONTACT_LIST:
                contacts = list_contacts(username)
                send_json(conn, MSG_TEXT, {"from": "server", "text": f"Contacts: {contacts}"})

            # -----------------------------
            # File transfer: META (relay)
            # payload from sender: {"to","file_id","filename","size"}
            # -----------------------------
            elif mtype == MSG_FILE_META:
                to_user = str(msg.get("to", "")).strip()
                file_id = str(msg.get("file_id", "")).strip()
                filename = str(msg.get("filename", "")).strip()
                size = int(msg.get("size", 0))

                if not to_user or not file_id or not filename or size <= 0:
                    send_json(conn, MSG_ERROR, {"error": "FILE_META requires to, file_id, filename, size>0."})
                    continue

                if to_user == username:
                    send_json(conn, MSG_ERROR, {"error": "You cannot send a file to yourself."})
                    continue

                if ENFORCE_CONTACTS_FOR_DM and not is_contact(username, to_user):
                    send_json(conn, MSG_ERROR, {"error": f"'{to_user}' is not in your contacts. Add them first."})
                    continue

                with clients_lock:
                    target_sock = user_to_sock.get(to_user)

                if not target_sock:
                    send_json(conn, MSG_ERROR, {"error": f"User '{to_user}' is not online."})
                    continue

                # Relay metadata to recipient
                send_json(
                    target_sock,
                    MSG_FILE_META,
                    {"from": username, "file_id": file_id, "filename": filename, "size": size},
                )
                send_json(conn, MSG_TEXT, {"from": "server", "text": f"file offer sent to {to_user}: {filename} ({size} bytes)"})

            # -----------------------------
            # File transfer: CHUNK (relay)
            # payload: {"to","file_id","chunk_b64"}
            # -----------------------------
            elif mtype == MSG_FILE_CHUNK:
                to_user = str(msg.get("to", "")).strip()
                file_id = str(msg.get("file_id", "")).strip()
                chunk_b64 = str(msg.get("chunk_b64", ""))

                if not to_user or not file_id or not chunk_b64:
                    send_json(conn, MSG_ERROR, {"error": "FILE_CHUNK requires to, file_id, chunk_b64."})
                    continue

                with clients_lock:
                    target_sock = user_to_sock.get(to_user)

                if not target_sock:
                    send_json(conn, MSG_ERROR, {"error": f"User '{to_user}' is not online."})
                    continue

                send_json(
                    target_sock,
                    MSG_FILE_CHUNK,
                    {"from": username, "file_id": file_id, "chunk_b64": chunk_b64},
                )

            # -----------------------------
            # File transfer: DONE (relay)
            # payload: {"to","file_id"}
            # -----------------------------
            elif mtype == MSG_FILE_DONE:
                to_user = str(msg.get("to", "")).strip()
                file_id = str(msg.get("file_id", "")).strip()

                if not to_user or not file_id:
                    send_json(conn, MSG_ERROR, {"error": "FILE_DONE requires to, file_id."})
                    continue

                with clients_lock:
                    target_sock = user_to_sock.get(to_user)

                if not target_sock:
                    send_json(conn, MSG_ERROR, {"error": f"User '{to_user}' is not online."})
                    continue

                send_json(target_sock, MSG_FILE_DONE, {"from": username, "file_id": file_id})
                send_json(conn, MSG_TEXT, {"from": "server", "text": f"file transfer complete: {file_id}"})

            # -----------------------------
            # Basic server help / fallback
            # -----------------------------
            elif mtype == MSG_TEXT:
                send_json(
                    conn,
                    MSG_TEXT,
                    {
                        "from": "server",
                        "text": "Commands: /add <user>, /remove <user>, /contacts, /dm <user> <msg>, /sendfile <user> <path>",
                    },
                )

            else:
                send_json(conn, MSG_ERROR, {"error": f"Unknown message type: {mtype}"})

    except ConnectionError:
        log.info(f"Client disconnected: {addr}")
    except Exception as e:
        log.exception(f"Error handling client {addr}: {e}")
    finally:
        with clients_lock:
            addr_to_sock.pop(addr, None)
            u = sock_to_user.pop(conn, None)
            if username is None:
                username = u
            if username and user_to_sock.get(username) is conn:
                user_to_sock.pop(username, None)

        try:
            conn.close()
        except Exception:
            pass


def main() -> None:
    log.info(f"Starting server on {HOST}:{PORT}")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)

    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log.info("Shutting down (Ctrl+C).")
    finally:
        srv.close()


if __name__ == "__main__":
    main()

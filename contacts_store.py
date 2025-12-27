from __future__ import annotations

import json
import os
from typing import Dict, List

DEFAULT_PATH = "contacts.json"


def _load(path: str = DEFAULT_PATH) -> Dict[str, List[str]]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # normalize to {str: [str,...]}
    out: Dict[str, List[str]] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, list):
            out[k] = [str(x) for x in v]
    return out


def _save(data: Dict[str, List[str]], path: str = DEFAULT_PATH) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def add_contact(owner: str, contact: str, path: str = DEFAULT_PATH) -> None:
    data = _load(path)
    contacts = set(data.get(owner, []))
    contacts.add(contact)
    data[owner] = sorted(contacts)
    _save(data, path)


def remove_contact(owner: str, contact: str, path: str = DEFAULT_PATH) -> None:
    data = _load(path)
    contacts = set(data.get(owner, []))
    contacts.discard(contact)
    data[owner] = sorted(contacts)
    _save(data, path)


def list_contacts(owner: str, path: str = DEFAULT_PATH) -> List[str]:
    data = _load(path)
    return list(data.get(owner, []))


def is_contact(owner: str, contact: str, path: str = DEFAULT_PATH) -> bool:
    data = _load(path)
    return contact in set(data.get(owner, []))

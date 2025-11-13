import hashlib
import json


def get_hash(data: list | dict | str) -> str:
    if isinstance(data, dict | list):
        data = json.dumps(data, sort_keys=True)

    if isinstance(data, str):
        data = data.encode()

    return hashlib.sha256(data).hexdigest()

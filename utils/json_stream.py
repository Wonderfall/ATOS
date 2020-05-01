import json
from utils.json_hooks import int_keys
from utils.get_config import participants_path

with open(participants_path, 'r+') as f:
    participants = json.load(f, object_pairs_hook=int_keys)

def dump_participants():
    with open(participants_path, 'w') as f:
        json.dump(participants, f, indent=4)
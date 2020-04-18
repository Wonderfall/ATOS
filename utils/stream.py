import json

from utils.get_config import *
from utils.json_hooks import int_keys

def is_on_stream(suggested_play_order):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)
    return suggested_play_order in [stream[x]['on_stream'] for x in stream]

def is_queued_for_stream(suggested_play_order):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)
    return suggested_play_order in sum([stream[x]['queue'] for x in stream], [])
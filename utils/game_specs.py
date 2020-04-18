import json

from utils.get_config import *
from utils.json_hooks import dateconverter, dateparser, int_keys

### Accès stream
def get_access_stream(access):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if tournoi['game'] == 'Project+':
        return f":white_small_square: **Accès host Dolphin Netplay** : `{access[0]}`"

    elif tournoi['game'] == 'Super Smash Bros. Ultimate':
        return f":white_small_square: **ID** : `{access[0]}`\n:white_small_square: **MDP** : `{access[1]}`"

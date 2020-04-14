import json

### Accès stream
def get_access_stream():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if tournoi['game'] == 'Project+':
        return f":white_small_square: **Accès host Dolphin Netplay** : `{tournoi['stream'][0]}`"

    elif tournoi['game'] == 'Super Smash Bros. Ultimate':
        return f":white_small_square: **ID** : `{tournoi['stream'][0]}`\n:white_small_square: **MDP** : `{tournoi['stream'][1]}`"

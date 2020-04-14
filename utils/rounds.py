import json

from utils.get_config import *
from utils.json_hooks import dateconverter, dateparser, int_keys

### Determine whether a match is top 8 or not
def is_top8(match_round):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    return (match_round >= tournoi["round_winner_top8"]) or (match_round <= tournoi["round_looser_top8"])

### Retourner nom du round
def nom_round(match_round):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    max_round_winner = tournoi["round_winner_top8"] + 2
    max_round_looser = tournoi["round_looser_top8"] - 3

    if match_round > 0:
        if match_round == max_round_winner:
            return "GF"
        elif match_round == max_round_winner - 1:
            return "WF"
        elif match_round == max_round_winner - 2:
            return "WS"
        elif match_round == max_round_winner - 3:
            return "WQ"
        else:
            return f"WR{match_round}"

    elif match_round < 0:
        if match_round == max_round_looser:
            return "LF"
        elif match_round == max_round_looser + 1:
            return "LS"
        elif match_round == max_round_looser + 2:
            return "LQ"
        else:
            return f"LR{-match_round}"

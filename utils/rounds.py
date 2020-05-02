import json

from utils.get_config import *
from utils.json_hooks import dateconverter, dateparser, int_keys

### Determine whether a match is top 8 or not
def is_top8(match_round):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    return (match_round >= tournoi["round_winner_top8"]) or (match_round <= tournoi["round_looser_top8"])

### Determine whether a match is BO5 or not
def is_bo5(match_round):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    round_winner_bo5 = tournoi["round_winner_top8"] + tournoi["start_bo5"]
    round_looser_bo5 = tournoi["round_looser_top8"] - tournoi["start_bo5"]
    return (match_round >= round_winner_bo5) or (match_round <= round_looser_bo5)

### Retourner nom du round
def nom_round(match_round):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    max_round_winner = tournoi["round_winner_top8"] + 2
    max_round_looser = tournoi["round_looser_top8"] - 3

    if match_round > 0:
        if match_round == max_round_winner:
            return "Grand Final"
        elif match_round == max_round_winner - 1:
            return "Winners Final"
        elif match_round == max_round_winner - 2:
            return "Winners Semi-Final"
        elif match_round == max_round_winner - 3:
            return "Winners Quarter-Final"
        else:
            return f"Winners Round {match_round}"

    elif match_round < 0:
        if match_round == max_round_looser:
            return "Losers Final"
        elif match_round == max_round_looser + 1:
            return "Losers Semi-Final"
        elif match_round == max_round_looser + 2:
            return "Losers Quarter-Final"
        else:
            return f"Losers Round {-match_round}"

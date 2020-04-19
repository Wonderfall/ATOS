import asyncio
import json
import challonge
import csv
from urllib import request, error
from utils.http_retry import async_http_retry
from utils.get_config import *
from utils.json_hooks import dateconverter, dateparser, int_keys
from statistics import median


async def get_ranking_csv():
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    url = (f"https://braacket.com/league/{stagelist[tournoi['game']]['ranking']['league_name']}/ranking/"
           f"{stagelist[tournoi['game']]['ranking']['league_id']}?rows=200&export=csv")

    await async_http_retry(request.urlretrieve, url, ranking_path)


async def seed_participants():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)

    # Backup, just in case
    with open(f'{participants_path}.bak', 'w') as f: json.dump(participants, f, indent=4)

    ranking = {}

    # Open and parse the previously downloaded CSV
    with open(ranking_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ranking[row['Player']] = int(row['Points'])

    # Determine median Elo (should be around 1500, but let's adjust that)
    base_elo = median(list(ranking.values()))

    # Assign Elo ranking to each player
    for joueur in participants:
        try:
            participants[joueur]['elo'] = ranking[participants[joueur]['display_name']]
        except KeyError:
            participants[joueur]['elo'] = base_elo # median Elo if none found

    # Sort!
    sorted_participants = sorted(participants.items(), key=lambda k_v: k_v[1]['elo'], reverse=True)

    # Send to Challonge
    challonge_participants = await async_http_retry(
        challonge.participants.bulk_add,
        tournoi['id'],
        [x[1]['display_name'] for x in sorted_participants]
    )

    # Assign IDs
    for inscrit in challonge_participants:
        for joueur in participants:
            if inscrit['name'] == participants[joueur]['display_name']:
                participants[joueur]['challonge'] = inscrit['id']
                break

    with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
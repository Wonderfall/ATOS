import asyncio
import json
import achallonge
import csv
from urllib import request, error
from utils.http_retry import async_http_retry
from utils.get_config import *
from utils.json_hooks import dateconverter, dateparser, int_keys
from statistics import median
from filecmp import cmp
from pathlib import Path


async def get_ranking_csv(tournoi):
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    for page in range(1,6): # Retrieve up to 5*200 = 1000 entries (since max. CSV export is 200)

        url = (f"https://braacket.com/league/{gamelist[tournoi['game']]['ranking']['league_name']}/ranking/"
               f"{gamelist[tournoi['game']]['ranking']['league_id']}?rows=200&page={page}&export=csv")

        # Braacket doesn't throw an error if retrived page shouldn't exist, so...
        await async_http_retry(request.urlretrieve, url, f'{ranking_path}_{page}')

        # ... stop and remove file if the last one is identical!
        if page != 1 and cmp(f'{ranking_path}_{page}', f'{ranking_path}_{page-1}'):
            Path(f'{ranking_path}_{page}').unlink()
            break


async def seed_participants():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)

    # Backup, just in case
    with open(f'{participants_path}.bak', 'w') as f: json.dump(participants, f, indent=4)

    ranking = {}

    # Open and parse the previously downloaded CSV
    for file in list(Path(Path(ranking_path).parent).rglob('*.csv_*')):
        with open(file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                ranking[row['Player']] = int(row['Points'])

    # Base elo : median if ranking incomplete, put at bottom otherwise
    base_elo = median(list(ranking.values())) #if len(ranking) < 200 else min(list(ranking.values()))

    # Assign Elo ranking to each player
    for joueur in participants:
        try:
            participants[joueur]['elo'] = ranking[participants[joueur]['display_name']]
        except KeyError:
            participants[joueur]['elo'] = base_elo # base Elo if none found

    # Sort!
    sorted_participants = sorted(participants.items(), key=lambda k_v: k_v[1]['elo'], reverse=True)
    sorted_participants = [x[1]['display_name'] for x in sorted_participants]

    # Send to Challonge
    challonge_participants = await async_http_retry(
        achallonge.participants.bulk_add,
        tournoi['id'],
        sorted_participants
    )

    # Assign IDs
    for inscrit in challonge_participants:
        for joueur in participants:
            if inscrit['name'] == participants[joueur]['display_name']:
                participants[joueur]['challonge'] = inscrit['id']
                break

    with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
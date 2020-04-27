### Custom Discord commands checks
import json
from datetime import datetime
from discord.ext import commands

from utils.get_config import *
from utils.json_hooks import dateconverter, dateparser, int_keys

# Is tournament pending?
def tournament_is_pending(ctx):
    try:
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        return tournoi["statut"] == "pending"
    except (FileNotFoundError, TypeError, KeyError):
        return False

# Is tournament pending?
def tournament_is_underway(ctx):
    try:
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        return tournoi["statut"] == "underway"
    except (FileNotFoundError, TypeError, KeyError):
        return False

# Is tournament pending?
def tournament_is_underway_or_pending(ctx):
    try:
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        return tournoi["statut"] in ["underway", "pending"]
    except (FileNotFoundError, TypeError, KeyError):
        return False

# Are inscriptions still open?
def inscriptions_still_open(ctx):
    try:
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        return datetime.now() < tournoi["fin_inscription"]
    except (FileNotFoundError, TypeError, KeyError):
        return False

# In channel?
def in_channel(channel_id):
    async def predicate(ctx):
        if ctx.channel.id != channel_id:
            await ctx.send(f"<@{ctx.author.id}> Cette commande fonctionne uniquement dans <#{channel_id}> !")
            return False
        return True
    return commands.check(predicate)

# Is owner or TO
async def is_owner_or_to(ctx):
    return to_id in [y.id for y in ctx.author.roles] or await ctx.bot.is_owner(ctx.author)

# Is streaming?
def is_streaming(ctx):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)
    return ctx.author.id in stream
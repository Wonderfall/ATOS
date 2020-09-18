import discord, random, logging, os, json, re, achallonge, dateutil.parser, dateutil.relativedelta, datetime, time, asyncio, yaml, sys
import aiofiles, aiofiles.os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from babel.dates import format_date, format_time
from discord.ext import commands
from pathlib import Path
from achallonge import ChallongeException

# Custom modules
from utils.json_hooks import dateconverter, dateparser, int_keys
from utils.command_checks import tournament_is_pending, tournament_is_underway, tournament_is_underway_or_pending, in_channel, in_combat_channel, is_streaming, is_owner_or_to, inscriptions_still_open
from utils.stream import is_on_stream, is_queued_for_stream
from utils.rounds import is_top8, nom_round, is_bo5
from utils.game_specs import get_access_stream
from utils.http_retry import async_http_retry
from utils.seeding import get_ranking_csv, seed_participants
from utils.logging import init_loggers
from utils.json_stream import participants, dump_participants

# Import configuration (variables only)
from utils.get_config import *

# Import raw texts (variables only)
from utils.raw_texts import *

log = logging.getLogger("atos")

#### Infos
version = "5.24"
author = "Wonderfall"
name = "A.T.O.S."

### Cogs
initial_extensions = ['cogs.dev_commands']


### Init things
bot = commands.Bot(command_prefix=commands.when_mentioned_or(bot_prefix)) # Set prefix for commands
bot.remove_command('help') # Remove default help command to set our own
achallonge.set_credentials(challonge_user, challonge_api_key)
scheduler = AsyncIOScheduler()


#### Notifier de l'initialisation
@bot.event
async def on_ready():
    log.info("Bot successfully connected to Discord.")
    print(f"-------------------------------------")
    print(f"             A. T. O. S.             ")
    print(f"        Automated TO for Smash       ")
    print(f"                                     ")
    print(f"Version : {version}                  ")
    print(f"discord.py : {discord.__version__}   ")
    print(f"User : {bot.user.name}               ")
    print(f"User ID : {bot.user.id}              ")
    print(f"-------------------------------------")
    await bot.change_presence(activity=discord.Game(f'{name} • {version}')) # As of April 2020, CustomActivity is not supported for bots
    await reload_tournament()


### A chaque arrivée de membre
@bot.event
async def on_member_join(member):

    if greet_new_members == False: return

    message = random.choice([
        f"<@{member.id}> joins the battle!",
        f"Bienvenue à toi sur le serveur {member.guild.name}, <@{member.id}>.",
        f"Un <@{member.id}> sauvage apparaît !",
        f"Le serveur {member.guild.name} accueille un nouveau membre :  <@{member.id}> !"
    ])

    try:
        await member.send(f"Bienvenue sur le serveur **{member.guild.name}** ! {welcome_text}")
    except discord.Forbidden:
        await bot.get_channel(blabla_channel_id).send(f"{message} {welcome_text}")
    else:
        await bot.get_channel(blabla_channel_id).send(message) # Avoid sending welcome_text to the channel if possible


### Récupérer informations du tournoi et initialiser tournoi.json
async def init_tournament(url_or_id):

    with open(preferences_path, 'r+') as f: preferences = yaml.full_load(f)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    try:
        infos = await async_http_retry(achallonge.tournaments.show, url_or_id)
    except ChallongeException:
        return

    debut_tournoi = dateutil.parser.parse(str(infos["start_at"])).replace(tzinfo=None)

    tournoi = {
        "name": infos["name"],
        "game": infos["game_name"].title(), # Non-recognized games are lowercase for Challonge
        "url": infos["full_challonge_url"],
        "id": infos["id"],
        "limite": infos["signup_cap"],
        "statut": infos["state"],
        "début_tournoi": debut_tournoi,
        "début_check-in": debut_tournoi - datetime.timedelta(minutes = preferences['check_in_opening']),
        "fin_check-in": debut_tournoi - datetime.timedelta(minutes = preferences['check_in_closing']),
        "fin_inscription": debut_tournoi - datetime.timedelta(minutes = preferences['inscriptions_closing']),
        "use_guild_name": preferences['use_guild_name'],
        "bulk_mode": preferences['bulk_mode'],
        "reaction_mode": preferences['reaction_mode'],
        "restrict_to_role": preferences['restrict_to_role'],
        "check_channel_presence": preferences['check_channel_presence'],
        "start_bo5": preferences['start_bo5'],
        "full_bo3": preferences['full_bo3'],
        "full_bo5": preferences['full_bo5'],
        "warned": [],
        "timeout": []
    }

    # Checks
    if tournoi['game'] not in gamelist:
        await bot.get_channel(to_channel_id).send(f":warning: Création du tournoi *{tournoi['game']}* annulée : **jeu introuvable dans la gamelist**.")
        return

    if not (datetime.datetime.now() < tournoi["début_check-in"] < tournoi["fin_check-in"] < tournoi["fin_inscription"] < tournoi["début_tournoi"]):
        await bot.get_channel(to_channel_id).send(f":warning: Création du tournoi *{tournoi['game']}* annulée : **conflit des temps de check-in et d'inscriptions**.")
        return

    if tournoi['bulk_mode'] == True:
        try:
            await get_ranking_csv(tournoi)
        except (KeyError, ValueError):
            await bot.get_channel(to_channel_id).send(f":warning: Création du tournoi *{tournoi['game']}* annulée : **données de ranking introuvables**.\n"
                                                      f"*Désactivez le bulk mode avec `{bot_prefix}set bulk_mode off` si vous ne souhaitez pas utiliser de ranking.*")
            return

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
    with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
    with open(stream_path, 'w') as f: json.dump({}, f, indent=4)

    # Ensure permissions
    guild = bot.get_guild(id=guild_id)
    challenger = guild.get_role(challenger_id)
    await bot.get_channel(check_in_channel_id).set_permissions(challenger, read_messages=True, send_messages=False, add_reactions=False)
    await bot.get_channel(check_in_channel_id).edit(slowmode_delay=60)
    await bot.get_channel(scores_channel_id).set_permissions(challenger, read_messages=True, send_messages=False, add_reactions=False)
    await bot.get_channel(queue_channel_id).set_permissions(challenger, read_messages=True, send_messages=False, add_reactions=False)

    scheduler.add_job(start_check_in, id='start_check_in', run_date=tournoi["début_check-in"], replace_existing=True)
    scheduler.add_job(end_check_in, id='end_check_in', run_date=tournoi["fin_check-in"], replace_existing=True)
    scheduler.add_job(end_inscription, id='end_inscription', run_date=tournoi["fin_inscription"], replace_existing=True)

    await init_compteur()

    await bot.change_presence(activity=discord.Game(tournoi['name']))

    await purge_channels()

### Ajouter un tournoi
@bot.command(name='setup')
@commands.check(is_owner_or_to)
async def setup_tournament(ctx, arg):

    if re.compile(r"^(https?\:\/\/)?(challonge.com)\/.+$").match(arg):
        await init_tournament(arg.replace("https://challonge.com/", ""))
    else:
        await ctx.message.add_reaction("🔗")
        return

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        tournoi["début_tournoi"]
    except KeyError:
        await ctx.message.add_reaction("⚠️")
    else:
        await ctx.message.add_reaction("✅")


### AUTO-MODE : will take care of creating tournaments for you
@scheduler.scheduled_job('interval', id='auto_setup_tournament', hours=1)
async def auto_setup_tournament():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(auto_mode_path, 'r+') as f: tournaments = yaml.full_load(f)
    with open(preferences_path, 'r+') as f: preferences = yaml.full_load(f)

    #  Auto-mode won't run if at least one of these conditions is met :
    #    - It's turned off in preferences.yml
    #    - A tournament is already initialized
    #    - It's "night" time

    if (preferences['auto_mode'] != True) or (tournoi != {}) or (not 10 <= datetime.datetime.now().hour <= 22): return

    for tournament in tournaments:

        for day in tournaments[tournament]["days"]:

            try:
                relative = dateutil.relativedelta.relativedelta(weekday = time.strptime(day, '%A').tm_wday) # It's a weekly
            except TypeError:
                relative = dateutil.relativedelta.relativedelta(day = day) # It's a monthly
            except ValueError:
                return # Neither?
 
            next_date = (datetime.datetime.now().astimezone() + relative).replace(
                hour = dateutil.parser.parse(tournaments[tournament]["start"]).hour,
                minute = dateutil.parser.parse(tournaments[tournament]["start"]).minute,
                second = 0,
                microsecond = 0 # for dateparser to work
            )

            # If the tournament is supposed to be in less than inscriptions_opening (hours), let's go !
            if abs(next_date - datetime.datetime.now().astimezone()) < datetime.timedelta(hours = preferences['inscriptions_opening']):

                new_tournament = await async_http_retry(
                    achallonge.tournaments.create,
                    name=f"{tournament} #{tournaments[tournament]['edition']}",
                    url=f"{re.sub('[^A-Za-z0-9]+', '', tournament)}{tournaments[tournament]['edition']}",
                    tournament_type='double elimination',
                    show_rounds=True,
                    description=tournaments[tournament]['description'],
                    signup_cap=tournaments[tournament]['capping'],
                    game_name=tournaments[tournament]['game'],
                    start_at=next_date
                )

                await init_tournament(new_tournament["id"])

                # Check if the tournamet was configured
                with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
                if tournoi != {}:
                    tournaments[tournament]["edition"] += 1
                    with open(auto_mode_path, 'w') as f: yaml.dump(tournaments, f)

                return


### Démarrer un tournoi
@bot.command(name='start')
@commands.check(is_owner_or_to)
@commands.check(tournament_is_pending)
async def start_tournament(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    guild = bot.get_guild(id=guild_id)
    challenger = guild.get_role(challenger_id)

    if datetime.datetime.now() > tournoi["fin_inscription"]:
        await async_http_retry(achallonge.tournaments.start, tournoi["id"])
        tournoi["statut"] = "underway"
        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
        await ctx.message.add_reaction("✅")
    else:
        await ctx.message.add_reaction("🕐")
        return

    await calculate_top8()

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser) # Refresh to get top 8
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    await bot.get_channel(annonce_channel_id).send(f"{server_logo} Le tournoi **{tournoi['name']}** est officiellement lancé ! Voici le bracket : {tournoi['url']}\n"
                                                   f":white_small_square: Vous pouvez y accéder à tout moment avec la commande `{bot_prefix}bracket`.\n"
                                                   f":white_small_square: Vous pouvez consulter les liens de stream avec la commande `{bot_prefix}stream`.")

    score_annonce = (f":information_source: La prise en charge des scores pour le tournoi **{tournoi['name']}** est automatisée :\n"
                     f":white_small_square: Seul **le gagnant du set** envoie le score de son set, précédé par la **commande** `{bot_prefix}win`.\n"
                     f":white_small_square: Le message du score doit contenir le **format suivant** : `{bot_prefix}win 2-0, 3-2, 3-1, ...`.\n"
                     f":white_small_square: Un mauvais score intentionnel, perturbant le déroulement du tournoi, est **passable de DQ et ban**.\n"
                     f":white_small_square: Consultez le bracket afin de **vérifier** les informations : {tournoi['url']}\n"
                     f":white_small_square: En cas de mauvais score : contactez un TO pour une correction manuelle.\n\n"
                     f":satellite_orbital: Chaque score étant **transmis un par un**, il est probable que la communication prenne jusqu'à 30 secondes.")

    await bot.get_channel(scores_channel_id).send(score_annonce)
    await bot.get_channel(scores_channel_id).set_permissions(challenger, read_messages=True, send_messages=True, add_reactions=False)

    queue_annonce = (f":information_source: **Le lancement des sets est automatisé.** Veuillez suivre les consignes de ce channel, que ce soit par le bot ou les TOs.\n"
                     f":white_small_square: Tout passage on stream sera notifié à l'avance, ici, dans votre channel (ou par DM).\n"
                     f":white_small_square: Tout set devant se jouer en BO5 est indiqué ici, et également dans votre channel.\n"
                     f":white_small_square: La personne qui commence les bans est indiquée dans votre channel (en cas de besoin : `{bot_prefix}flip`).\n\n"
                     f":timer: Vous serez **DQ automatiquement** si vous n'avez pas été actif sur votre channel __dans les {tournoi['check_channel_presence']} minutes qui suivent sa création__.")

    await bot.get_channel(queue_channel_id).send(queue_annonce)

    tournoi_annonce = (f":alarm_clock: <@&{challenger_id}> On arrête le freeplay ! Le tournoi est sur le point de commencer. Veuillez lire les consignes :\n"
                       f":white_small_square: Vos sets sont annoncés dès que disponibles dans <#{queue_channel_id}> : **ne lancez rien sans consulter ce channel**.\n"
                       f":white_small_square: Le ruleset ainsi que les informations pour le bannissement des stages sont dispo dans <#{gamelist[tournoi['game']]['ruleset']}>.\n"
                       f":white_small_square: Le gagnant d'un set doit rapporter le score **dès que possible** dans <#{scores_channel_id}> avec la commande `{bot_prefix}win`.\n"
                       f":white_small_square: Vous pouvez DQ du tournoi avec la commande `{bot_prefix}dq`, ou juste abandonner votre set en cours avec `{bot_prefix}ff`.\n"
                       f":white_small_square: En cas de lag qui rend votre set injouable, utilisez la commande `{bot_prefix}lag` pour résoudre la situation.\n"
                       f":timer: Vous serez **DQ automatiquement** si vous n'avez pas été actif sur votre channel __dans les {tournoi['check_channel_presence']} minutes qui suivent sa création__.")

    if tournoi["game"] == "Project+":
        tournoi_annonce += f"\n{gamelist[tournoi['game']]['icon']} En cas de desync, utilisez la commande `{bot_prefix}desync` pour résoudre la situation."

    tournoi_annonce += (f"\n\n:fire: Le **top 8** commencera, d'après le bracket :\n"
                        f":white_small_square: En **{nom_round(tournoi['round_winner_top8'])}**\n"
                        f":white_small_square: En **{nom_round(tournoi['round_looser_top8'])}**\n\n")
    
    if tournoi["full_bo3"]:
        tournoi_annonce += ":three: L'intégralité du tournoi se déroulera en **BO3**."
    elif tournoi["full_bo5"]:
        tournoi_annonce += ":five: L'intégralité du tournoi se déroulera en **BO5**."
    elif tournoi["start_bo5"] != 0:
        tournoi_annonce += (f":five: Les **BO5** commenceront quant à eux :\n"
                            f":white_small_square: En **{nom_round(tournoi['round_winner_bo5'])}**\n"
                            f":white_small_square: En **{nom_round(tournoi['round_looser_bo5'])}**")
    else:
        tournoi_annonce += ":five: Les **BO5** commenceront en **top 8**."

    tournoi_annonce += "\n\n*L'équipe de TO et moi-même vous souhaitons un excellent tournoi !*"

    await bot.get_channel(tournoi_channel_id).send(tournoi_annonce)

    scheduler.add_job(underway_tournament, 'interval', id='underway_tournament', minutes=1, start_date=tournoi["début_tournoi"], replace_existing=True)


### Terminer un tournoi
@bot.command(name='end')
@commands.check(is_owner_or_to)
@commands.check(tournament_is_underway)
async def end_tournament(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if datetime.datetime.now() > tournoi["début_tournoi"]:
        await async_http_retry(achallonge.tournaments.finalize, tournoi["id"])
        await ctx.message.add_reaction("✅")
    else:
        await ctx.message.add_reaction("🕐")
        return

    # Remove underway task
    try:
        scheduler.remove_job('underway_tournament')
    except JobLookupError:
        pass
    
    # Annoucements (including results)
    await annonce_resultats()
    await bot.get_channel(annonce_channel_id).send(
        f"{server_logo} Le tournoi **{tournoi['name']}** est terminé, merci à toutes et à tous d'avoir participé ! "
        f"J'espère vous revoir bientôt.")

    # Reset participants
    participants.clear()

    # Reset JSON storage
    with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
    with open(tournoi_path, 'w') as f: json.dump({}, f, indent=4)
    with open(stream_path, 'w') as f: json.dump({}, f, indent=4)

    # Remove now obsolete files
    for file in list(Path(Path(ranking_path).parent).rglob('*.csv_*')):
        await aiofiles.os.remove(file)
    for file in list(Path(Path(participants_path).parent).rglob('*.bak')):
        await aiofiles.os.remove(file)

    # Change presence back to default
    await bot.change_presence(activity=discord.Game(f'{name} • {version}'))

    # Remove tournament roles & categories
    await purge_categories()
    await purge_roles()


### S'execute à chaque lancement, permet de relancer les tâches en cas de crash
async def reload_tournament():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        await bot.change_presence(activity=discord.Game(tournoi['name']))
    except KeyError:
        log.info("No tournament had to be reloaded.")
        return

    # Relancer les tâches automatiques
    if tournoi["statut"] == "underway":
        scheduler.add_job(underway_tournament, 'interval', id='underway_tournament', minutes=1, replace_existing=True)

    elif datetime.datetime.now() < tournoi["fin_inscription"]:
        scheduler.add_job(start_check_in, id='start_check_in', run_date=tournoi["début_check-in"], replace_existing=True)
        scheduler.add_job(end_check_in, id='end_check_in', run_date=tournoi["fin_check-in"], replace_existing=True)
        scheduler.add_job(end_inscription, id='end_inscription', run_date=tournoi["fin_inscription"], replace_existing=True)
        scheduler.add_job(dump_participants, 'interval', id='dump_participants', seconds=10, replace_existing=True)

        if tournoi["début_check-in"] < datetime.datetime.now() < tournoi["fin_check-in"]:
            scheduler.add_job(rappel_check_in, 'interval', id='rappel_check_in', minutes=10, replace_existing=True)

    log.info("Scheduled tasks for a tournament have been reloaded.")

    # Prendre les inscriptions manquées
    if datetime.datetime.now() < tournoi["fin_inscription"]:
        
        if tournoi["reaction_mode"]:
            annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])

            # Avoir une liste des users ayant réagi
            for reaction in annonce.reactions:
                if str(reaction.emoji) == "✅":
                    reactors = await reaction.users().flatten()
                    break

            # Inscrire ceux qui ne sont pas dans les participants
            id_list = []

            for reactor in reactors:
                if reactor.id != bot.user.id:
                    id_list.append(reactor.id)  # Récupérer une liste des IDs pour plus tard

                    if reactor.id not in participants:
                        await inscrire(reactor)

            # Désinscrire ceux qui ne sont plus dans la liste des users ayant réagi
            for inscrit in participants:
                if inscrit not in id_list:
                    await desinscrire(annonce.guild.get_member(inscrit))
        
        else:
            async for message in bot.get_channel(inscriptions_channel_id).history(oldest_first=True):
                if message.author == bot.user or message.reactions != []:
                    continue

                if not any([bot.user in await reaction.users().flatten() for reaction in message.reactions]):
                    await bot.process_commands(message)

        log.info("Missed inscriptions were also taken care of.")


### Annonce et lance les inscriptions
@bot.command(name='inscriptions')
@commands.check(is_owner_or_to)
@commands.check(tournament_is_pending)
async def annonce_inscription(ctx):
    
    scheduler.add_job(dump_participants, 'interval', id='dump_participants', seconds=10, replace_existing=True)

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    inscriptions_channel = bot.get_channel(inscriptions_channel_id)
    inscriptions_role = inscriptions_channel.guild.get_role(gamelist[tournoi['game']]['role']) if tournoi["restrict_to_role"] else inscriptions_channel.guild.default_role

    if tournoi['reaction_mode']:
        await inscriptions_channel.set_permissions(inscriptions_role, read_messages=True, send_messages=False, add_reactions=False)
    else:
        await inscriptions_channel.set_permissions(inscriptions_role, read_messages=True, send_messages=True, add_reactions=False)
        await inscriptions_channel.edit(slowmode_delay=60)

    await ctx.message.add_reaction("✅")

    await bot.get_channel(annonce_channel_id).send(f"{server_logo} Inscriptions pour le **{tournoi['name']}** ouvertes dans <#{inscriptions_channel_id}> ! Consultez-y les messages épinglés. <@&{gamelist[tournoi['game']]['role']}>\n"
                                                   f":calendar_spiral: Ce tournoi aura lieu le **{format_date(tournoi['début_tournoi'], format='full', locale=language)} à {format_time(tournoi['début_tournoi'], format='short', locale=language)}**.")

### Initialise le compteur d'inscrits dans le salon d'inscriptions
async def init_compteur():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    annonce = (
        f"{server_logo} **{tournoi['name']}** - {gamelist[tournoi['game']]['icon']} *{tournoi['game']}*\n"
        f":white_small_square: __Date__ : {format_date(tournoi['début_tournoi'], format='full', locale=language)} à {format_time(tournoi['début_tournoi'], format='short', locale=language)}\n"
        f":white_small_square: __Check-in__ : de {format_time(tournoi['début_check-in'], format='short', locale=language)} à {format_time(tournoi['fin_check-in'], format='short', locale=language)} "
        f"(fermeture des inscriptions à {format_time(tournoi['fin_inscription'], format='short', locale=language)})\n"
        f":white_small_square: __Limite__ : 0/{str(tournoi['limite'])} joueurs *(mise à jour en temps réel)*\n"
        f":white_small_square: __Bracket__ : {tournoi['url'] if not tournoi['bulk_mode'] else 'disponible peu de temps avant le début du tournoi'}\n"
        f":white_small_square: __Format__ : singles, double élimination (ruleset : <#{gamelist[tournoi['game']]['ruleset']}>)\n\n"
        f"Vous pouvez vous inscrire/désinscrire {'en ajoutant/retirant la réaction ✅ à ce message' if tournoi['reaction_mode'] else f'avec les commandes `{bot_prefix}in`/`{bot_prefix}out`'}.\n"
        f"*Note : votre **pseudonyme {'sur ce serveur' if tournoi['use_guild_name'] else 'Discord général'}** au moment de l'inscription sera celui utilisé dans le bracket.*"
    )

    inscriptions_channel = bot.get_channel(inscriptions_channel_id)

    await inscriptions_channel.purge(limit=None)

    annonce_msg = await inscriptions_channel.send(annonce)
    tournoi['annonce_id'] = annonce_msg.id
    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

    if tournoi['reaction_mode']:
        await annonce_msg.add_reaction("✅")
    
    await annonce_msg.pin()

### Inscription
async def inscrire(member):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if (member.id not in participants) and (len(participants) < tournoi['limite']):
        participants[member.id] = {
            "display_name": member.display_name if tournoi['use_guild_name'] else str(member),
            "checked_in": datetime.datetime.now() > tournoi["début_check-in"]
        }

        if tournoi["bulk_mode"] == False or datetime.datetime.now() > tournoi["fin_inscription"]:
            try:
                participants[member.id]["challonge"] = (
                    await async_http_retry(
                        achallonge.participants.create,
                        tournoi["id"],
                        participants[member.id]["display_name"]
                    )
                )['id']
            except ChallongeException:
                del participants[member.id]
                return

        await member.add_roles(member.guild.get_role(challenger_id))
        await update_annonce()
        try:
            msg = f"Tu t'es inscrit(e) avec succès pour le tournoi **{tournoi['name']}**."
            if datetime.datetime.now() > tournoi["début_check-in"]:
                msg += " Tu n'as **pas besoin de check-in** comme le tournoi commence bientôt !"
            await member.send(msg)
        except discord.Forbidden:
            pass

    elif tournoi["reaction_mode"] and len(participants) >= tournoi['limite']:
        try:
            await member.send(f"Il n'y a malheureusement plus de place pour le tournoi **{tournoi['name']}**. "
                              f"Retente ta chance plus tard, par exemple à la fin du check-in pour remplacer les absents !")
        except discord.Forbidden:
            pass

        try:
            inscription = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
            await inscription.remove_reaction("✅", member)
        except (discord.HTTPException, discord.NotFound):
            pass


### Désinscription
async def desinscrire(member):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if member.id in participants:

        if tournoi["bulk_mode"] == False or datetime.datetime.now() > tournoi["fin_inscription"]:
            await async_http_retry(achallonge.participants.destroy, tournoi['id'], participants[member.id]['challonge'])

        try:
            await member.remove_roles(member.guild.get_role(challenger_id))
        except discord.HTTPException:
            pass

        if datetime.datetime.now() < tournoi["fin_inscription"]:

            del participants[member.id]

            if tournoi['reaction_mode']:
                try:
                    inscription = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
                    await inscription.remove_reaction("✅", member)
                except (discord.HTTPException, discord.NotFound):
                    pass

            await update_annonce()

            try:
                await member.send(f"Tu es désinscrit(e) du tournoi **{tournoi['name']}**. À une prochaine fois peut-être !")
            except discord.Forbidden:
                pass


### Mettre à jour l'annonce d'inscription
async def update_annonce():

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    old_annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
    new_annonce = re.sub(r'[0-9]{1,3}\/', str(len(participants)) + '/', old_annonce.content)
    await old_annonce.edit(content=new_annonce)


### Début du check-in
async def start_check_in():

    guild = bot.get_guild(id=guild_id)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    challenger = guild.get_role(challenger_id)

    scheduler.add_job(rappel_check_in, 'interval', id='rappel_check_in', minutes=10, replace_existing=True)

    await bot.get_channel(inscriptions_channel_id).send(f":information_source: Le check-in a commencé dans <#{check_in_channel_id}>. "
                                                        f"Vous pouvez toujours vous inscrire ici jusqu'à **{format_time(tournoi['fin_inscription'], format='short', locale=language)}**.\n\n"
                                                        f"*Toute personne s'inscrivant à partir de ce moment est **check-in automatiquement**.*")

    await bot.get_channel(check_in_channel_id).send(f"<@&{challenger_id}> Le check-in pour **{tournoi['name']}** a commencé ! "
                                                    f"Vous avez jusqu'à **{format_time(tournoi['fin_check-in'], format='short', locale=language)}** pour signaler votre présence :\n"
                                                    f":white_small_square: Utilisez `{bot_prefix}in` pour confirmer votre inscription\n:white_small_square: Utilisez `{bot_prefix}out` pour vous désinscrire\n\n"
                                                    f"*Si vous n'avez pas check-in à temps, vous serez désinscrit automatiquement du tournoi.*")

    await bot.get_channel(check_in_channel_id).set_permissions(challenger, read_messages=True, send_messages=True, add_reactions=False)


### Rappel de check-in
async def rappel_check_in():

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    guild = bot.get_guild(id=guild_id)

    rappel_msg = ""

    for inscrit in participants:

        if participants[inscrit]["checked_in"] == False:
            rappel_msg += f"- <@{inscrit}>\n"

            if tournoi["fin_check-in"] - datetime.datetime.now() < datetime.timedelta(minutes=10):
                try:
                    await guild.get_member(inscrit).send(f"**Attention !** Il te reste moins d'une dizaine de minutes pour check-in au tournoi **{tournoi['name']}**.")
                except discord.Forbidden:
                    pass

    if rappel_msg == "": return

    await bot.get_channel(check_in_channel_id).send(":clock1: **Rappel de check-in !**")

    if len(rappel_msg) < 2000:
        await bot.get_channel(check_in_channel_id).send(rappel_msg)
    else: # Discord doesn't deal with more than 2000 characters
        rappel_msg = [x.strip() for x in rappel_msg.split('\n') if x.strip() != ''] # so we have to split
        while rappel_msg:
            await bot.get_channel(check_in_channel_id).send('\n'.join(rappel_msg[:50]))
            del rappel_msg[:50] # and send by groups of 50 people

    await bot.get_channel(check_in_channel_id).send(f"*Vous avez jusqu'à {format_time(tournoi['fin_check-in'], format='short', locale=language)}, sinon vous serez désinscrit(s) automatiquement.*")


### Fin du check-in
async def end_check_in():

    guild = bot.get_guild(id=guild_id)

    await bot.get_channel(check_in_channel_id).set_permissions(guild.get_role(challenger_id), read_messages=True, send_messages=False, add_reactions=False)
    await bot.get_channel(check_in_channel_id).send(":clock1: **Le check-in est terminé :**\n"
                                                    ":white_small_square: Les personnes n'ayant pas check-in vont être retirées du tournoi.\n"
                                                    ":white_small_square: Rappel : une inscription après le début du check-in ne néccessite pas de check-in.")

    try:
        scheduler.remove_job('rappel_check_in')
    except JobLookupError:
        pass

    for inscrit in list(participants):
        try:
            if participants[inscrit]["checked_in"] == False:
                await desinscrire(guild.get_member(inscrit))
        except KeyError:
            pass

    await bot.get_channel(inscriptions_channel_id).send(":information_source: **Les absents du check-in ont été retirés** : "
                                                        "des places sont peut-être libérées pour des inscriptions de dernière minute.\n")


### Fin des inscriptions
async def end_inscription():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    if tournoi["reaction_mode"]:
        annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
        await annonce.clear_reaction("✅")
    else:
        guild = bot.get_guild(id=guild_id)
        inscriptions_role = guild.get_role(gamelist[tournoi['game']]['role']) if tournoi["restrict_to_role"] else guild.default_role
        await bot.get_channel(inscriptions_channel_id).set_permissions(inscriptions_role, read_messages=True, send_messages=False, add_reactions=False)

    await bot.get_channel(inscriptions_channel_id).send(":clock1: **Les inscriptions sont fermées :** le bracket est désormais en cours de finalisation.")

    if tournoi["bulk_mode"]:
        await seed_participants(participants)

    try:
        scheduler.remove_job('dump_participants')
    except JobLookupError:
        pass
    finally:
        dump_participants()


async def check_in(member):
    participants[member.id]["checked_in"] = True
    try:
        await member.send("Tu as été check-in avec succès. Tu n'as plus qu'à patienter jusqu'au début du tournoi !")
    except discord.Forbidden:
        pass


### Prise en charge des inscriptions, désinscriptions, check-in et check-out
@bot.command(aliases=['in', 'out'])
@commands.check(inscriptions_still_open)
@commands.max_concurrency(1, wait=True)
async def participants_management(ctx):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if ctx.invoked_with == 'out':

        if ctx.channel.id in [check_in_channel_id, inscriptions_channel_id, inscriptions_vip_channel_id] and ctx.author.id in participants:
            await desinscrire(ctx.author)
            await ctx.message.add_reaction("✅")

        else:
            await ctx.message.add_reaction("🚫")

    elif ctx.invoked_with == 'in':

        if ctx.channel.id == check_in_channel_id and ctx.author.id in participants and tournoi["fin_check-in"] > datetime.datetime.now() > tournoi["début_check-in"]:
            await check_in(ctx.author)
            await ctx.message.add_reaction("✅")

        elif ctx.channel.id == inscriptions_channel_id and ctx.author.id not in participants and len(participants) < tournoi['limite']:
            await inscrire(ctx.author)
            await ctx.message.add_reaction("✅")

        elif ctx.channel.id == inscriptions_vip_channel_id and ctx.author.id not in participants and len(participants) < tournoi['limite']:
            await inscrire(ctx.author)
            await ctx.message.add_reaction("✅")

        else:
            await ctx.message.add_reaction("🚫")


### Nettoyer les channels liés aux tournois
async def purge_channels():
    guild = bot.get_guild(id=guild_id)

    for channel_id in [check_in_channel_id, queue_channel_id, scores_channel_id]:
        channel = guild.get_channel(channel_id)
        await channel.purge(limit=None)


### Nettoyer les catégories liées aux tournois
async def purge_categories():
    guild = bot.get_guild(id=guild_id)

    for category in [cat for cat in guild.categories if cat.name.lower() in ["winner bracket", "looser bracket"]]:
        for channel in category.channels: await channel.delete() # first, delete the channels
        await category.delete() # then delete the category


### Nettoyer les rôles liés aux tournois
async def purge_roles():
    guild = bot.get_guild(id=guild_id)
    challenger = guild.get_role(challenger_id)

    for member in challenger.members:
        try:
            await member.remove_roles(challenger)
        except (discord.HTTPException, discord.Forbidden):
            pass


### Affiche le bracket en cours
@bot.command(name='bracket')
@commands.check(tournament_is_underway_or_pending)
async def post_bracket(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    await ctx.send(f"{server_logo} **{tournoi['name']}** : {tournoi['url']}")


### Pile/face basique
@bot.command(name='flip', aliases=['flipcoin', 'coinflip', 'coin'])
async def flipcoin(ctx):
    await ctx.send(f"<@{ctx.author.id}> {random.choice(['Tu commences à faire les bans.', 'Ton adversaire commence à faire les bans.'])}")


### Ajout manuel
@bot.command(name='add')
@commands.check(is_owner_or_to)
@commands.check(tournament_is_pending)
async def add_inscrit(ctx):
    for member in ctx.message.mentions:
        await inscrire(member)
    dump_participants()
    await ctx.message.add_reaction("✅")


### Suppression/DQ manuel
@bot.command(name='rm')
@commands.check(is_owner_or_to)
@commands.check(tournament_is_underway_or_pending)
async def remove_inscrit(ctx):
    for member in ctx.message.mentions:
        await desinscrire(member)
    dump_participants()
    await ctx.message.add_reaction("✅")


### Se DQ soi-même
@bot.command(name='dq')
@commands.has_role(challenger_id)
@commands.check(tournament_is_underway)
@commands.cooldown(1, 30, type=commands.BucketType.user)
@commands.max_concurrency(1, wait=True)
async def self_dq(ctx):
    await desinscrire(ctx.author)
    await ctx.message.add_reaction("✅")


### Managing sets during tournament : launch & remind
### Goal : get the bracket only once to limit API calls
async def underway_tournament():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    guild = bot.get_guild(id=guild_id)
    bracket = await async_http_retry(achallonge.matches.index, tournoi["id"], state='open')
    await launch_matches(guild, bracket)
    await call_stream(guild, bracket)
    await rappel_matches(guild, bracket)
    await clean_channels(guild, bracket)


### Gestion des scores
@bot.command(name='win')
@in_channel(scores_channel_id)
@commands.check(tournament_is_underway)
@commands.has_role(challenger_id)
@commands.cooldown(1, 30, type=commands.BucketType.user)
@commands.max_concurrency(1, wait=True)
async def score_match(ctx, arg):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    winner = participants[ctx.author.id]["challonge"] # Le gagnant est celui qui poste

    try:
        match = await async_http_retry(
            achallonge.matches.index,
            tournoi['id'],
            state='open',
            participant_id=winner
        )
    except ChallongeException:
        await ctx.message.add_reaction("🕐")
        await ctx.send(f"<@{ctx.author.id}> Dû à une coupure de Challonge, je n'ai pas pu récupérer les données du set. Merci de retenter dans quelques instants.")
        return

    try:
        if match[0]["underway_at"] == None:
            await ctx.message.add_reaction("⚠️")
            await ctx.send(f"<@{ctx.author.id}> Le set pour lequel tu as donné le score n'a **pas encore commencé** !")
            return
    except IndexError:
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> Tu n'as pas de set prévu pour le moment, il n'y a donc pas de score à rentrer.")
        return

    try:
        score = re.search(r'([0-9]+) *\- *([0-9]+)', arg).group().replace(" ", "")
    except AttributeError:
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> **Ton score ne possède pas le bon format** *(3-0, 2-1, 3-2...)*, merci de le rentrer à nouveau.")
        return

    if score[0] < score[2]: score = score[::-1] # Le premier chiffre doit être celui du gagnant

    if is_bo5(match[0]["round"]):
        aimed_score, looser_score, temps_min = 3, [0, 1, 2], 10
    else:
        aimed_score, looser_score, temps_min = 2, [0, 1], 5

    debut_set = dateutil.parser.parse(str(match[0]["underway_at"])).replace(tzinfo=None)

    if int(score[0]) != aimed_score or int(score[2]) not in looser_score:
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> **Score incorrect**, vérifiez par exemple si le set doit se jouer en BO3 ou BO5.")
        return

    if datetime.datetime.now() - debut_set < datetime.timedelta(minutes = temps_min):
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> **Temps écoulé trop court** pour qu'un résultat soit déjà rentré pour le set.")
        return

    for joueur in participants:
        if participants[joueur]["challonge"] == match[0]["player2_id"]:
            player2 = joueur
            break

    og_score = score

    if winner == participants[player2]["challonge"]:
        score = score[::-1] # Le score doit suivre le format "player1-player2" pour scores_csv

    try:
        await async_http_retry(
            achallonge.matches.update,
            tournoi['id'],
            match[0]['id'],
            scores_csv=score,
            winner_id=winner
        )
        await ctx.message.add_reaction("✅")

    except ChallongeException:
        await ctx.message.add_reaction("🕐")
        await ctx.send(f"<@{ctx.author.id}> Dû à une coupure de Challonge, je n'ai pas pu envoyer ton score. Merci de retenter dans quelques instants.")

    else:
        gaming_channel = discord.utils.get(ctx.guild.text_channels, name=str(match[0]["suggested_play_order"]))

        if gaming_channel != None:
            await gaming_channel.send(f":bell: __Score rapporté__ : **{participants[ctx.author.id]['display_name']}** gagne **{og_score}** !\n"
                                      f"*En cas d'erreur, appelez un TO ! Un mauvais score intentionnel est passable de DQ et ban du tournoi.*\n"
                                      f"*Note : ce channel sera automatiquement supprimé 5 minutes à partir de la dernière activité.*")


### Clean channels
async def clean_channels(guild, bracket):

    play_orders = [match['suggested_play_order'] for match in bracket]

    for category, channels in guild.by_category():
        # Category must be a tournament category
        if category != None and category.name.lower() in ["winner bracket", "looser bracket"]:
            for channel in channels:
                # Channel names correspond to a suggested play order
                if int(channel.name) not in play_orders: # If the channel is not useful anymore
                    last_message = await channel.fetch_message(channel.last_message_id)
                    # Remove the channel if the last message is more than 5 minutes old
                    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    if now - last_message.created_at > datetime.timedelta(minutes = 5):
                        try:
                            await channel.delete()
                        except (discord.NotFound, discord.HTTPException):
                            pass


### Forfeit
@bot.command(name='forfeit', aliases=['ff', 'loose'])
@commands.check(tournament_is_underway)
@commands.has_role(challenger_id)
@commands.cooldown(1, 120, type=commands.BucketType.user)
@commands.max_concurrency(1, wait=True)
async def forfeit_match(ctx):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    looser = participants[ctx.author.id]["challonge"]

    try:
        match = await async_http_retry(
            achallonge.matches.index,
            tournoi['id'],
            state='open',
            participant_id=looser
        )
    except ChallongeException:
        await ctx.message.add_reaction("⚠️")
        return

    try:
        for joueur in participants:
            if participants[joueur]["challonge"] == match[0]["player1_id"]: player1 = joueur
            if participants[joueur]["challonge"] == match[0]["player2_id"]: player2 = joueur
    except IndexError:
        return

    if looser == participants[player2]["challonge"]:
        winner, score = participants[player1]["challonge"], "1-0"
    else:
        winner, score = participants[player2]["challonge"], "0-1"

    try:
        await async_http_retry(
            achallonge.matches.update,
            tournoi['id'],
            match[0]['id'],
            scores_csv=score,
            winner_id=winner
        )
    except ChallongeException:
        await ctx.message.add_reaction("⚠️")
    else:
        await ctx.message.add_reaction("✅")


### Get and return a category
async def get_available_category(match_round):
    guild = bot.get_guild(id=guild_id)
    desired_cat = 'winner bracket' if match_round > 0 else 'looser bracket'

    # by_category() doesn't return a category if it has no channels, so we use a list comprehension
    for category in [cat for cat in guild.categories if cat.name.lower() == desired_cat and len(cat.channels) < 50]:
        return category

    else:
        new_category = await guild.create_category(
            name=desired_cat,
            reason='Since no category was available, a new one was created'
        )
        # kwarg 'position' will be supported in next discord.py release, for now we have to edit
        await new_category.edit(position = guild.get_channel(tournoi_cat_id).position + 1)
        return new_category


### Lancer matchs ouverts
async def launch_matches(guild, bracket):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    sets = ""

    for match in [x for x in bracket if x["underway_at"] == None][:20:]: # "Only" lauch 20 max at once

        await async_http_retry(achallonge.matches.mark_as_underway, tournoi["id"], match["id"])

        for joueur in participants:
            if participants[joueur]["challonge"] == match["player1_id"]: player1 = guild.get_member(joueur)
            if participants[joueur]["challonge"] == match["player2_id"]: player2 = guild.get_member(joueur)

        top_8 = "(**top 8**) :fire:" if is_top8(match["round"]) else ""

        # Création d'un channel volatile pour le set
        try:
            gaming_channel = await guild.create_text_channel(
                str(match["suggested_play_order"]),
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.get_role(to_id): discord.PermissionOverwrite(read_messages=True),
                    guild.get_role(streamer_id): discord.PermissionOverwrite(read_messages=True),
                    player1: discord.PermissionOverwrite(read_messages=True),
                    player2: discord.PermissionOverwrite(read_messages=True)
                },
                category = await get_available_category(match['round']),
                topic = "Channel temporaire pour un set.",
                reason = f"Lancement du set n°{match['suggested_play_order']}"
            )

        except discord.HTTPException:
            gaming_channel_txt = f":video_game: Je n'ai pas pu créer de channel, faites votre set en MP ou dans <#{tournoi_channel_id}>."

            if is_queued_for_stream(match["suggested_play_order"]):
                await player1.send(f"Tu joueras on stream pour ton prochain set contre **{player2.display_name}** : je te communiquerai les codes d'accès quand ce sera ton tour.")
                await player2.send(f"Tu joueras on stream pour ton prochain set contre **{player1.display_name}** : je te communiquerai les codes d'accès quand ce sera ton tour.")

        else:
            gaming_channel_txt = f":video_game: Allez faire votre set dans le channel <#{gaming_channel.id}> !"

            with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

            gaming_channel_annonce = (f":arrow_forward: **{nom_round(match['round'])}** : <@{player1.id}> vs <@{player2.id}> {top_8}\n"
                                      f":white_small_square: Les règles du set doivent suivre celles énoncées dans <#{gamelist[tournoi['game']]['ruleset']}>.\n"
                                      f":white_small_square: La liste des stages légaux à l'heure actuelle est disponible via la commande `{bot_prefix}stages`.\n"
                                      f":white_small_square: En cas de lag qui rend la partie injouable, utilisez la commande `{bot_prefix}lag` pour résoudre la situation.\n"
                                      f":white_small_square: **Dès que le set est terminé**, le gagnant envoie le score dans <#{scores_channel_id}> avec la commande `{bot_prefix}win`.\n\n"
                                      f":game_die: **{random.choice([player1.display_name, player2.display_name])}** est tiré au sort pour commencer le ban des stages *({gamelist[tournoi['game']]['ban_instruction']})*.\n")

            if tournoi["game"] == "Project+":
                gaming_channel_annonce += f"{gamelist[tournoi['game']]['icon']} **Minimum buffer suggéré** : le host peut le faire calculer avec la commande `{bot_prefix}buffer [ping]`.\n"

            if is_bo5(match["round"]):
                gaming_channel_annonce += ":five: Vous devez jouer ce set en **BO5** *(best of five)*.\n"
            else:
                gaming_channel_annonce += ":three: Vous devez jouer ce set en **BO3** *(best of three)*.\n"

            if not is_top8(match["round"]):
                scheduler.add_job(
                    check_channel_activity,
                    id = f'check activity of set {gaming_channel.name}',
                    args = [gaming_channel, player1, player2],
                    run_date = datetime.datetime.now() + datetime.timedelta(minutes = tournoi["check_channel_presence"])
                )

            if is_queued_for_stream(match["suggested_play_order"]):
                gaming_channel_annonce += ":tv: **Vous jouerez on stream**. Dès que ce sera votre tour, je vous communiquerai les codes d'accès."

            await gaming_channel.send(gaming_channel_annonce)

        on_stream = "(**on stream**) :tv:" if is_queued_for_stream(match["suggested_play_order"]) else ""
        bo_type = 'BO5' if is_bo5(match['round']) else 'BO3'

        sets += f":arrow_forward: **{nom_round(match['round'])}** ({bo_type}) : <@{player1.id}> vs <@{player2.id}> {on_stream}\n{gaming_channel_txt} {top_8}\n\n"

    if sets != "":
        if len(sets) < 2000:
            await bot.get_channel(queue_channel_id).send(sets)
        else: # Discord doesn't deal with more than 2000 characters
            sets = [x.strip() for x in sets.split('\n\n') if x.strip() != ''] # so we have to split
            while sets:
                await bot.get_channel(queue_channel_id).send('\n\n'.join(sets[:10]))
                del sets[:10] # and send by groups of ten sets


async def check_channel_activity(channel, player1, player2):
    player1_is_active, player2_is_active = False, False

    try:
        async for message in channel.history():
            if message.author.id == player1.id:
                player1_is_active = True
            if message.author.id == player2.id:
                player2_is_active = True
            if player1_is_active and player2_is_active:
                return
    except discord.NotFound:
        return

    if player1_is_active == False:
        await channel.send(f":timer: **DQ automatique de <@{player1.id}> pour inactivité** : aucune manifestation à temps du joueur.")
        await desinscrire(player1)
        await bot.get_channel(to_channel_id).send(f":information_source: **DQ automatique** de <@{player1.id}> pour inactivité, set n°{channel.name}.")
        await player1.send("Désolé, tu as été DQ automatiquement car tu n'as pas été actif sur ton channel de set dans les premières minutes qui ont suivi son lancement.")

    if player2_is_active == False:
        await channel.send(f":timer: **DQ automatique de <@{player2.id}> pour inactivité** : aucune manifestation à temps du joueur.")
        await desinscrire(player2)
        await bot.get_channel(to_channel_id).send(f":information_source: **DQ automatique** de <@{player2.id}> pour inactivité, set n°{channel.name}.")
        await player2.send("Désolé, tu as été DQ automatiquement car tu n'as pas été actif sur ton channel de set dans les premières minutes qui ont suivi son lancement.")


@bot.command(name='initstream', aliases=['is'])
@commands.has_role(streamer_id)
@commands.check(tournament_is_underway_or_pending)
async def init_stream(ctx, arg):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)

    if re.compile(r"^(https?\:\/\/)?(www.twitch.tv)\/.+$").match(arg):
        stream[ctx.author.id] = {
            'channel': arg.replace("https://www.twitch.tv/", ""),
            'access': ['N/A', 'N/A'],
            'on_stream': None,
            'queue': []
        }
        with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
        await ctx.message.add_reaction("✅")
    else:
        await ctx.message.add_reaction("🔗")


@bot.command(name='stopstream')
@commands.has_role(streamer_id)
@commands.check(tournament_is_underway_or_pending)
@commands.check(is_streaming)
async def stop_stream(ctx):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)
    del stream[ctx.author.id]
    with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
    await ctx.message.add_reaction("✅")


@bot.command(name='stream', aliases=['twitch', 'tv'])
@commands.check(tournament_is_underway_or_pending)
async def post_stream(ctx):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)

    if len(stream) == 0:
        await ctx.send(f"<@{ctx.author.id}> Il n'y a pas de stream en cours (ou prévu) pour ce tournoi à l'heure actuelle.")
    
    elif len(stream) == 1:
        await ctx.send(f"<@{ctx.author.id}> https://www.twitch.tv/{stream[next(iter(stream))]['channel']}")

    else:
        multitwitch = 'http://www.multitwitch.tv/' + '/'.join([stream[x]['channel'] for x in stream])
        await ctx.send(f"<@{ctx.author.id}> {multitwitch}")


### Ajout ID et MDP d'arène de stream
@bot.command(name='setstream', aliases=['ss'])
@commands.has_role(streamer_id)
@commands.check(tournament_is_underway_or_pending)
@commands.check(is_streaming)
async def setup_stream(ctx, *args):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)

    if tournoi['game'] == 'Super Smash Bros. Ultimate' and len(args) == 2:
        stream[ctx.author.id]["access"] = args

    elif tournoi['game'] == 'Project+' and len(args) == 1:
        stream[ctx.author.id]["access"] = args

    else:
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> Paramètres invalides pour le jeu **{tournoi['game']}**.")
        return

    with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
    await ctx.message.add_reaction("✅")


### Ajouter un set dans la stream queue
@bot.command(name='addstream', aliases=['as'])
@commands.has_role(streamer_id)
@commands.check(tournament_is_underway_or_pending)
@commands.check(is_streaming)
@commands.max_concurrency(1, wait=True)
async def add_stream(ctx, *args: int):

    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    # Pre-add before the tournament goes underway - BE CAREFUL!
    if tournoi["statut"] == "pending":
        for arg in args: stream[ctx.author.id]["queue"].append(arg)
        with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
        await ctx.message.add_reaction("✅")
        await ctx.send(f"<@{ctx.author.id}> Sets ajoutés à la stream queue : toutefois ils n'ont pas été vérifiés, le bracket n'ayant pas commencé.")
        return

    # Otherwise we should check if the sets are open
    try:
        bracket = await async_http_retry(achallonge.matches.index, tournoi['id'], state=('open', 'pending'))
    except ChallongeException:
        await ctx.message.add_reaction("🕐")
        return

    for arg in args:
        for match in bracket:
            if (match["suggested_play_order"] == arg) and (match["underway_at"] == None) and (not is_queued_for_stream(arg)):
                stream[ctx.author.id]["queue"].append(arg)
                break

    with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
    await ctx.message.add_reaction("✅")


### Enlever un set de la stream queue
@bot.command(name='rmstream', aliases=['rs'])
@commands.has_role(streamer_id)
@commands.check(tournament_is_underway_or_pending)
@commands.check(is_streaming)
async def remove_stream(ctx, *args: int):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)

    try:
        for arg in args: stream[ctx.author.id]["queue"].remove(arg)
    except ValueError:
        await ctx.message.add_reaction("⚠️")
    else:
        with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
        await ctx.message.add_reaction("✅")


### Interchanger 2 sets de la stream queue
@bot.command(name='swapstream', aliases=['sws'])
@commands.has_role(streamer_id)
@commands.check(tournament_is_underway_or_pending)
@commands.check(is_streaming)
async def swap_stream(ctx, arg1: int, arg2: int):
    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)

    try:
        x, y = stream[ctx.author.id]["queue"].index(arg1), stream[ctx.author.id]["queue"].index(arg2)
    except ValueError:
        await ctx.message.add_reaction("⚠️")
    else:
        stream[ctx.author.id]["queue"][y], stream[ctx.author.id]["queue"][x] = stream[ctx.author.id]["queue"][x], stream[ctx.author.id]["queue"][y]
        with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
        await ctx.message.add_reaction("✅")


### Infos stream
@bot.command(name='mystream', aliases=['ms'])
@commands.has_role(streamer_id)
@commands.check(tournament_is_underway_or_pending)
@commands.check(is_streaming)
@commands.max_concurrency(1, wait=True)
async def list_stream(ctx):

    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        bracket = await async_http_retry(achallonge.matches.index, tournoi['id'], state=('open', 'pending'))
    except ChallongeException:
        await ctx.message.add_reaction("🕐")
        return

    msg = f":information_source: Codes d'accès au stream **{stream[ctx.author.id]['channel']}** :\n{get_access_stream(stream[ctx.author.id]['access'])}\n"

    try:
        match = bracket[[x["suggested_play_order"] for x in bracket].index(stream[ctx.author.id]['on_stream'])]
    except KeyError: # bracket is empty
        msg += ":stop_button: Le tournoi n'est probablement pas en cours.\n"
    except ValueError: # on stream not found
        msg += ":stop_button: Aucun set on stream à l'heure actuelle.\n"
    else:
        for joueur in participants:
            if participants[joueur]["challonge"] == match["player1_id"]: player1 = participants[joueur]['display_name']
            if participants[joueur]["challonge"] == match["player2_id"]: player2 = participants[joueur]['display_name']

        msg += f":arrow_forward: **Set on stream actuel** *({match['suggested_play_order']})* : **{player1}** vs **{player2}**\n"

    list_stream = ""

    for order in stream[ctx.author.id]['queue']:
        for match in bracket:
            if match["suggested_play_order"] == order:

                player1, player2 = "(?)", "(?)"
                for joueur in participants:
                    if participants[joueur]["challonge"] == match["player1_id"]:
                        player1 = participants[joueur]['display_name']
                    if participants[joueur]["challonge"] == match["player2_id"]:
                        player2 = participants[joueur]['display_name']

                list_stream += f":white_small_square: **{match['suggested_play_order']}** : *{player1}* vs *{player2}*\n"
                break

    if list_stream != "":
        msg += f":play_pause: Liste des sets prévus pour passer on stream :\n{list_stream}"
    else:
        msg += ":play_pause: Il n'y a aucun set prévu pour passer on stream."

    await ctx.send(msg)


### Appeler les joueurs on stream
async def call_stream(guild, bracket):

    with open(stream_path, 'r+') as f: stream = json.load(f, object_pairs_hook=int_keys)

    play_orders = [match["suggested_play_order"] for match in bracket]

    for streamer in stream:

        # If current on stream set is still open, then it's not finished
        if stream[streamer]["on_stream"] in play_orders: continue

        try:
            match = bracket[play_orders.index(stream[streamer]["queue"][0])]
        except (IndexError, ValueError): # stream queue is empty / match could be pending
            continue
        else: # wait for the match to be marked as underway
            if match["underway_at"] == None: continue

        for joueur in participants:
            if participants[joueur]["challonge"] == match["player1_id"]: player1 = guild.get_member(joueur)
            if participants[joueur]["challonge"] == match["player2_id"]: player2 = guild.get_member(joueur)

        gaming_channel = discord.utils.get(guild.text_channels, name=str(match["suggested_play_order"]))

        if gaming_channel == None:
            dm_msg = f"C'est ton tour de passer on stream ! Voici les codes d'accès :\n{get_access_stream(stream[streamer]['access'])}"
            await player1.send(dm_msg)
            await player2.send(dm_msg)
        else:
            await gaming_channel.send(f"<@{player1.id}> <@{player2.id}>\n" # ping them
                                      f":clapper: Vous pouvez passer on stream sur la chaîne **{stream[streamer]['channel']}** ! "
                                      f"Voici les codes d'accès :\n{get_access_stream(stream[streamer]['access'])}")

        await bot.get_channel(stream_channel_id).send(f":arrow_forward: Envoi on stream du set n°{match['suggested_play_order']} chez **{stream[streamer]['channel']}** : "
                                                      f"**{participants[player1.id]['display_name']}** vs **{participants[player2.id]['display_name']}** !")

        stream[streamer]["on_stream"] = match["suggested_play_order"]

        while match["suggested_play_order"] in stream[streamer]["queue"]:
            stream[streamer]["queue"].remove(match["suggested_play_order"])

        with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)


### Calculer les rounds à partir desquels un set est top 8 (bracket D.E.)
async def calculate_top8():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    bracket = await async_http_retry(achallonge.matches.index, tournoi['id'], state=("open", "pending"))

    # Get all rounds from bracket
    rounds = [match["round"] for match in bracket]

    # Calculate top 8
    tournoi["round_winner_top8"] = max(rounds) - 2
    tournoi["round_looser_top8"] = min(rounds) + 3

    # Minimal values, in case of a small tournament
    if tournoi["round_winner_top8"] < 1: tournoi["round_winner_top8"] = 1
    if tournoi["round_looser_top8"] > -1: tournoi["round_looser_top8"] = -1

    # Calculate start_bo5
    if tournoi["start_bo5"] > 0:
        tournoi["round_winner_bo5"] = tournoi["round_winner_top8"] + tournoi["start_bo5"] - 1
    elif tournoi["start_bo5"] in [0, -1]:
        tournoi["round_winner_bo5"] = tournoi["round_winner_top8"] + tournoi["start_bo5"]
    else:
        tournoi["round_winner_bo5"] = tournoi["round_winner_top8"] + tournoi["start_bo5"] + 1

    if tournoi["start_bo5"] > 1:
        tournoi["round_looser_bo5"] = min(rounds) # top 3 is LF anyway
    else:
        tournoi["round_looser_bo5"] = tournoi["round_looser_top8"] - tournoi["start_bo5"]

    # Avoid aberrant values
    if tournoi["round_winner_bo5"] > max(rounds): tournoi["round_winner_bo5"] = max(rounds)
    if tournoi["round_winner_bo5"] < 1: tournoi["round_winner_bo5"] = 1
    if tournoi["round_looser_bo5"] < min(rounds): tournoi["round_looser_bo5"] = min(rounds)
    if tournoi["round_looser_bo5"] > -1: tournoi["round_looser_bo5"] = -1

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)


### Lancer un rappel de matchs
async def rappel_matches(guild, bracket):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    for match in bracket:

        if (match["underway_at"] != None) and (not is_queued_for_stream(match["suggested_play_order"])) and (not is_on_stream(match["suggested_play_order"])):

            debut_set = dateutil.parser.parse(str(match["underway_at"])).replace(tzinfo=None)

            if tournoi['game'] == 'Super Smash Bros. Ultimate':
                seuil = 42 if is_bo5(match["round"]) else 28 # Calculé selon (tps max match * nb max matchs) + 7 minutes
            elif tournoi['game'] == 'Project+':
                seuil = 47 if is_bo5(match["round"]) else 31 # Idem
            else:
                return

            if datetime.datetime.now() - debut_set > datetime.timedelta(minutes = seuil):

                gaming_channel = discord.utils.get(guild.text_channels, name=str(match["suggested_play_order"]))

                if gaming_channel != None:

                    for joueur in participants:
                        if participants[joueur]["challonge"] == match["player1_id"]: player1 = guild.get_member(joueur)
                        if participants[joueur]["challonge"] == match["player2_id"]: player2 = guild.get_member(joueur)

                    # Avertissement unique
                    if match["suggested_play_order"] not in tournoi["warned"]:

                        tournoi["warned"].append(match["suggested_play_order"])
                        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

                        alerte = (f":timer: **Ce set n'a toujours pas reçu de score !** <@{player1.id}> <@{player2.id}>\n"
                                  f":white_small_square: Le gagnant du set est prié de le poster dans <#{scores_channel_id}> dès que possible.\n"
                                  f":white_small_square: Dans une dizaine de minutes, les TOs seront alertés qu'une décision doit être prise.\n"
                                  f":white_small_square: Si une personne est détectée comme inactive, elle sera **DQ automatiquement** du tournoi.\n")

                        await gaming_channel.send(alerte)

                    # DQ pour inactivité (exceptionnel...) -> fixé à 10 minutes après l'avertissement
                    elif (match["suggested_play_order"] not in tournoi["timeout"]) and (datetime.datetime.now() - debut_set > datetime.timedelta(minutes = seuil + 10)):

                        tournoi["timeout"].append(match["suggested_play_order"])
                        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

                        async for message in gaming_channel.history(): # Rechercher qui est la dernière personne active du channel

                            if (message.author != bot.user) and (to_id not in [y.id for y in message.author.roles]): # La personne ne doit être ni un bot ni un TO, donc un joueur

                                try:
                                    winner
                                except NameError:
                                    winner, winner_last_activity = message.author, message.created_at # Le premier résultat sera assigné à winner
                                else:
                                    if message.author != winner:
                                        looser, looser_last_activity = message.author, message.created_at # Le second résultat sera assigné à looser
                                        break

                        try:
                            winner
                        except NameError: # S'il n'y a jamais eu de résultat, aucun joueur n'a donc été actif : DQ des deux 
                            await gaming_channel.send(f"<@&{to_id}> **DQ automatique des __2 joueurs__ pour inactivité : <@{player1.id}> & <@{player2.id}>**")
                            await async_http_retry(achallonge.participants.destroy, tournoi["id"], participants[player1.id]['challonge'])
                            await async_http_retry(achallonge.participants.destroy, tournoi["id"], participants[player2.id]['challonge'])
                            continue

                        try:
                            looser
                        except NameError: # S'il n'y a pas eu de résultat pour un second joueur différent : DQ de l'inactif
                            looser = player2 if winner.id == player1.id else player1
                            await gaming_channel.send(f"<@&{to_id}> **DQ automatique de <@{looser.id}> pour inactivité.**")
                            await async_http_retry(achallonge.participants.destroy, tournoi["id"], participants[looser.id]['challonge'])
                            continue

                        if winner_last_activity - looser_last_activity > datetime.timedelta(minutes = 10): # Si différence d'inactivité de plus de 10 minutes
                            await gaming_channel.send(f"<@&{to_id}> **Une DQ automatique a été executée pour inactivité :**\n-<@{winner.id}> passe au round suivant.\n-<@{looser.id}> est DQ du tournoi.")
                            await async_http_retry(achallonge.participants.destroy, tournoi["id"], participants[looser.id]['challonge'])

                        else: # Si pas de différence notable, demander une décision manuelle
                            await gaming_channel.send(f"<@&{to_id}> **Durée anormalement longue détectée** pour ce set, une décision d'un TO doit être prise")

                        await bot.get_channel(to_channel_id).send(f":information_source: Le set du channel <#{gaming_channel.id}> prend anormalement du temps, une intervention est peut-être nécessaire.")


### Obtenir stagelist
@bot.command(name='stages', aliases=['stage', 'stagelist', 'ban', 'bans', 'map', 'maps'])
@commands.check(tournament_is_underway_or_pending)
async def get_stagelist(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    msg = f":map: **Stages légaux pour {tournoi['game']} :**\n:white_small_square: __Starters__ :\n"
    for stage in gamelist[tournoi['game']]['starters']: msg += f"- {stage}\n"

    if 'counterpicks' in gamelist[tournoi['game']]:
        msg += ":white_small_square: __Counterpicks__ :\n"
        for stage in gamelist[tournoi['game']]['counterpicks']: msg += f"- {stage}\n"

    await ctx.send(msg)


### Obtenir ruleset
@bot.command(name='ruleset', aliases=['rules'])
@commands.check(tournament_is_underway_or_pending)
async def get_ruleset(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)
    await ctx.send(f"<@{ctx.author.id}> Le ruleset est disponible ici : <#{gamelist[tournoi['game']]['ruleset']}>")


### Lag
@bot.command(name='lag')
@commands.has_role(challenger_id)
@in_combat_channel()
@commands.cooldown(1, 120, type=commands.BucketType.channel)
async def send_lag_text(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    msg = lag_text

    if tournoi['game'] == 'Project+':
        msg += (f"\n{gamelist[tournoi['game']]['icon']} **Spécificités Project+ :**\n"
                f":white_small_square: Vérifier que le PC fait tourner le jeu de __manière fluide (60 FPS constants)__, sinon :\n"
                f"- Baisser la résolution interne dans les paramètres graphiques.\n"
                f"- Désactiver les textures HD, l'anti-aliasing, s'ils ont été activés.\n"
                f"- Windows seulement : changer le backend pour *Direct3D9* (le + fluide) ou *Direct3D11* (+ précis que D9)\n"
                f":white_small_square: Vérifier que la connexion est __stable et suffisamment rapide__ :\n"
                f"- Le host peut augmenter le \"minimum buffer\" de 6 à 8 : utilisez la commande `{bot_prefix}buffer` en fournissant votre ping.\n"
                f"- Suivre les étapes génériques contre le lag, citées ci-dessus.\n"
                f":white_small_square: Utilisez la commande `{bot_prefix}desync` en cas de desync suspectée.")

    await bot.get_channel(to_channel_id).send(f":satellite: **Lag reporté** : les TOs sont invités à consulter le channel <#{ctx.channel.id}>")
    await ctx.send(msg)


### Calculate recommended minimum buffer
@bot.command(name='buffer')
async def calculate_buffer(ctx, arg: int):

    theoretical_buffer = arg // 8 + (arg % 8 > 0)
    suggested_buffer = theoretical_buffer if theoretical_buffer >= 4 else 4

    await ctx.send(f"<@{ctx.author.id}> Minimum buffer (host) suggéré pour Dolphin Netplay : **{suggested_buffer}**.\n"
                   f"*Si du lag persiste, il y a un problème de performance : montez le buffer tant que nécessaire.*")


### Annoncer les résultats
async def annonce_resultats():

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    participants, resultats = await async_http_retry(achallonge.participants.index, tournoi["id"]), []

    if len(participants) < 8:
        await bot.get_channel(resultats_channel_id).send(f"{server_logo} Résultats du **{tournoi['name']}** : {tournoi['url']}")
        return

    for joueur in participants:
        resultats.append((joueur['final_rank'], joueur['display_name']))

    resultats.sort()
    top6 = ' / '.join([y for x, y in resultats if x == 5])
    top8 = ' / '.join([y for x, y in resultats if x == 7])

    ending = random.choice([
        "Bien joué à tous ! Quant aux autres : ne perdez pas espoir, ce sera votre tour un jour...",
        "Merci à tous d'avoir participé, on se remet ça très bientôt ! Prenez soin de vous.",
        "Félicitations à eux. N'oubliez pas que la clé est la persévérance ! Croyez toujours en vous.",
        "Ce fut un plaisir en tant que bot d'aider à la gestion de ce tournoi et d'assister à vos merveileux sets."
    ])
    
    classement = (f"{server_logo} **__Résultats du tournoi {tournoi['name']}__**\n\n"
                  f":trophy: **1er** : **{resultats[0][1]}**\n"
                  f":second_place: **2e** : {resultats[1][1]}\n"
                  f":third_place: **3e** : {resultats[2][1]}\n"
                  f":medal: **4e** : {resultats[3][1]}\n"
                  f":reminder_ribbon: **5e** : {top6}\n"
                  f":reminder_ribbon: **7e** : {top8}\n\n"
                  f":bar_chart: {len(participants)} entrants\n"
                  f"{gamelist[tournoi['game']]['icon']} {tournoi['game']}\n"
                  f":link: **Bracket :** {tournoi['url']}\n\n"
                  f"{ending}")
    
    await bot.get_channel(resultats_channel_id).send(classement)


### Ajouter un rôle
async def attribution_role(event):
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    for game in gamelist:

        if event.emoji.name == re.search(r'\:(.*?)\:', gamelist[game]['icon']).group(1):
            role = event.member.guild.get_role(gamelist[game]['role'])

            try:
                await event.member.add_roles(role)
                await event.member.send(f"Le rôle **{role.name}** t'a été attribué avec succès : tu recevras des informations concernant les tournois *{game}* !")
            except (discord.HTTPException, discord.Forbidden):
                pass

        elif event.emoji.name == gamelist[game]['icon_1v1']:
            role = event.member.guild.get_role(gamelist[game]['role_1v1'])

            try:
                await event.member.add_roles(role)
                await event.member.send(f"Le rôle **{role.name}** t'a été attribué avec succès : tu seras contacté si un joueur cherche des combats sur *{game}* !")
            except (discord.HTTPException, discord.Forbidden):
                pass


### Enlever un rôle
async def retirer_role(event):
    with open(gamelist_path, 'r+') as f: gamelist = yaml.full_load(f)

    guild = bot.get_guild(id=guild_id) # due to event.member not being available

    for game in gamelist:

        if event.emoji.name == re.search(r'\:(.*?)\:', gamelist[game]['icon']).group(1):
            role, member = guild.get_role(gamelist[game]['role']), guild.get_member(event.user_id)

            try:
                await member.remove_roles(role)
                await member.send(f"Le rôle **{role.name}** t'a été retiré avec succès : tu ne recevras plus les informations concernant les tournois *{game}*.")
            except (discord.HTTPException, discord.Forbidden):
                pass

        elif event.emoji.name == gamelist[game]['icon_1v1']:
            role, member = guild.get_role(gamelist[game]['role_1v1']), guild.get_member(event.user_id)

            try:
                await member.remove_roles(role)
                await member.send(f"Le rôle **{role.name}** t'a été retiré avec succès : tu ne seras plus contacté si un joueur cherche des combats sur *{game}*.")
            except (discord.HTTPException, discord.Forbidden):
                pass


### À chaque ajout de réaction
@bot.event
async def on_raw_reaction_add(event):
    if event.user_id == bot.user.id: return

    elif (event.emoji.name == "✅") and (event.channel_id == inscriptions_channel_id):

        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if tournoi["reaction_mode"] and event.message_id == tournoi["annonce_id"]:
            await inscrire(event.member) # available for REACTION_ADD only

    elif (manage_game_roles == True) and (event.channel_id == roles_channel_id):
        await attribution_role(event)


### À chaque suppression de réaction
@bot.event
async def on_raw_reaction_remove(event):
    if event.user_id == bot.user.id: return

    elif (event.emoji.name == "✅") and (event.channel_id == inscriptions_channel_id):

        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if tournoi["reaction_mode"] and event.message_id == tournoi["annonce_id"]:
            await desinscrire(bot.get_guild(id=guild_id).get_member(event.user_id)) # event.member not available for REACTION_REMOVE

    elif (manage_game_roles == True) and (event.channel_id == roles_channel_id):
        await retirer_role(event)


### Help message
@bot.command(name='help', aliases=['info', 'version'])
@commands.cooldown(1, 30, type=commands.BucketType.user)
async def send_help(ctx):
    await ctx.send(f"**{name} {version}** - *Made by {author} with* :heart:\n{help_text}\n")
    author_roles = [y.id for y in ctx.author.roles]
    if challenger_id in author_roles: await ctx.send(challenger_help_text) # challenger help
    if to_id in author_roles or await ctx.bot.is_owner(ctx.author): await ctx.send(admin_help_text) # admin help
    if streamer_id in author_roles: await ctx.send(streamer_help_text) # streamer help


### Set preference
@bot.command(name='set', aliases=['turn'])
@commands.check(is_owner_or_to)
async def set_preference(ctx, arg1, arg2):
    with open(preferences_path, 'r+') as f: preferences = yaml.full_load(f)

    try:
        if isinstance(preferences[arg1.lower()], bool):
            if arg2.lower() in ["true", "on"]:
                preferences[arg1.lower()] = True 
            elif arg2.lower() in ["false", "off"]:
                preferences[arg1.lower()] = False
            else:
                raise ValueError
        elif isinstance(preferences[arg1.lower()], int):
            preferences[arg1.lower()] = int(arg2)

    except KeyError:
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> **Paramètre inconnu :** `{arg1}`.")

    except ValueError:
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> **Valeur incorrecte :** `{arg2}`.")

    else:
        with open(preferences_path, 'w') as f: yaml.dump(preferences, f)
        await ctx.message.add_reaction("✅")
        await ctx.send(f"<@{ctx.author.id}> **Paramètre changé :** `{arg1} = {arg2}`.")


### See preferences
@bot.command(name='settings', aliases=['preferences', 'config'])
@commands.check(is_owner_or_to)
async def check_settings(ctx):
    with open(preferences_path, 'r+') as f: preferences = yaml.full_load(f)

    parametres = ""
    for parametre in preferences:
        parametres += f":white_small_square: **{parametre}** : *{preferences[parametre]}*\n"

    await ctx.send(f":gear: __Liste des paramètres modifiables sans redémarrage__ :\n{parametres}\n"
                   f"Vous pouvez modifier chacun de ces paramètres avec la commande `{bot_prefix}set [paramètre] [valeur]`.\n"
                   f"*Ces paramètres ne s'appliquent qu'au moment de la création d'un tournoi, et ne peuvent pas changer jusqu'à sa fin.*")


### Desync message
@bot.command(name='desync')
@commands.cooldown(1, 30, type=commands.BucketType.user)
async def send_desync_help(ctx):
    await ctx.send(desync_text)


### On command error : invoker has not enough permissions
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CheckFailure, commands.MissingRole, commands.NotOwner)):
        log.debug(f"Detected check failure for {ctx.command.name}", exc_info=error)
        await ctx.message.add_reaction("🚫")
    elif isinstance(error, (commands.MissingRequiredArgument, commands.ArgumentParsingError, commands.BadArgument)):
        await ctx.message.add_reaction("💿")
        await ctx.send(f"<@{ctx.author.id}> Les paramètres de cette commande sont mal renseignés. Utilise `{bot_prefix}help` pour en savoir plus.", delete_after=10)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.message.add_reaction("❄️")
        await ctx.send(f"<@{ctx.author.id}> **Cooldown** : cette commande sera de nouveau disponible pour toi dans {int(error.retry_after)} secondes.", delete_after=error.retry_after)
    elif isinstance(error, commands.CommandNotFound) and show_unknown_command:
        await ctx.message.add_reaction("❔")
        await ctx.send(f"<@{ctx.author.id}> Voulais-tu écrire autre chose ? Utilise `{bot_prefix}help` pour avoir la liste des commandes.", delete_after=10)
    elif isinstance(error, commands.CommandInvokeError):
        log.error(f"Error while executing command {ctx.command.name}", exc_info=error)
        await ctx.message.add_reaction("⚠️")

@bot.event
async def on_error(event, *args, **kwargs):
    exception = sys.exc_info()
    log.error(f"Unhandled exception with {event}", exc_info=exception)


if __name__ == '__main__':
    # loggers initialization
    if debug_mode:
        level = 10
    else:
        level = 20
    init_loggers(level, Path("./data/logs/"))
    log.info(f"A.T.O.S. Version {version}")
    #### Scheduler
    scheduler.start()
    ### Add base cogs
    for extension in initial_extensions:
        bot.load_extension(extension)
    #### Lancement du bot
    try:
        bot.run(bot_secret, bot = True, reconnect = True)
    except KeyboardInterrupt:
        log.info("Crtl-C detected, shutting down...")
        bot.logout()
    except Exception as e:
        log.critical("Unhandled exception.", exc_info=e)
    finally:
        log.info("Shutting down...")
        dump_participants()
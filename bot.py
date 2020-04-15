import discord, random, logging, os, json, re, challonge, dateutil.parser, dateutil.relativedelta, datetime, time, asyncio, yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from babel.dates import format_date, format_time
from discord.ext import commands

# Custom modules
from utils.json_hooks import dateconverter, dateparser, int_keys
from utils.command_checks import tournament_is_pending, tournament_is_underway, tournament_is_underway_or_pending, in_channel, can_check_in
from utils.rounds import is_top8, nom_round
from utils.game_specs import get_access_stream

# Import configuration (variables only)
from utils.get_config import *

# Import raw texts (variables only)
from utils.raw_texts import *

if debug_mode == True: logging.basicConfig(level=logging.DEBUG)

#### Infos
version = "5.1"
author = "Wonderfall"
name = "A.T.O.S."

### Init things
bot = commands.Bot(command_prefix=commands.when_mentioned_or(bot_prefix)) # Set prefix for commands
bot.remove_command('help') # Remove default help command to set our own
challonge.set_credentials(challonge_user, challonge_api_key)
scheduler = AsyncIOScheduler()


#### Notifier de l'initialisation
@bot.event
async def on_ready():
    print(f"-------------------------------------")
    print(f"           A.T.O.S. {version}        ")
    print(f"        Automated TO for Smash       ")
    print(f"                                     ")
    print(f"Logged on Discord as...              ")
    print(f"User : {bot.user.name}               ")
    print(f"ID   : {bot.user.id}                 ")
    print(f"-------------------------------------")
    await bot.change_presence(activity=discord.Game(version)) # As of April 2020, CustomActivity is not supported for bots
    #scheduler.add_job(auto_mode, 'interval', id='auto_mode', minutes=10, replace_existing=True)
    await reload_tournament()


### A chaque arrivée de membre
@bot.event
async def on_member_join(member):

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

    try:
        infos = challonge.tournaments.show(url_or_id)
    except:
        return

    tournoi = {
        "name": infos["name"],
        "game": infos["game_name"].title(), # Non-recognized games are lowercase for Challonge
        "url": infos["full_challonge_url"],
        "id": infos["id"],
        "limite": infos["signup_cap"],
        "statut": infos["state"],
        "début_tournoi": dateutil.parser.parse(str(infos["start_at"])).replace(tzinfo=None),
        "début_check-in": dateutil.parser.parse(str(infos["start_at"])).replace(tzinfo=None) - datetime.timedelta(hours = 1),
        "fin_check-in": dateutil.parser.parse(str(infos["start_at"])).replace(tzinfo=None) - datetime.timedelta(minutes = 10),
        "on_stream": None,
        "stream": ["N/A", "N/A"],
        "warned": [],
        "timeout": []
    }

    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)
    if (datetime.datetime.now() > tournoi["début_tournoi"]) or (tournoi['game'] not in stagelist): return

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
    with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
    with open(waiting_list_path, 'w') as f: json.dump({}, f, indent=4)
    with open(stream_path, 'w') as f: json.dump([], f, indent=4)

    await annonce_inscription()

    scheduler.add_job(start_check_in, id='start_check_in', run_date=tournoi["début_check-in"], replace_existing=True)
    scheduler.add_job(end_check_in, id='end_check_in', run_date=tournoi["fin_check-in"], replace_existing=True)

    await bot.change_presence(activity=discord.Game(f"{version} • {tournoi['name']}"))


### Ajouter un tournoi
@bot.command(name='setup')
@commands.has_role(to_id)
async def setup_tournament(ctx, arg):

    if re.compile("^(https?\:\/\/)?(challonge.com)\/.+$").match(arg):
        await init_tournament(arg.replace("https://challonge.com/", ""))
    else:
        await ctx.message.add_reaction("🔗")

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        tournoi["début_tournoi"]
    except KeyError:
        await ctx.message.add_reaction("⚠️")
    else:
        await ctx.message.add_reaction("✅")


### AUTO-MODE : will take care of creating tournaments for you
@scheduler.scheduled_job('interval', id='auto_mode', minutes=10)
async def auto_mode():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(auto_mode_path, 'r+') as f: tournaments = yaml.full_load(f)

    #  Auto-mode won't run if at least one of these conditions is met :
    #    - It's turned off in config.yml (default)
    #    - A tournament is already initialized
    #    - It's "night" time

    if (auto_mode == False) or (tournoi != {}) or (not 10 < datetime.datetime.now().hour < 21): return

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
                minute = dateutil.parser.parse(tournaments[tournament]["start"]).minute
            )

            # If the tournament is supposed to be in less than 36 hours, let's go !
            if abs(next_date - datetime.datetime.now().astimezone()) < datetime.timedelta(hours = 36):

                new_tournament = challonge.tournaments.create(
                    name = f"{tournament} #{tournaments[tournament]['edition']}",
                    url = f"{re.sub('[^A-Za-z0-9]+', '', tournament)}{tournaments[tournament]['edition']}",
                    tournament_type = "double elimination",
                    show_rounds = True,
                    description = tournaments[tournament]['description'],
                    signup_cap = tournaments[tournament]['capping'],
                    game_name = tournaments[tournament]['game'],
                    start_at = next_date
                )

                tournaments[tournament]["edition"] += 1
                with open(auto_mode_path, 'w') as f: yaml.dump(tournaments, f)

                await init_tournament(new_tournament["id"])
                return


### Démarrer un tournoi
@bot.command(name='start')
@commands.has_role(to_id)
@commands.check(tournament_is_pending)
async def start_tournament(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if datetime.datetime.now() > tournoi["fin_check-in"]:
        challonge.tournaments.start(tournoi["id"])
        tournoi["statut"] = "underway"
        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
        await ctx.message.add_reaction("✅")
    else:
        await ctx.message.add_reaction("🕐")
        return

    await calculate_top8()

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser) # Refresh to get top 8
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    await bot.get_channel(annonce_channel_id).send(f"{server_logo} Le tournoi **{tournoi['name']}** est officiellement lancé, voici le bracket : {tournoi['url']} *(vous pouvez y accéder à tout moment avec la commande `!bracket` sur Discord et Twitch)*")

    score_annonce = (f":information_source: La prise en charge des scores pour le tournoi **{tournoi['name']}** est automatisée :\n"
                     f":white_small_square: Seul **le gagnant du set** envoie le score de son set, précédé par la **commande** `!win`.\n"
                     f":white_small_square: Le message du score doit contenir le **format suivant** : `!win 2-0, 3-2, 3-1, ...`.\n"
                     f":white_small_square: Un mauvais score intentionnel, perturbant le déroulement du tournoi, est **passable de DQ et ban**.\n"
                     f":white_small_square: Consultez le bracket afin de **vérifier** les informations : {tournoi['url']}\n"
                     f":white_small_square: En cas de mauvais score : contactez un TO pour une correction manuelle.")

    await bot.get_channel(scores_channel_id).send(score_annonce)

    queue_annonce = (":information_source: Le lancement des sets est automatisé. **Veuillez suivre les consignes de ce channel**, que ce soit par le bot ou les TOs. "
                     "Tout passage on stream sera notifié à l'avance.")

    await bot.get_channel(queue_channel_id).send(queue_annonce)

    tournoi_annonce = (f":alarm_clock: <@&{challenger_id}> On arrête le freeplay ! Le tournoi est sur le point de commencer. Veuillez lire les consignes :\n"
                       f":white_small_square: Vos sets sont annoncés dès que disponibles dans <#{queue_channel_id}> : **ne lancez rien sans consulter ce channel**.\n"
                       f":white_small_square: Le ruleset ainsi que les informations pour le bannissement des stages sont dispo dans <#{stagelist[tournoi['game']]['ruleset']}>.\n"
                       f":white_small_square: Le gagnant d'un set doit rapporter le score **dès que possible** dans <#{scores_channel_id}> avec la commande `!win`.\n"
                       f":white_small_square: Si vous le souhaitez vraiment, vous pouvez toujours DQ du tournoi avec la commande `!dq` à tout moment.\n"
                       f":white_small_square: En cas de lag qui rend votre set injouable, utilisez la commande `!lag` pour résoudre la situation.\n\n"
                       f":fire: Le **top 8** commencera, d'après le bracket :\n- En **winner round {tournoi['round_winner_top8']}** (semi-finales)\n- En **looser round {-tournoi['round_looser_top8']}**\n\n"
                       f"*L'équipe de TO et moi-même vous souhaitons un excellent tournoi.*")

    if tournoi["game"] == "Project+":
        tournoi_annonce += f"\n\n{stagelist[tournoi['game']]['icon']} En cas de desync, utilisez la commande `!desync` pour résoudre la situation."

    await bot.get_channel(tournoi_channel_id).send(tournoi_annonce)

    scheduler.add_job(underway_tournament, 'interval', id='underway_tournament', minutes=1, start_date=tournoi["début_tournoi"], replace_existing=True)


### Terminer un tournoi
@bot.command(name='end')
@commands.has_role(to_id)
@commands.check(tournament_is_underway)
async def end_tournament(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)

    if datetime.datetime.now() > tournoi["début_tournoi"]:
        challonge.tournaments.finalize(tournoi["id"])
        await ctx.message.add_reaction("✅")
    else:
        await ctx.message.add_reaction("🕐")
        return

    scheduler.remove_job('underway_tournament')

    await annonce_resultats()

    await bot.get_channel(annonce_channel_id).send(f"{server_logo} Le tournoi **{tournoi['name']}** est terminé, merci à toutes et à tous d'avoir participé ! J'espère vous revoir bientôt.")

    challenger = ctx.guild.get_role(challenger_id)

    for inscrit in participants:
        try:
            await ctx.guild.get_member(inscrit).remove_roles(challenger)
        except discord.HTTPException:
            pass

    with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
    with open(waiting_list_path, 'w') as f: json.dump({}, f, indent=4)
    with open(tournoi_path, 'w') as f: json.dump({}, f, indent=4)
    with open(stream_path, 'w') as f: json.dump([], f, indent=4)

    await bot.change_presence(activity=discord.Game(version))


### S'execute à chaque lancement, permet de relancer les tâches en cas de crash
async def reload_tournament():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        await bot.change_presence(activity=discord.Game(f"{version} • {tournoi['name']}"))
    except KeyError:
        print("No tournament had to be reloaded.")
        return

    # Relancer les tâches automatiques
    if tournoi["statut"] == "underway":
        scheduler.add_job(underway_tournament, 'interval', id='underway_tournament', minutes=1, replace_existing=True)

    elif tournoi["statut"] == "pending":
        scheduler.add_job(start_check_in, id='start_check_in', run_date=tournoi["début_check-in"], replace_existing=True)
        scheduler.add_job(end_check_in, id='end_check_in', run_date=tournoi["fin_check-in"], replace_existing=True)

        if tournoi["début_check-in"] < datetime.datetime.now() < tournoi["fin_check-in"]:
            scheduler.add_job(rappel_check_in, 'interval', id='rappel_check_in', minutes=10, replace_existing=True)

    print("Scheduled tasks for a tournament have been reloaded.")

    # Prendre les inscriptions manquées
    if datetime.datetime.now() < tournoi["fin_check-in"]:

        annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])

        with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)

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

        print("Missed inscriptions were also taken care of.")


### Annonce l'inscription
async def annonce_inscription():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    annonce = (f"{server_logo} **{tournoi['name']}** - {stagelist[tournoi['game']]['icon']} *{tournoi['game']}*\n"
               f":white_small_square: __Date__ : {format_date(tournoi['début_tournoi'], format='full', locale=language)} à {format_time(tournoi['début_tournoi'], format='short', locale=language)}\n"
               f":white_small_square: __Check-in__ : de {format_time(tournoi['début_check-in'], format='short', locale=language)} à {format_time(tournoi['fin_check-in'], format='short', locale=language)}\n"
               f":white_small_square: __Limite__ : 0/{str(tournoi['limite'])} joueurs *(mise à jour en temps réel)*\n"
               f":white_small_square: __Bracket__ : {tournoi['url']}\n"
               f":white_small_square: __Format__ : singles, double élimination (<#{stagelist[tournoi['game']]['ruleset']}>)\n\n"
               "Merci de vous inscrire en ajoutant une réaction ✅ à ce message. Vous pouvez vous désinscrire en la retirant à tout moment.\n"
               "*Notez que votre pseudonyme Discord au moment de l'inscription sera celui utilisé dans le bracket.*")

    inscriptions_channel = bot.get_channel(inscriptions_channel_id)

    async for message in inscriptions_channel.history(): await message.delete()

    annonce_msg = await inscriptions_channel.send(annonce)
    tournoi['annonce_id'] = annonce_msg.id
    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

    await annonce_msg.add_reaction("✅")

    await bot.get_channel(annonce_channel_id).send(f"{server_logo} Inscriptions pour le **{tournoi['name']}** ouvertes dans <#{inscriptions_channel_id}> ! <@&{stagelist[tournoi['game']]['role']}>\n"
                                                   f":calendar_spiral: Ce tournoi aura lieu le **{format_date(tournoi['début_tournoi'], format='full', locale=language)} à {format_time(tournoi['début_tournoi'], format='short', locale=language)}**.")

    await purge_channels()


### Inscription
async def inscrire(member):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(waiting_list_path, 'r+') as f: waiting_list = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if (member.id not in participants) and (len(participants) < tournoi['limite']):

        participants[member.id] = {
            "display_name" : member.display_name,
            "challonge" : challonge.participants.create(tournoi["id"], member.display_name)['id'],
            "checked_in" : False
        }

        if datetime.datetime.now() > tournoi["début_check-in"]:
            participants[member.id]["checked_in"] = True
            await member.add_roles(member.guild.get_role(challenger_id))

        with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
        await update_annonce()

        try:
            await member.send(f"Tu t'es inscrit(e) avec succès pour le tournoi **{tournoi['name']}**.")
        except discord.Forbidden:
            pass

    elif (member.id not in waiting_list) and (len(participants) >= tournoi['limite']):

        try:
            tournoi['waiting_list_id']
        except KeyError:
            inscriptions_channel = bot.get_channel(inscriptions_channel_id)
            waiting_list_msg = await inscriptions_channel.send(":hourglass: __Liste d'attente__ :\n")
            tournoi['waiting_list_id'] = waiting_list_msg.id
            with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

        waiting_list[member.id] = { "display_name" : member.display_name }

        with open(waiting_list_path, 'w') as f: json.dump(waiting_list, f, indent=4)
        await update_waiting_list()

        try:
            await member.send(f"Dû au manque de place, tu es ajouté(e) à la liste d'attente pour le tournoi **{tournoi['name']}**. Tu seras prévenu(e) si une place se libère !")
        except discord.Forbidden:
            pass


### Mettre à jour la liste d'attente
async def update_waiting_list():

    with open(waiting_list_path, 'r+') as f: waiting_list = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    old_waiting_list = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["waiting_list_id"])

    new_waiting_list = ":hourglass: __Liste d'attente__ :\n"

    for joueur in waiting_list:
        new_waiting_list += f":white_small_square: {waiting_list[joueur]['display_name']}\n"

    await old_waiting_list.edit(content=new_waiting_list)


### Désinscription
async def desinscrire(member):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(waiting_list_path, 'r+') as f: waiting_list = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if member.id in participants:

        challonge.participants.destroy(tournoi["id"], participants[member.id]['challonge'])

        if datetime.datetime.now() > tournoi["début_check-in"]:
            try:
                await member.remove_roles(member.guild.get_role(challenger_id))
            except discord.HTTPException:
                pass

        if datetime.datetime.now() < tournoi["fin_check-in"]:

            del participants[member.id]
            with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)

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

            # If there's a waiting list, add the next waiting player
            try:
                next_waiting_player = next(iter(waiting_list))
            except StopIteration:
                pass
            else:
                await inscrire(member.guild.get_member(next_waiting_player))

                # Since the member can be inactive, check-in should be required
                with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
                participants[next_waiting_player]["checked_in"] = False
                with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)

                del waiting_list[next_waiting_player]
                with open(waiting_list_path, 'w') as f: json.dump(waiting_list, f, indent=4)

                await update_waiting_list()


    elif member.id in waiting_list:

        del waiting_list[member.id]
        with open(waiting_list_path, 'w') as f: json.dump(waiting_list, f, indent=4)

        await update_waiting_list()

        try:
            await member.send(f"Tu as été retiré(e) de la liste d'attente pour le tournoi **{tournoi['name']}**.")
        except discord.Forbidden:
            pass


### Mettre à jour l'annonce d'inscription
async def update_annonce():

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    old_annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
    new_annonce = re.sub(r'[0-9]{1,2}\/', str(len(participants)) + '/', old_annonce.content)
    await old_annonce.edit(content=new_annonce)


### Début du check-in
async def start_check_in():

    guild = bot.get_guild(id=guild_id)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    challenger = guild.get_role(challenger_id)

    for inscrit in participants:
        await guild.get_member(inscrit).add_roles(challenger)

    scheduler.add_job(rappel_check_in, 'interval', id='rappel_check_in', minutes=10, replace_existing=True)

    await bot.get_channel(inscriptions_channel_id).send(f":information_source: Le check-in a commencé dans <#{check_in_channel_id}>. "
                                                        f"Vous pouvez toujours vous inscrire ici jusqu'à **{format_time(tournoi['fin_check-in'], format='short', locale=language)}** tant qu'il y a de la place.")

    await bot.get_channel(check_in_channel_id).send(f"<@&{challenger_id}> Le check-in pour **{tournoi['name']}** a commencé ! "
                                                    f"Vous avez jusqu'à **{format_time(tournoi['fin_check-in'], format='short', locale=language)}** pour signaler votre présence :\n"
                                                    f":white_small_square: Utilisez `!in` pour confirmer votre inscription\n:white_small_square: Utilisez `!out` pour vous désinscrire\n\n"
                                                    f"*Si vous n'avez pas check-in à temps, vous serez désinscrit automatiquement du tournoi.*")


### Rappel de check-in
async def rappel_check_in():

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    guild = bot.get_guild(id=guild_id)

    rappel_msg = ""

    for inscrit in participants:

        if participants[inscrit]["checked_in"] == False:
            rappel_msg += f"- <@{inscrit}>\n"

            if tournoi["fin_check-in"] - datetime.datetime.now() < datetime.timedelta(minutes=10):
                try:
                    await guild.get_member(inscrit).send(f"Attention ! Il ne te reste plus qu'une dizaine de minutes pour check-in au tournoi **{tournoi['name']}**.")
                except discord.Forbidden:
                    pass

    if rappel_msg != "":
        await bot.get_channel(check_in_channel_id).send(f":clock1: **Rappel de check-in !**\n{rappel_msg}\n"
                                                        f"*Vous avez jusqu'à {format_time(tournoi['fin_check-in'], format='short', locale=language)}, sinon vous serez désinscrit(s) automatiquement.*")


### Fin du check-in
async def end_check_in():

    guild = bot.get_guild(id=guild_id)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        scheduler.remove_job('rappel_check_in')
    except:
        pass

    annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
    await annonce.clear_reaction("✅")

    for inscrit in list(participants):
        if participants[inscrit]["checked_in"] == False:
            challonge.participants.destroy(tournoi["id"], participants[inscrit]['challonge'])
            to_dq = guild.get_member(inscrit)
            try:
                await to_dq.remove_roles(guild.get_role(challenger_id))
                await to_dq.send(f"Tu as été DQ du tournoi {tournoi['name']} car tu n'as pas check-in à temps, désolé !")
            except (discord.HTTPException, discord.Forbidden):
                pass
            del participants[inscrit]

    with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
    await update_annonce()

    await bot.get_channel(check_in_channel_id).send(":clock1: **Le check-in est terminé.** Les personnes n'ayant pas check-in ont été retirées du bracket. Contactez les TOs en cas de besoin.")
    await bot.get_channel(inscriptions_channel_id).send(":clock1: **Les inscriptions sont fermées.** Le tournoi débutera dans les minutes qui suivent : le bracket est en cours de finalisation. Contactez les TOs en cas de besoin.")


### Prise en charge du check-in et check-out
@bot.command(name='in')
@commands.check(can_check_in)
async def check_in(ctx):
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    participants[ctx.author.id]["checked_in"] = True
    with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
    await ctx.message.add_reaction("✅")


### Prise en charge du check-in et check-out
@bot.command(name='out')
@commands.check(can_check_in)
async def check_out(ctx):
    await desinscrire(ctx.author)
    await ctx.message.add_reaction("✅")


### Nettoyer les channels liés aux tournois
async def purge_channels():
    guild = bot.get_guild(id=guild_id)

    for category, channels in guild.by_category():

        if category != None:

            if category.id == tournoi_cat_id:
                for channel in channels:
                    async for message in channel.history():
                        await message.delete()

            if category.id in [winner_cat_id, looser_cat_id]:
                for channel in channels:
                    await channel.delete()


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
@commands.has_role(to_id)
@commands.check(tournament_is_pending)
async def add_inscrit(ctx):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    
    if datetime.datetime.now() > tournoi["fin_check-in"]:
        await ctx.message.add_reaction("🕐")
        return

    for member in ctx.message.mentions: await inscrire(member)
    await ctx.message.add_reaction("✅")


### Suppression/DQ manuel
@bot.command(name='rm')
@commands.has_role(to_id)
@commands.check(tournament_is_underway_or_pending)
async def remove_inscrit(ctx):
    for member in ctx.message.mentions: await desinscrire(member)
    await ctx.message.add_reaction("✅")


### Se DQ soi-même
@bot.command(name='dq')
@commands.check(tournament_is_underway_or_pending)
async def self_dq(ctx):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if ctx.author.id in participants:

        challonge.participants.destroy(tournoi["id"], participants[ctx.author.id]['challonge'])

        if datetime.datetime.now() > tournoi["début_check-in"]:
            await ctx.author.remove_roles(ctx.guild.get_role(challenger_id))

        if datetime.datetime.now() < tournoi["fin_check-in"]:
            inscription = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
            await inscription.remove_reaction("✅", ctx.author)
            del participants[ctx.author.id]
            with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
            await update_annonce()

        await ctx.message.add_reaction("✅")

    else:
        await ctx.message.add_reaction("⚠️")


### Managing sets during tournament : launch & remind
### Goal : get the bracket only once to limit API calls
async def underway_tournament():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    guild = bot.get_guild(id=guild_id)
    bracket = challonge.matches.index(tournoi["id"], state="open")
    await launch_matches(guild, bracket)
    await rappel_matches(guild, bracket)


### Gestion des scores
@bot.command(name='win')
@in_channel(scores_channel_id)
@commands.check(tournament_is_underway)
@commands.has_role(challenger_id)
async def score_match(ctx, arg):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(stream_path, 'r+') as f: stream = json.load(f)

    winner = participants[ctx.author.id]["challonge"] # Le gagnant est celui qui poste

    try:
        match = challonge.matches.index(tournoi['id'], state="open", participant_id=winner)

        if match[0]["underway_at"] == None:
            await ctx.send(f"<@{ctx.author.id}> Huh, le set pour lequel tu as donné le score n'a **pas encore commencé** !")
            return

    except:
        await ctx.message.add_reaction("⚠️")
        return

    try:
        score = re.search(r'([0-9]+) *\- *([0-9]+)', arg).group().replace(" ", "")
    except AttributeError:
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> **Ton score ne possède pas le bon format** *(3-0, 2-1, 3-2...)*, merci de le rentrer à nouveau.")
        return

    if score[0] < score[2]: score = score[::-1] # Le premier chiffre doit être celui du gagnant

    if is_top8(match[0]["round"]):
        aimed_score, looser_score, temps_min = 3, [0, 1, 2], 10
    else:
        aimed_score, looser_score, temps_min = 2, [0, 1], 5

    debut_set = dateutil.parser.parse(str(match[0]["underway_at"])).replace(tzinfo=None)

    if (int(score[0]) != aimed_score) or (int(score[2]) not in looser_score) or (datetime.datetime.now() - debut_set < datetime.timedelta(minutes = temps_min)):
        await ctx.message.add_reaction("⚠️")
        await ctx.send(f"<@{ctx.author.id}> **Score incorrect**, ou temps écoulé trop court. Rappel : BO3 jusqu'au top 8 qui a lieu en BO5.")
        return

    for joueur in participants:
        if participants[joueur]["challonge"] == match[0]["player1_id"]: player1 = joueur
        if participants[joueur]["challonge"] == match[0]["player2_id"]: player2 = joueur

    og_score = score

    if winner == participants[player2]["challonge"]:
        score = score[::-1] # Le score doit suivre le format "player1-player2" pour scores_csv

    try:
        challonge.matches.update(tournoi['id'], match[0]["id"], scores_csv=score, winner_id=winner)
        await ctx.message.add_reaction("✅")

    except:
        await ctx.message.add_reaction("⚠️")

    else:
        gaming_channel = discord.utils.get(ctx.guild.text_channels, name=str(match[0]["suggested_play_order"]))

        if gaming_channel != None:
            await gaming_channel.send(f":bell: __Score rapporté__ : **{participants[ctx.author.id]['display_name']}** gagne **{og_score}** !\n"
                                      f"*En cas d'erreur, appelez un TO ! Un mauvais score intentionnel est passable de DQ et ban du tournoi.*\n"
                                      f"*Note : ce channel sera automatiquement supprimé dans 10 minutes.*")

            scheduler.add_job(
                scheduled_channel_removal,
                id = f'remove {gaming_channel.name}',
                args = [gaming_channel.name],
                run_date = datetime.datetime.now() + datetime.timedelta(minutes=10)
            )

        if match[0]["suggested_play_order"] == tournoi["on_stream"]:
            tournoi["on_stream"] = None
            with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
            await call_stream()


# Scheduled channel removal
async def scheduled_channel_removal(channel_name):
    guild = bot.get_guild(id=guild_id)
    gaming_channel = discord.utils.get(guild.text_channels, name=channel_name)
    try:
        await gaming_channel.delete(reason="Scheduled channel removal")
    except (discord.NotFound, discord.HTTPException):
        pass


### Forfeit
@bot.command(name='forfeit', aliases=['ff', 'loose'])
@commands.check(tournament_is_underway)
@commands.has_role(challenger_id)
async def forfeit_match(ctx):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)

    try:
        looser = participants[ctx.author.id]["challonge"]
        match = challonge.matches.index(tournoi['id'], state="open", participant_id=looser)

        for joueur in participants:
            if participants[joueur]["challonge"] == match[0]["player1_id"]: player1 = joueur
            if participants[joueur]["challonge"] == match[0]["player2_id"]: player2 = joueur

        if looser == participants[player2]["challonge"]:
            winner = participants[player1]["challonge"]
            score = "1-0"
        else:
            winner = participants[player2]["challonge"]
            score = "0-1"

        challonge.matches.update(tournoi['id'], match[0]["id"], scores_csv=score, winner_id=winner)
        await ctx.message.add_reaction("✅")

    except:
        await ctx.message.add_reaction("⚠️")


### Lancer matchs ouverts
async def launch_matches(guild, bracket):

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    sets = ""

    for match in bracket:

        if match["underway_at"] == None:

            challonge.matches.mark_as_underway(tournoi["id"], match["id"])

            for joueur in participants:
                if participants[joueur]["challonge"] == match["player1_id"]: player1 = guild.get_member(joueur)
                if participants[joueur]["challonge"] == match["player2_id"]: player2 = guild.get_member(joueur)

            # Création d'un channel volatile pour le set
            try:
                gaming_channel = await guild.create_text_channel(
                    str(match["suggested_play_order"]),
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        player1: discord.PermissionOverwrite(read_messages=True),
                        player2: discord.PermissionOverwrite(read_messages=True)
                    },
                    category = discord.Object(id=(winner_cat_id if match["round"] > 0 else looser_cat_id)),
                    topic = "Channel temporaire pour un set.",
                    reason = f"Lancement du set n°{match['suggested_play_order']}"
                )

            except discord.HTTPException:
                gaming_channel_txt = f":video_game: Je n'ai pas pu créer de channel, faites votre set en MP ou dans <#{tournoi_channel_id}>."

                if match["suggested_play_order"] in stream:
                    await player1.send(f"Tu joueras on stream pour ton prochain set contre **{player2.display_name}** : je te communiquerai les codes d'accès de l'arène quand ce sera ton tour.")
                    await player2.send(f"Tu joueras on stream pour ton prochain set contre **{player1.display_name}** : je te communiquerai les codes d'accès de l'arène quand ce sera ton tour.")

            else:
                gaming_channel_txt = f":video_game: Allez faire votre set dans le channel <#{gaming_channel.id}> !"

                with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

                gaming_channel_annonce = (f":arrow_forward: Ce channel a été créé pour le set suivant : <@{player1.id}> vs <@{player2.id}>\n"
                                          f":white_small_square: Les règles du set doivent suivre celles énoncées dans <#{stagelist[tournoi['game']]['ruleset']}> (doit être lu au préalable).\n"
                                          f":white_small_square: La liste des stages légaux à l'heure actuelle est toujours disponible via la commande `!stages`.\n"
                                          f":white_small_square: En cas de lag qui rend la partie injouable, utilisez la commande `!lag` pour résoudre la situation.\n"
                                          f":white_small_square: **Dès que le set est terminé**, le gagnant envoie le score dans <#{scores_channel_id}> avec la commande `!win`.\n\n"
                                          f":game_die: **{random.choice([player1.display_name, player2.display_name])}** est tiré au sort pour commencer le ban des stages.\n")

                if tournoi["game"] == "Project+":
                    gaming_channel_annonce += f"{stagelist[tournoi['game']]['icon']} **Minimum buffer suggéré** : le host peut le faire calculer avec la commande `!buffer ping`.\n"

                if is_top8(match["round"]):
                    gaming_channel_annonce += ":fire: C'est un set de **top 8** : vous devez le jouer en **BO5** *(best of five)*.\n"

                if match["suggested_play_order"] in stream:
                    gaming_channel_annonce += ":tv: Vous jouerez **on stream**. Dès que ce sera votre tour, je vous communiquerai les codes d'accès de l'arène."

                await gaming_channel.send(gaming_channel_annonce)

            try:
                if (match["suggested_play_order"] == stream[0]) and (tournoi["on_stream"] == None): await call_stream()
            except IndexError:
                pass

            on_stream = "(**on stream**) :tv:" if match["suggested_play_order"] in stream else ""
            top_8 = "(**top 8**) :fire:" if is_top8(match["round"]) else ""

            sets += f":arrow_forward: **{nom_round(match['round'])}** : <@{player1.id}> vs <@{player2.id}> {on_stream}\n{gaming_channel_txt} {top_8}\n\n"

    if sets != "":
        if len(sets) < 2000:
            await bot.get_channel(queue_channel_id).send(sets)
        else: # Discord doesn't deal with more than 2000 characters
            sets = [x.strip() for x in sets.split('\n\n') if x.strip() != ''] # so we have to split
            while sets:
                await bot.get_channel(queue_channel_id).send('\n\n'.join(sets[:10]))
                del sets[:10] # and send by groups of ten sets


### Ajout ID et MDP d'arène de stream
@bot.command(name='setstream')
@commands.has_role(to_id)
@commands.check(tournament_is_underway_or_pending)
async def setup_stream(ctx, *args):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if tournoi['game'] == 'Super Smash Bros. Ultimate' and len(args) == 2:
        tournoi["stream"] = args

    elif tournoi['game'] == 'Project+' and len(args) == 1:
        tournoi["stream"] = args

    else:
        await ctx.message.add_reaction("⚠️")
        return

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
    await ctx.message.add_reaction("✅")


### Ajouter un set dans la stream queue
@bot.command(name='addstream')
@commands.has_role(to_id)
@commands.check(tournament_is_underway_or_pending)
async def add_stream(ctx, *args: int):

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    # Pre-add before the tournament goes underway - BE CAREFUL!
    if tournoi["statut"] == "pending":
        for arg in args: stream.append(arg)
        with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
        await ctx.message.add_reaction("☑️")
        return

    try:
        bracket = challonge.matches.index(tournoi['id'], state=("open", "pending"))
    except:
        await ctx.message.add_reaction("⚠️")
        return

    for arg in args:
        for match in bracket:
            if (match["suggested_play_order"] == arg) and (match["underway_at"] == None) and (arg not in stream):
                stream.append(arg)
                break

    with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
    await ctx.message.add_reaction("✅")


### Enlever un set de la stream queue
@bot.command(name='rmstream')
@commands.has_role(to_id)
@commands.check(tournament_is_underway_or_pending)
async def remove_stream(ctx, *args):

    if args[0] == "queue": # Reset la stream queue
        with open(stream_path, 'w') as f: json.dump([], f, indent=4)
        await ctx.message.add_reaction("✅")
        return

    if args[0] == "now": # Reset le set on stream
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        tournoi["on_stream"] = None
        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
        await ctx.message.add_reaction("✅")
        return

    with open(stream_path, 'r+') as f: stream = json.load(f)

    try:
        for arg in args: stream.remove(int(arg))
    except (ValueError, TypeError):
        await ctx.message.add_reaction("⚠️")
    else:
        with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
        await ctx.message.add_reaction("✅")


### Infos stream
@bot.command(name='stream')
@commands.has_role(to_id)
@commands.check(tournament_is_underway_or_pending)
async def list_stream(ctx):

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        bracket = challonge.matches.index(tournoi['id'], state=("open", "pending"))
    except:
        await ctx.message.add_reaction("⚠️")
        return

    msg = f":information_source: Arène de stream :\n{get_access_stream()}\n"

    if tournoi["on_stream"] != None:

        for match in bracket:

            if tournoi["on_stream"] == match["suggested_play_order"]:

                for joueur in participants:
                    if participants[joueur]["challonge"] == match["player1_id"]: player1 = participants[joueur]['display_name']
                    if participants[joueur]["challonge"] == match["player2_id"]: player2 = participants[joueur]['display_name']

                msg += f":arrow_forward: **Set on stream actuel** *({tournoi['on_stream']})* : **{player1}** vs **{player2}**\n"
                break

        else: msg += ":warning: Huh ? Le set on stream ne semble pas/plus être en cours. Je suggère `!rmstream now`.\n"

    else:
        msg += ":stop_button: Il n'y a aucun set on stream à l'heure actuelle.\n"

    list_stream = ""

    for order in stream:

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
        msg += f":play_pause: Liste des sets prévus pour passer on stream prochainement :\n{list_stream}"
    else:
        msg += ":play_pause: Il n'y a aucun set prévu pour passer on stream prochainement."

    await ctx.send(msg)


### Appeler les joueurs on stream
async def call_stream():

    guild = bot.get_guild(id=guild_id)

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    bracket = challonge.matches.index(tournoi["id"], state="open")

    if stream == [] or tournoi["on_stream"] != None: return

    for match in bracket:

        if (match["suggested_play_order"] == stream[0]) and (match["underway_at"] != None):

            for joueur in participants:
                if participants[joueur]["challonge"] == match["player1_id"]: player1 = guild.get_member(joueur)
                if participants[joueur]["challonge"] == match["player2_id"]: player2 = guild.get_member(joueur)

            gaming_channel = discord.utils.get(guild.text_channels, name=str(match["suggested_play_order"]))

            if gaming_channel == None:
                await player1.send(f"C'est ton tour de passer on stream ! N'oublie pas de donner les scores dès que le set est fini. Voici les codes d'accès de l'arène :\n{get_access_stream()}")
                await player2.send(f"C'est ton tour de passer on stream ! N'oublie pas de donner les scores dès que le set est fini. Voici les codes d'accès de l'arène :\n{get_access_stream()}")
            else:
                await gaming_channel.send(f":clapper: C'est votre tour de passer on stream ! **N'oubliez pas de donner les scores dès que le set est fini.** <@{player1.id}> <@{player2.id}>\n\nVoici les codes d'accès de l'arène :\n{get_access_stream()}")

            await bot.get_channel(stream_channel_id).send(f":arrow_forward: Envoi on stream du set n°{match['suggested_play_order']} : **{participants[player1.id]['display_name']}** vs **{participants[player2.id]['display_name']}** !")

            tournoi["on_stream"] = match["suggested_play_order"]
            with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

            while match["suggested_play_order"] in stream: stream.remove(match["suggested_play_order"])
            with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)

            break


### Calculer les rounds à partir desquels un set est top 8 (bracket D.E.)
async def calculate_top8():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    bracket = challonge.matches.index(tournoi['id'], state=("open", "pending"))

    max_round_winner, max_round_looser = 1, -1

    for match in bracket:
        if match["round"] > max_round_winner: max_round_winner = match["round"]
        if match["round"] < max_round_looser: max_round_looser = match["round"]

    tournoi["round_winner_top8"] = max_round_winner - 2
    tournoi["round_looser_top8"] = max_round_looser + 3

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)


### Lancer un rappel de matchs
async def rappel_matches(guild, bracket):

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    for match in bracket:

        if (match["underway_at"] != None) and (match["suggested_play_order"] not in stream) and (match["suggested_play_order"] != tournoi["on_stream"]):

            debut_set = dateutil.parser.parse(str(match["underway_at"])).replace(tzinfo=None)

            if tournoi['game'] == 'Super Smash Bros. Ultimate':
                seuil = 42 if is_top8(match["round"]) else 28 # Calculé selon (tps max match * nb max matchs) + 7 minutes
            elif tournoi['game'] == 'Project+':
                seuil = 47 if is_top8(match["round"]) else 31 # Idem
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
                                  f":white_small_square: Le gagnant est prié de le poster dans <#{scores_channel_id}> dès que possible.\n"
                                  f":white_small_square: Sous peu, la dernière personne ayant été active sur ce channel sera déclarée vainqueur.\n"
                                  f":white_small_square: La personne ayant été inactive (d'après le dernier message posté) sera **DQ sans concession** du tournoi.\n")

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
                            challonge.participants.destroy(tournoi["id"], participants[player1.id]['challonge'])
                            challonge.participants.destroy(tournoi["id"], participants[player2.id]['challonge'])
                            continue

                        try:
                            looser
                        except NameError: # S'il n'y a pas eu de résultat pour un second joueur différent : DQ de l'inactif
                            looser = player2 if winner.id == player1.id else player1
                            await gaming_channel.send(f"<@&{to_id}> **DQ automatique de <@{looser.id}> pour inactivité.**")
                            challonge.participants.destroy(tournoi["id"], participants[looser.id]['challonge'])
                            continue

                        if winner_last_activity - looser_last_activity > datetime.timedelta(minutes = 10): # Si différence d'inactivité de plus de 10 minutes
                            await gaming_channel.send(f"<@&{to_id}> **Une DQ automatique a été executée pour inactivité :**\n-<@{winner.id}> passe au round suivant.\n-<@{looser.id}> est DQ du tournoi.")
                            challonge.participants.destroy(tournoi["id"], participants[looser.id]['challonge'])

                        else: # Si pas de différence notable, demander une décision manuelle
                            await gaming_channel.send(f"<@&{to_id}> **Durée anormalement longue détectée** pour ce set, une décision d'un TO doit être prise")


### Obtenir stagelist
@bot.command(name='stages', aliases=['stage', 'stagelist', 'ban', 'bans', 'map', 'maps'])
@commands.check(tournament_is_underway_or_pending)
async def get_stagelist(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    msg = f":map: **Stages légaux pour {tournoi['game']} :**\n:white_small_square: __Starters__ :\n"
    for stage in stagelist[tournoi['game']]['starters']: msg += f"- {stage}\n"

    if 'counterpicks' in stagelist[tournoi['game']]:
        msg += ":white_small_square: __Counterpicks__ :\n"
        for stage in stagelist[tournoi['game']]['counterpicks']: msg += f"- {stage}\n"

    await ctx.send(msg)


### Lag
@bot.command(name='lag')
@commands.has_role(challenger_id)
async def send_lag_text(ctx):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    msg = lag_text

    try:
        if tournoi['game'] == 'Project+':
            msg += (f"\n{stagelist[tournoi['game']]['icon']} **Spécificités Project+ :**\n"
                    ":white_small_square: Vérifier que le PC fait tourner le jeu de __manière fluide (60 FPS constants)__, sinon :\n"
                    "- Baisser la résolution interne dans les paramètres graphiques.\n"
                    "- Désactiver les textures HD, l'anti-aliasing, s'ils ont été activés.\n"
                    "- Windows seulement : changer le backend pour *Direct3D9* (le + fluide) ou *Direct3D11* (+ précis que D9)\n"
                    ":white_small_square: Vérifier que la connexion est __stable et suffisamment rapide__ :\n"
                    "- Le host peut augmenter le \"minimum buffer\" de 6 à 8 : utilisez la commande `!buffer` en fournissant votre ping.\n"
                    "- Suivre les étapes génériques contre le lag, citées ci-dessus.\n"
                    ":white_small_square: Utilisez la commande `!desync` en cas de desync suspectée.")
    except KeyError:
        pass

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
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    participants, resultats = challonge.participants.index(tournoi["id"]), []

    if len(participants) < 8:
        await bot.get_channel(resultats_channel_id).send(f"{server_logo} Résultats du **{tournoi['name']}** : {tournoi['url']}")
        return

    for joueur in participants:
        resultats.append((joueur['final_rank'], joueur['display_name']))

    resultats.sort()
    fifth = [y for x, y in resultats if x == 5]
    seventh = [y for x, y in resultats if x == 7]

    ending = random.choice([
        "Bien joué à tous ! Quant aux autres : ne perdez pas espoir, ce sera votre tour un jour...",
        "Merci à tous d'avoir participé, on se remet ça très bientôt ! Prenez soin de vous.",
        "Félicitations à eux. N'oubliez pas que la clé est la persévérance ! Croyez toujours en vous.",
        "Ce fut un plaisir en tant que bot d'aider à la gestion de ce tournoi et d'assister à vos merveileux sets."
    ])
    
    classement = (f"{server_logo} **__Résultats du {tournoi['name']}__**\n\n"
                  f":trophy: **1er** : **{resultats[0][1]}**\n"
                  f":second_place: **2e** : {resultats[1][1]}\n"
                  f":third_place: **3e** : {resultats[2][1]}\n"
                  f":medal: **4e** : {resultats[3][1]}\n"
                  f":reminder_ribbon: **5e** : {fifth[0]} / {fifth[1]}\n"
                  f":reminder_ribbon: **7e** : {seventh[0]} / {seventh[1]}\n\n"
                  f":bar_chart: {len(participants)}\n"
                  f"{stagelist[tournoi['game']]['icon']} {tournoi['game']}\n"
                  f":link: **Bracket :** {tournoi['url']}\n\n"
                  f"{ending}")
    
    await bot.get_channel(resultats_channel_id).send(classement)


### Ajouter un rôle
async def attribution_role(event):
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    for game in stagelist:

        if event.emoji.name == re.search(r'\:(.*?)\:', stagelist[game]['icon']).group(1):
            role = event.member.guild.get_role(stagelist[game]['role'])

            try:
                await event.member.add_roles(role)
                await event.member.send(f"Le rôle **{role.name}** t'a été attribué avec succès : tu recevras des informations concernant les tournois *{game}* !")
            except (discord.HTTPException, discord.Forbidden):
                pass

        elif event.emoji.name == stagelist[game]['icon_1v1']:
            role = event.member.guild.get_role(stagelist[game]['role_1v1'])

            try:
                await event.member.add_roles(role)
                await event.member.send(f"Le rôle **{role.name}** t'a été attribué avec succès : tu seras contacté si un joueur cherche des combats sur *{game}* !")
            except (discord.HTTPException, discord.Forbidden):
                pass


### Enlever un rôle
async def retirer_role(event):
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    guild = bot.get_guild(id=guild_id) # due to event.member not being available

    for game in stagelist:

        if event.emoji.name == re.search(r'\:(.*?)\:', stagelist[game]['icon']).group(1):
            role, member = guild.get_role(stagelist[game]['role']), guild.get_member(event.user_id)

            try:
                await member.remove_roles(role)
                await member.send(f"Le rôle **{role.name}** t'a été retiré avec succès : tu ne recevras plus les informations concernant les tournois *{game}*.")
            except (discord.HTTPException, discord.Forbidden):
                pass

        elif event.emoji.name == stagelist[game]['icon_1v1']:
            role, member = guild.get_role(stagelist[game]['role_1v1']), guild.get_member(event.user_id)

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

        if event.message_id == tournoi["annonce_id"]:
            await inscrire(event.member) # available for REACTION_ADD only

    elif (event.channel_id == roles_channel_id): await attribution_role(event)


### À chaque suppression de réaction
@bot.event
async def on_raw_reaction_remove(event):
    if event.user_id == bot.user.id: return

    elif (event.emoji.name == "✅") and (event.channel_id == inscriptions_channel_id):

        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if event.message_id == tournoi["annonce_id"]:
            await desinscrire(bot.get_guild(id=guild_id).get_member(event.user_id)) # event.member not available for REACTION_REMOVE

    elif (event.channel_id == roles_channel_id): await retirer_role(event)


### Help message
@bot.command(name='help', aliases=['info', 'version'])
async def send_help(ctx):
    await ctx.send(f"{help_text}\n**{name} {version}** - *Made by {author} with* :heart:")

### Desync message
@bot.command(name='desync')
async def send_desync_help(ctx):
    await ctx.send(desync_text)

### On command error : invoker has not enough permissions
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CheckFailure, commands.MissingRole)):
        await ctx.message.add_reaction("🚫")


#### Scheduler
scheduler.start()

#### Lancement du bot
bot.run(bot_secret, bot = True, reconnect = True)

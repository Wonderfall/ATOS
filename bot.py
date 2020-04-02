import discord, random, logging, os, json, re, challonge, dateutil.parser, datetime, asyncio, yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler

with open('data/config.yml', 'r+') as f: config = yaml.safe_load(f)

if config["debug"] == True: logging.basicConfig(level=logging.DEBUG)

#### Version
version                             = "4.1"

### File paths
tournoi_path                        = config["paths"]["tournoi"]
participants_path                   = config["paths"]["participants"]
stream_path                         = config["paths"]["stream"]
stagelist_path                      = config["paths"]["stagelist"]

#### Discord IDs
guild_id                            = config["discord"]["guild"]

### Server channels
blabla_channel_id                   = config["discord"]["channels"]["blabla"]
annonce_channel_id                  = config["discord"]["channels"]["annonce"]
check_in_channel_id                 = config["discord"]["channels"]["check_in"]
inscriptions_channel_id             = config["discord"]["channels"]["inscriptions"]
scores_channel_id                   = config["discord"]["channels"]["scores"]
stream_channel_id                   = config["discord"]["channels"]["stream"]
queue_channel_id                    = config["discord"]["channels"]["queue"]
tournoi_channel_id                  = config["discord"]["channels"]["tournoi"]

### Info, non-interactive channels
ruleset_channel_id                  = config["discord"]["channels"]["ruleset"]
deroulement_channel_id              = config["discord"]["channels"]["deroulement"]
faq_channel_id                      = config["discord"]["channels"]["faq"]

### Server categories
tournoi_cat_id                      = config["discord"]["categories"]["tournoi"]
arenes_cat_id                       = config["discord"]["categories"]["arenes"]
arenes                              = discord.Object(id=arenes_cat_id)

### Role IDs
challenger_id                       = config["discord"]["roles"]["challenger"]
to_id                               = config["discord"]["roles"]["to"]

### Custom emojis
server_logo                         = config["discord"]["emojis"]["logo"]

#### Challonge
challonge_user                      = config["challonge"]["user"]

### Tokens
bot_secret                          = config["discord"]["secret"]
challonge_api_key                   = config["challonge"]["api_key"]


### Texts
welcome_text=f"""
Je t'invite à consulter le channel <#{deroulement_channel_id}> et <#{ruleset_channel_id}>, et également <#{inscriptions_channel_id}> si tu souhaites t'inscrire à un tournoi. N'oublie pas de consulter les <#{annonce_channel_id}> régulièrement, et de poser tes questions aux TOs sur <#{faq_channel_id}>. Enfin, amuse-toi bien.
"""

help_text=f"""
:cd: **Commandes user :**
- `!help` : c'est la commande que tu viens de rentrer.
- `!bracket` : obtenir le lien du bracket en cours.

:video_game: **Commandes joueur :**
- `!dq` : se retirer du tournoi avant/après (DQ) que celui-ci ait commencé.
- `!flip` : pile/face simple, fonctionne dans tous les channels.
- `!win` : rentrer le score d'un set dans <#{scores_channel_id}> *(paramètre : score)*.
- `!stages` : obtenir la stagelist légale actuelle.
- `!lag` : ouvrir une procédure de lag, à utiliser avec parcimonie.

:no_entry_sign: **Commandes administrateur :**
- `!purge` : purifier les channels relatifs à un tournoi.
- `!setup` : initialiser un tournoi *(paramètre : lien challonge valide)*.
- `!rm` : désinscrire/retirer (DQ) quelqu'un du tournoi *(paramètre : @mention | liste)*.
- `!add` : ajouter quelqu'un au tournoi *(paramètre : @mention | liste)*.

:tv: **Commandes stream :**
- `!stream` : obtenir toutes les informations relatives au stream (IDs, on stream, queue).
- `!setstream` : mettre en place l'arène de stream *(2 paramètres : ID MDP)*.
- `!addstream` : ajouter un set à la stream queue *(paramètre : n° | liste de n°)*.
- `!rmstream` : retirer un set de la stream queue *(paramètre : n° | queue | now)*.

*Version {version}, made by Wonderfall with :heart:*
"""

lag_text=f"""
:satellite: **Un lag a été constaté**, les <@&{to_id}> sont contactés.

**1)** En attendant, chaque joueur peut :
- Vérifier qu'aucune autre connexion locale ne pompe la connexion.
- S'assurer que la connexion au réseau est, si possible, câblée.
- S'assurer qu'il/elle n'emploie pas un partage de connexion de réseau mobile (passable de DQ).

**2)** Si malgré ces vérifications la connexion n'est pas toujours pas satisfaisante, chaque joueur doit :
- Préparer un test de connexion *(Switch pour Ultimate, Speedtest pour Project+)*.
- Décrire sa méthode de connexion actuelle *(Wi-Fi, Ethernet direct, CPL -> ADSL, FFTH, 4G...)*.

**3)** Si nécessaire, un TO s'occupera de votre cas et proposera une arène avec le/les joueur(s) problématique(s).
"""

### Init things
bot = discord.Client()
challonge.set_credentials(challonge_user, challonge_api_key)
scheduler = AsyncIOScheduler()


### De-serialize & re-serialize datetime objects for JSON storage
def dateconverter(o):
    if isinstance(o, datetime.datetime):
        return o.__str__()

def dateparser(dct):
    for k, v in dct.items():
        try:
            dct[k] = datetime.datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        except:
            pass
    return dct

### Get int keys !
def int_keys(ordered_pairs):
    result = {}
    for key, value in ordered_pairs:
        try:
            key = int(key)
        except ValueError:
            pass
        result[key] = value
    return result

### Determine whether a match is top 8 or not
def is_top8(match_round):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if (match_round >= tournoi["round_winner_top8"]) or (match_round <= tournoi["round_looser_top8"]):
        return True
    else:
        return False

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
    await bot.change_presence(activity=discord.Game(version))
    await reload_tournament()


### A chaque arrivée de membre
@bot.event
async def on_member_join(member):
    await bot.get_channel(blabla_channel_id).send(f"{server_logo} Bienvenue à toi sur le serveur {member.guild.name}, <@{member.id}>. {welcome_text}")


### Récupérer informations du tournoi et initialiser tournoi.json
@bot.event
async def get_tournament(url):

    if re.compile("^(https?\:\/\/)?(challonge.com)\/.+$").match(url):
        try:
            bracket = challonge.tournaments.show(url.replace("https://challonge.com/", ""))
        except:
            return
    else:
        return

    tournoi = {
        "name": bracket["name"],
        "game": bracket["game_name"],
        "url": url,
        "id": bracket["id"],
        "limite": bracket["signup_cap"],
        "statut": bracket["state"],
        "début_tournoi": dateutil.parser.parse(str(bracket["start_at"])).replace(tzinfo=None),
        "début_check-in": dateutil.parser.parse(str(bracket["start_at"])).replace(tzinfo=None) - datetime.timedelta(hours = 1),
        "fin_check-in": dateutil.parser.parse(str(bracket["start_at"])).replace(tzinfo=None) - datetime.timedelta(minutes = 10),
        "on_stream": None,
        "stream": ["N/A", "N/A"],
        "warned": []
    }

    return tournoi


### Ajouter un tournoi
@bot.event
async def setup_tournament(message):

    url = message.content.replace("!setup ", "")
    tournoi = await get_tournament(url)

    if tournoi == None:
        await message.add_reaction("⚠️")
        return

    elif datetime.datetime.now() > tournoi["début_tournoi"]:
        await message.add_reaction("🕐")
        return

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
    with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
    with open(stream_path, 'w') as f: json.dump([], f, indent=4)

    await annonce_inscription()

    scheduler.add_job(start_check_in, id='start_check_in', run_date=tournoi["début_check-in"], replace_existing=True)
    scheduler.add_job(end_check_in, id='end_check_in', run_date=tournoi["fin_check-in"], replace_existing=True)
    scheduler.add_job(check_tournament_state, 'interval', id='check_tournament_state', minutes=1, replace_existing=True)

    await message.add_reaction("✅")
    await bot.change_presence(activity=discord.Game(f"{version} • {tournoi['name']}"))

    await purge_channels()


### S'execute à chaque lancement, permet de relancer les tâches en cas de crash
@bot.event
async def reload_tournament():

    try:
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        await bot.change_presence(activity=discord.Game(f"{version} • {tournoi['name']}"))

        # Relancer les tâches automatiques
        scheduler.add_job(start_check_in, id='start_check_in', run_date=tournoi["début_check-in"], replace_existing=True)
        scheduler.add_job(end_check_in, id='end_check_in', run_date=tournoi["fin_check-in"], replace_existing=True)
        scheduler.add_job(check_tournament_state, 'interval', id='check_tournament_state', minutes=1, replace_existing=True)

        print("Scheduled tasks for a tournament have been reloaded.")

        if tournoi["statut"] == "pending":

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

    except:
        print("No scheduled tasks for any tournament had to be reloaded.")
        pass


### Annonce l'inscription
@bot.event
async def annonce_inscription():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    annonce = (f"{server_logo} **{tournoi['name']}** - {tournoi['game']}\n"
               f":arrow_forward: **Date** : le {tournoi['début_tournoi'].strftime('%d.%m.%y à %Hh%M')}\n"
               f":arrow_forward: **Check-in** : de {tournoi['début_check-in'].strftime('%Hh%M')} à {tournoi['fin_check-in'].strftime('%Hh%M')}\n"
               f":arrow_forward: **Limite** : 0/{str(tournoi['limite'])} joueurs *(mise à jour en temps réel)*\n"
               f":arrow_forward: **Bracket** : {tournoi['url']}\n"
               f":arrow_forward: **Format** : singles, double élimination\n\n"
               "Merci de vous inscrire en ajoutant une réaction ✅ à ce message. Vous pouvez vous désinscrire en la retirant à tout moment.\n"
               "*Notez que votre pseudonyme Discord au moment de l'inscription sera celui utilisé dans le bracket.*")

    inscriptions_channel = bot.get_channel(inscriptions_channel_id)

    async for message in inscriptions_channel.history(): await message.delete()

    annonce_msg = await inscriptions_channel.send(annonce)
    tournoi['annonce_id'] = annonce_msg.id
    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

    await annonce_msg.add_reaction("✅")
    await bot.get_channel(annonce_channel_id).send(f"{server_logo} Inscriptions pour le **{tournoi['name']}** ouvertes dans <#{inscriptions_channel_id}> ! Ce tournoi aura lieu le **{tournoi['début_tournoi'].strftime('%d.%m.%y à %Hh%M')}**.")


### Inscription
@bot.event
async def inscrire(member):

    try:
        with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if (datetime.datetime.now() > tournoi["fin_check-in"]) or (len(participants) >= tournoi['limite']):
            await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"]).remove_reaction("✅", member)
            return
    except:
        return

    if member.id not in participants:

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


### Désinscription
@bot.event
async def desinscrire(member):

    try:
        with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if datetime.datetime.now() > tournoi["fin_check-in"]: return
    except:
        return

    if member.id in participants:
        challonge.participants.destroy(tournoi["id"], participants[member.id]['challonge'])

        if datetime.datetime.now() > tournoi["début_check-in"]:
            await member.remove_roles(member.guild.get_role(challenger_id))

        del participants[member.id]
        with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
        await update_annonce()


### Mettre à jour l'annonce d'inscription
@bot.event
async def update_annonce():

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    old_annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
    new_annonce = re.sub(r'[0-9]{1,2}\/', str(len(participants)) + '/', old_annonce.content)
    await old_annonce.edit(content=new_annonce)


### Début du check-in
@bot.event
async def start_check_in():

    guild = bot.get_guild(id=guild_id)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    challenger = guild.get_role(challenger_id)

    for inscrit in participants:
        await guild.get_member(inscrit).add_roles(challenger)

    scheduler.add_job(rappel_check_in, 'interval', id='rappel_check_in', minutes=10, replace_existing=True)

    await bot.get_channel(inscriptions_channel_id).send(f":information_source: Le check-in a commencé dans <#{check_in_channel_id}>. Vous pouvez toujours vous inscrire ici jusqu'à **{tournoi['fin_check-in'].strftime('%Hh%M')}** sans besoin de check-in par la suite, et tant qu'il y a de la place.")
    await bot.get_channel(check_in_channel_id).send(f"<@&{challenger_id}> Le check-in pour **{tournoi['name']}** a commencé : vous avez jusqu'à **{tournoi['fin_check-in'].strftime('%Hh%M')}** pour signaler votre présence, sinon vous serez retiré automatiquement du tournoi.\n- Utilisez `!in` pour confirmer votre inscription\n- Utilisez `!out` pour vous désinscrire")


### Rappel de check-in
@bot.event
async def rappel_check_in():

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    rappel_msg = ""

    for inscrit in participants:
        if participants[inscrit]["checked_in"] == False:
            rappel_msg += f"- <@{inscrit}>\n"

    if rappel_msg != "":
        await bot.get_channel(check_in_channel_id).send(f":clock1: **Rappel de check-in !**\n{rappel_msg}\n*Vous avez jusqu'à {tournoi['fin_check-in'].strftime('%Hh%M')}, sinon vous serez désinscrit(s) automatiquement.*")


### Fin du check-in
@bot.event
async def end_check_in():

    guild = bot.get_guild(id=guild_id)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        scheduler.remove_job('rappel_check_in')
    except:
        pass

    for inscrit in participants:
        if participants[inscrit]["checked_in"] == False:
            challonge.participants.destroy(tournoi["id"], participants[inscrit]['challonge'])
            await guild.get_member(inscrit).remove_roles(guild.get_role(challenger_id))
            del participants[inscrit]

    with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
    await update_annonce()

    annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
    await annonce.clear_reaction("✅")

    await bot.get_channel(check_in_channel_id).send(":clock1: **Le check-in est terminé.** Les personnes n'ayant pas check-in ont été retirées du bracket. Contactez les TOs s'il y a un quelconque problème, merci de votre compréhension.")
    await bot.get_channel(inscriptions_channel_id).send(":clock1: **Les inscriptions sont fermées.** Le tournoi débutera dans les minutes qui suivent : le bracket est en cours de finalisation. Contactez les TOs s'il y a un quelconque problème, merci de votre compréhension.")


### Prise en charge du check-in et check-out
@bot.event
async def check_in(message):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if (message.author.id in participants) and (tournoi["fin_check-in"] > datetime.datetime.now() > tournoi["début_check-in"]):

        if message.content == "!in":
            participants[message.author.id]["checked_in"] = True
            await message.add_reaction("✅")

        elif message.content == "!out":
            challonge.participants.destroy(tournoi["id"], participants[message.author.id]['challonge'])
            await message.author.remove_roles(message.guild.get_role(challenger_id))
            del participants[message.author.id]
            await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"]).remove_reaction("✅", message.author)
            await message.add_reaction("✅")

        else:
            return

        with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
        await update_annonce()


### Régulièrement executé
@bot.event
async def check_tournament_state():

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    bracket = challonge.tournaments.show(tournoi["id"])

    ### Dès que le tournoi commence
    if (tournoi["statut"] == "pending") and (bracket['state'] != "pending"):

        await bot.get_channel(annonce_channel_id).send(f"{server_logo} Le tournoi **{tournoi['name']}** est officiellement lancé, voici le bracket : {tournoi['url']} *(vous pouvez y accéder à tout moment avec la commande `!bracket` sur Discord et Twitch)*")

        scorann = (f":information_source: La prise en charge des scores pour le tournoi **{tournoi['name']}** est automatisée :\n"
                   f":arrow_forward: Seul **le gagnant du set** envoie le score de son set, précédé par la **commande** `!win`.\n"
                   f":arrow_forward: Le message du score doit contenir le **format suivant** : `!win 2-0, 3-2, 3-1, ...`.\n"
                   f":arrow_forward: **Une vérification sera demandée**, vous devrez alors ajouter une réaction (:white_check_mark: / :x:).\n"
                   f":arrow_forward: Consultez le bracket afin de **vérifier** les informations : {tournoi['url']}\n"
                   f":arrow_forward: En cas de mauvais score : contactez un TO pour une correction manuelle.")

        await bot.get_channel(scores_channel_id).send(scorann)

        queue_annonce = ":information_source: Le lancement des sets est automatisé. **Veuillez suivre les consignes de ce channel**, que ce soit par le bot ou les TOs. Notez que tout passage on stream sera notifié à l'avance, ici et/ou par DM."

        await bot.get_channel(queue_channel_id).send(queue_annonce)

        tournoi_annonce = (f"<@&{challenger_id}> *On arrête le freeplay !* Le tournoi est sur le point de commencer. Petit rappel :\n"
                           f"- Vos sets sont annoncés dès que disponibles dans <#{queue_channel_id}> : **ne lancez rien sans consulter ce channel**.\n"
                           f"- Le ruleset ainsi que les informations pour le bannissement des stages sont dispo dans <#{ruleset_channel_id}>.\n"
                           f"- Le gagnant d'un set doit rapporter le score **dès que possible** dans <#{scores_channel_id}> avec la commande `!win`.\n"
                           f"- Si vous le souhaitez vraiment, vous pouvez toujours DQ du tournoi avec la commande `!dq` à tout moment.\n"
                           f"- En cas de lag qui rend votre set injouable, utilsiez la commande `!lag` pour résoudre la situation.\n\n"
                           f"*L'équipe de TO et moi-même vous souhaitons un excellent tournoi.*")

        await bot.get_channel(tournoi_channel_id).send(tournoi_annonce)

        tournoi["statut"] = "underway"
        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

        await calculate_top8()

    #### Si le tournoi est en cours
    elif bracket['state'] in ["in_progress", "underway"]:

        try:
            open_matches = challonge.matches.index(tournoi["id"], state="open")
            guild = bot.get_guild(id=guild_id)
            await launch_matches(open_matches, guild)
            await rappel_matches(open_matches, guild)
        except:
            pass

    ### Dès que le tournoi est terminé
    elif bracket['state'] in ["complete", "ended"]:

        scheduler.remove_job('check_tournament_state')

        await bot.get_channel(annonce_channel_id).send(f"{server_logo} Le tournoi **{tournoi['name']}** est terminé, merci à toutes et à tous d'avoir participé ! J'espère vous revoir bientôt.")

        guild = bot.get_guild(id=guild_id)
        challenger = guild.get_role(challenger_id)
        for inscrit in participants: await guild.get_member(inscrit).remove_roles(challenger)

        with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
        with open(tournoi_path, 'w') as f: json.dump({}, f, indent=4)
        with open(stream_path, 'w') as f: json.dump([], f, indent=4)

        await bot.change_presence(activity=discord.Game(version))


### Nettoyer les channels liés aux tournois
@bot.event
async def purge_channels():
    guild = bot.get_guild(id=guild_id)

    for category, channels in guild.by_category():

        if category != None:

            if category.id == tournoi_cat_id:
                for channel in channels:
                    async for message in channel.history():
                        await message.delete()

            if category.id == arenes_cat_id:
                for channel in channels:
                    await channel.delete()


### Affiche le bracket en cours
@bot.event
async def post_bracket(message):
    try:
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        await message.channel.send(f"{server_logo} **{tournoi['name']}** : {tournoi['url']}")
    except:
        await message.channel.send(":warning: Il n'y a pas de tournoi prévu à l'heure actuelle.")


### Pile/face basique
@bot.event
async def flipcoin(message):
    if message.content == "!flip":
        await message.channel.send(f"<@{message.author.id}> {random.choice(['Tu commences à faire les bans.', 'Ton adversaire commence à faire les bans.'])}")


### Ajout mannuel
@bot.event
async def add_inscrit(message):

    try:
        with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if (datetime.datetime.now() > tournoi["fin_check-in"]) or (len(participants) >= tournoi['limite']):
            await message.add_reaction("🚫")
            return

    except:
        await message.add_reaction("⚠️")
        return

    for member in message.mentions:

        if member.id not in participants:

            participants[member.id] = {
                "display_name" : member.display_name,
                "challonge" : challonge.participants.create(tournoi["id"], member.display_name)['id'],
                "checked_in" : False
            }

            if datetime.datetime.now() > tournoi["début_check-in"]:
                participants[member.id]["checked_in"] = True
                await member.add_roles(message.guild.get_role(challenger_id))

    with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
    await message.add_reaction("✅")


### Suppression/DQ manuel
@bot.event
async def remove_inscrit(message):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    for member in message.mentions:

        if member.id in participants:

            try:
                challonge.participants.destroy(tournoi["id"], participants[member.id]['challonge'])
            except:
                await message.add_reaction("⚠️")
                return

            if datetime.datetime.now() > tournoi["début_check-in"]:
                await member.remove_roles(message.guild.get_role(challenger_id))

            if datetime.datetime.now() < tournoi["end_check-in"]:
                await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"]).remove_reaction("✅", member)

            if tournoi["statut"] == "pending":
                del participants[member.id]
                with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
                await update_annonce()

    await message.add_reaction("✅")


### Se DQ soi-même
@bot.event
async def self_dq(message):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if message.author.id in participants:

        challonge.participants.destroy(tournoi["id"], participants[message.author.id]['challonge'])

        if datetime.datetime.now() > tournoi["début_check-in"]:
            await message.author.remove_roles(message.guild.get_role(challenger_id))

        if datetime.datetime.now() < tournoi["end_check_in"]:
            await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"]).remove_reaction("✅", message.author)

        if tournoi["statut"] == "pending":
            del participants[message.author.id]
            with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
            await update_annonce()

        await message.add_reaction("✅")

    else:
        await message.add_reaction("⚠️")


### Gestion des scores
@bot.event
async def score_match(message):

    try:
        with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        with open(stream_path, 'r+') as f: stream = json.load(f)

        if tournoi["statut"] != "underway": return

        winner = participants[message.author.id]["challonge"] # Le gagnant est celui qui poste
        match = challonge.matches.index(tournoi['id'], state="open", participant_id=winner)

        if match == []: return

    except:
        await message.add_reaction("⚠️")
        return


    try:
        score = re.search(r'([0-9]+) *\- *([0-9]+)', message.content).group().replace(" ", "")

    except:
        await message.add_reaction("⚠️")
        await message.channel.send(f"<@{message.author.id}> **Ton score ne possède pas le bon format** *(3-0, 2-1, 3-2...)*, merci de le rentrer à nouveau.")
        return

    else:
        if score[0] < score[2]: score = score[::-1] # Le premier chiffre doit être celui du gagnant

        aimed_score = 3 if is_top8(match[0]["round"]) else 2
        
        if score[0] < aimed_score:
            await message.add_reaction("⚠️")
            await message.channel.send(f"<@{message.author.id}> **Ton score est incorrect**. Rappel : BO3 jusqu'à top 8 qui a lieu en BO5.")
            return

        for joueur in participants:
            if participants[joueur]["challonge"] == match[0]["player1_id"]: player1 = joueur
            if participants[joueur]["challonge"] == match[0]["player2_id"]: player2 = joueur

        if winner == participants[player2]["challonge"]:
            score = score[::-1] # Le score doit suivre le format "player1-player2" pour scores_csv
            looser = player1
        else:
            looser = player2


    try:
        confirmation = message.channel.send(f"<@{message.author.id}> Confirmes-tu que tu as gagné **{score}** contre **{participants[looser]['display_name']}** ?")
        confirmation.add_reaction("✅")
        confirmation.add_reaction("❌")

        def check(reaction, user):
            return (user == message.author) and (str(reaction.emoji) in ["✅", "❌"]) and (reaction.message.id == confirmation.id)

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=20.0, check=check)

        except asyncio.TimeoutError:
            await message.channel.send(f"<@{message.author.id}> Tu n'as pas confirmé à temps, merci de rentrer ton score à nouveau puis de confirmer.")
            await message.add_reaction("❌")
            return

        else:
            if str(reaction.emoji) == "❌":
                await message.add_reaction("❌")
                return

        challonge.matches.update(tournoi['id'], match[0]["id"], scores_csv=score, winner_id=winner)

        if match[0]["suggested_play_order"] == tournoi["on_stream"]:
            tournoi["on_stream"] = None
            with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
            await call_stream()

    except:
        await message.add_reaction("⚠️")

    else:
        await message.add_reaction("✅")


### Lancer matchs ouverts
@bot.event
async def launch_matches(bracket, guild):

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
                    category=arenes)

            except:
                gaming_channel_txt = f":video_game: Je n'ai pas pu créer de channel, faites votre set en MP ou dans <#{tournoi_channel_id}>."

                if match["suggested_play_order"] in stream:
                    await player1.send(f"Tu joueras on stream pour ton prochain set contre **{player2.display_name}** : je te communiquerai les codes d'accès de l'arène quand ce sera ton tour.")
                    await player2.send(f"Tu joueras on stream pour ton prochain set contre **{player1.display_name}** : je te communiquerai les codes d'accès de l'arène quand ce sera ton tour.")

            else:
                gaming_channel_txt = f":video_game: Allez faire votre set dans le channel <#{gaming_channel.id}> !"

                gaming_channel_annonce = (f":arrow_forward: Ce channel a été créé pour le set suivant : <@{player1.id}> vs <@{player2.id}>\n"
                                          f"- Les règles du set doivent suivre celles énoncées dans <#{ruleset_channel_id}> (doit être lu au préalable).\n"
                                          f"- La liste des stages légaux à l'heure actuelle est toujours disponible via la commande `!stages`.\n"
                                          f"- En cas de lag qui rend la partie injouable, utilisez la commande `!lag` pour résoudre la situation.\n"
                                          f"- **Dès que le set est terminé**, le gagnant envoie le score dans <#{scores_channel_id}> avec la commande `!win`.\n\n"
                                          f":game_die: **{random.choice([player1.display_name, player2.display_name])}** est tiré au sort pour commencer le ban des stages.\n")

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

            sets += f":arrow_forward: À lancer : <@{player1.id}> vs <@{player2.id}> {on_stream}\n{gaming_channel_txt} {top_8}\n\n"

    if sets != "": await bot.get_channel(queue_channel_id).send(sets)


### Ajout ID et MDP d'arène de stream
@bot.event
async def setup_stream(message):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    arene = message.content.replace("!setstream ", "").split()

    if len(arene) == 2:
        tournoi["stream"] = arene
        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
        await message.add_reaction("✅")

    else:
        await message.add_reaction("⚠️")


### Ajouter un set dans la stream queue
@bot.event
async def add_stream(message):

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    try:
        to_add = list(map(int, message.content.replace("!addstream ", "").split()))
        bracket = challonge.matches.index(tournoi['id'], state=("open", "pending"))

    except:
        await message.add_reaction("⚠️")
        return

    for order in to_add:
        for match in bracket:
            if (match["suggested_play_order"] == order) and (match["underway_at"] == None) and (order not in stream):
                stream.append(order)
                break

    with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
    await message.add_reaction("✅")


### Enlever un set de la stream queue
@bot.event
async def remove_stream(message):

    if message.content == "!rmstream queue": # Reset la stream queue
        with open(stream_path, 'w') as f: json.dump([], f, indent=4)
        await message.add_reaction("✅")

    elif message.content == "!rmstream now": # Reset le set on stream
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        tournoi["on_stream"] = None
        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
        await message.add_reaction("✅")

    else:
        try:
            with open(stream_path, 'r+') as f: stream = json.load(f)
            for order in list(map(int, message.content.replace("!rmstream ", "").split())): stream.remove(order)
            with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)
            await message.add_reaction("✅")
        except:
            await message.add_reaction("⚠️")


### Infos stream
@bot.event
async def list_stream(message):

    try:
        with open(stream_path, 'r+') as f: stream = json.load(f)
        with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
        bracket = challonge.matches.index(tournoi['id'], state=("open", "pending"))
    except:
        await message.add_reaction("⚠️")
        return

    msg = f":information_source: Arène de stream :\n- **ID** : `{tournoi['stream'][0]}`\n- **MDP** : `{tournoi['stream'][1]}`\n"

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

                list_stream += f"**{match['suggested_play_order']}** : *{player1}* vs *{player2}*\n"
                break

    if list_stream != "":
        msg += f":play_pause: Liste des sets prévus pour passer on stream prochainement :\n{list_stream}"
    else:
        msg += ":play_pause: Il n'y a aucun set prévu pour passer on stream prochainement."

    await message.channel.send(msg)


### Appeler les joueurs on stream
@bot.event
async def call_stream():

    bracket = challonge.matches.index(tournoi["id"], state="open")
    guild = bot.get_guild(id=guild_id)

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if stream == [] or tournoi["on_stream"] != None: return

    for match in bracket:

        if (match["suggested_play_order"] == stream[0]) and (match["underway_at"] != None):

            for joueur in participants:
                if participants[joueur]["challonge"] == match["player1_id"]: player1 = guild.get_member(joueur)
                if participants[joueur]["challonge"] == match["player2_id"]: player2 = guild.get_member(joueur)

            gaming_channel = discord.utils.get(guild.text_channels, name=str(match["suggested_play_order"]))

            if gaming_channel == None:
                await player1.send(f"C'est ton tour de passer on stream ! N'oublie pas de donner les scores dès que le set est fini. Voici les codes d'accès de l'arène :\n:arrow_forward: **ID** : `{tournoi['stream'][0]}`\n:arrow_forward: **MDP** : `{tournoi['stream'][1]}`")
                await player2.send(f"C'est ton tour de passer on stream ! N'oublie pas de donner les scores dès que le set est fini. Voici les codes d'accès de l'arène :\n:arrow_forward: **ID** : `{tournoi['stream'][0]}`\n:arrow_forward: **MDP** : `{tournoi['stream'][1]}`")
            else:
                await gaming_channel.send(f":clapper: C'est votre tour de passer on stream ! **N'oubliez pas de donner les scores dès que le set est fini.**\n\nVoici les codes d'accès de l'arène :\n:arrow_forward: **ID** : `{tournoi['stream'][0]}`\n:arrow_forward: **MDP** : `{tournoi['stream'][1]}`")

            await bot.get_channel(stream_channel_id).send(f":arrow_forward: Envoi on stream du set n°{match['suggested_play_order']} : **{participants[player1.id]['display_name']}** vs **{participants[player2.id]['display_name']}** !")

            tournoi["on_stream"] = match["suggested_play_order"]
            with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

            while match["suggested_play_order"] in stream: stream.remove(match["suggested_play_order"])
            with open(stream_path, 'w') as f: json.dump(stream, f, indent=4)

            break


### Calculer les rounds à partir desquels un set est top 8 (bracket D.E.)
@bot.event
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

    await bot.get_channel(tournoi_channel_id).send(f":fire: Le **top 8** commencera, d'après le bracket :\n- En **winner round {tournoi['round_winner_top8']}** (semi-finales)\n- En **looser round {-tournoi['round_looser_top8']}**")


### Appeler les joueurs on stream
@bot.event
async def rappel_matches(bracket, guild):
    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    for match in bracket:

        if (match["underway_at"] != None) and (match["suggested_play_order"] not in stream) and (match["suggested_play_order"] != tournoi["on_stream"]):

            debut_set = dateutil.parser.parse(str(match["underway_at"])).replace(tzinfo=None)
            seuil = 42 if is_top8(match["round"]) else 28 # Calculé selon (tps max match * nb max matchs) + 7 minutes

            if datetime.datetime.now() - debut_set > datetime.timedelta(minutes = seuil):

                gaming_channel = discord.utils.get(guild.text_channels, name=str(match["suggested_play_order"]))

                if gaming_channel != None:

                    for joueur in participants:
                        if participants[joueur]["challonge"] == match["player1_id"]: player1 = guild.get_member(joueur)
                        if participants[joueur]["challonge"] == match["player2_id"]: player2 = guild.get_member(joueur)

                    # Avertissement
                    if match["suggested_play_order"] not in tournoi["warned"]:

                        alerte = (f":timer: **Je n'ai toujours pas reçu de score pour ce set !** <@{player1.id}> <@{player2.id}>\n"
                                  f"- Merci de le poster dans <#{scores_channel_id}> dès que possible.\n"
                                  f"- Au-delà d'un certain temps, la dernière personne ayant été active sur ce channel sera déclarée vainqueur.\n"
                                  f"- La personne ayant été inactive (d'après le dernier message posté) sera **DQ sans concession** du tournoi.")

                        await gaming_channel.send(alerte)

                        tournoi["warned"].append(match["suggested_play_order"])
                        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

                    # DQ pour inactivité (exceptionnel...) -> fixé à 10 minutes après l'avertissement
                    elif (match["suggested_play_order"] in tournoi["warned"]) and (datetime.datetime.now() - debut_set > datetime.timedelta(minutes = seuil + 10)):

                        async for message in gaming_channel.history(): # Rechercher qui est la dernière personne activve du channel
                            if message.author != bot.user:
                                winner = message.author
                                break

                        to_dq = player2 if winner.id == player1.id else player1

                        await bot.get_channel(tournoi_channel_id).send(f"<@&{to_id}> **Une DQ automatique a été executée pour inactivité :**\n-<@{winner}> passe au round suivant.\n-<@{to_dq}> est DQ du tournoi.")

                        try:
                            await to_dq.send("Désolé, mais tu as été DQ du tournoi pour inactivité. Ceci est un message automatique, pour toute plainte merci de contacter les TOs.")
                        except:
                            pass
                        
                        challonge.participants.destroy(tournoi["id"], participants[to_dq.id]['challonge'])
                        await to_dq.remove_roles(guild.get_role(challenger_id))

### Obtenir stagelist
@bot.event
async def get_stagelist(message):
    with open(stagelist_path, 'r+') as f: stagelist = yaml.load(f)

    msg = ":map: **Voici la liste des stages légaux à l'heure actuelle :**\n"
    for stage in stagelist["liste"]: msg += f"- {stage}\n"

    await message.channel.send(msg)


### Si administrateur
@bot.event
async def author_is_admin(message):

    if to_id in [y.id for y in message.author.roles]:
        return True

    else:
        await message.add_reaction("🚫")
        return False


### À chaque ajout de réaction
@bot.event
async def on_raw_reaction_add(event):
    if event.user_id == bot.user.id: return

    if (event.emoji.name == "✅") and (event.channel_id == inscriptions_channel_id):

        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if event.message_id == tournoi["annonce_id"]:
            await inscrire(event.member) # available for REACTION_ADD only


### À chaque suppression de réaction
@bot.event
async def on_raw_reaction_remove(event):
    if event.user_id == bot.user.id: return

    if (event.emoji.name == "✅") and (event.channel_id == inscriptions_channel_id):

        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if event.message_id == tournoi["annonce_id"]:
            await desinscrire(bot.get_guild(id=guild_id).get_member(event.user_id)) # event.member not available for REACTION_REMOVE


### À chaque message
@bot.event
async def on_message(message):

    if message.author.id == bot.user.id: return

    elif message.channel.id == check_in_channel_id: await check_in(message)

    elif message.content == '!flip': await flipcoin(message)

    elif (message.channel.id == scores_channel_id) and (message.content.startswith("!win ")): await score_match(message)

    elif message.content == '!bracket': await post_bracket(message)

    elif message.content == '!dq': await self_dq(message)

    elif message.content == '!help': await message.channel.send(help_text)

    elif message.content == '!lag': await message.channel.send(lag_text)

    elif message.content == '!stages': await get_stagelist(message)

    elif ((message.content in ["!purge", "!stream"] or message.content.startswith(('!setup ', '!rm ', '!add ', '!setstream ', '!addstream ', '!rmstream ')))) and (await author_is_admin(message)):
        if message.content == '!purge': await purge_channels()
        elif message.content == '!stream': await list_stream(message)
        elif message.content.startswith('!setup '): await setup_tournament(message)
        elif message.content.startswith('!rm '): await remove_inscrit(message)
        elif message.content.startswith('!add '): await add_inscrit(message)
        elif message.content.startswith('!setstream '): await setup_stream(message)
        elif message.content.startswith('!addstream '): await add_stream(message)
        elif message.content.startswith('!rmstream '): await remove_stream(message)



#### Scheduler
scheduler.start()

#### Lancement du bot
bot.run(bot_secret)

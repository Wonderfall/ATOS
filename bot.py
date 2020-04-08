import discord, random, logging, os, json, re, challonge, dateutil.parser, datetime, asyncio, yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from babel.dates import format_date, format_time

with open('data/config.yml', 'r+') as f: config = yaml.safe_load(f)

if config["system"]["debug"] == True: logging.basicConfig(level=logging.DEBUG)

#### Version
version                             = "4.19"

### File paths
tournoi_path                        = config["paths"]["tournoi"]
participants_path                   = config["paths"]["participants"]
waiting_list_path                   = config["paths"]["waiting_list"]
stream_path                         = config["paths"]["stream"]
stagelist_path                      = config["paths"]["stagelist"]

### Locale
language                            = config["system"]["language"]

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
resultats_channel_id                = config["discord"]["channels"]["resultats"]
roles_channel_id                    = config["discord"]["channels"]["roles"]

### Info, non-interactive channels
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
Je t'invite à consulter le channel <#{deroulement_channel_id}>, et également <#{inscriptions_channel_id}> si tu souhaites t'inscrire à un tournoi.
N'oublie pas de consulter les <#{annonce_channel_id}> régulièrement, et de poser tes questions aux TOs sur <#{faq_channel_id}>.

Je te conseille de t'attribuer un rôle dans <#{roles_channel_id}> par la même occasion.

Enfin, amuse-toi bien !
"""

help_text=f"""
:cd: **Commandes user :**
:white_small_square: `!help` : c'est la commande que tu viens de rentrer.
:white_small_square: `!bracket` : obtenir le lien du bracket en cours.

:video_game: **Commandes joueur :**
:white_small_square: `!dq` : se retirer du tournoi avant/après (DQ) que celui-ci ait commencé.
:white_small_square: `!flip` : pile/face simple, fonctionne dans tous les channels.
:white_small_square: `!win` : rentrer le score d'un set dans <#{scores_channel_id}> *(paramètre : score)*.
:white_small_square: `!stages` : obtenir la stagelist légale actuelle.
:white_small_square: `!lag` : ouvrir une procédure de lag, à utiliser avec parcimonie.
:white_small_square: `!desync` : obtenir une notice d'aide en cas de desync sur Project+ - Dolphin Netplay.

:no_entry_sign: **Commandes administrateur :**
:white_small_square: `!purge` : purifier les channels relatifs à un tournoi.
:white_small_square: `!setup` : initialiser un tournoi *(paramètre : lien challonge valide)*.
:white_small_square: `!rm` : désinscrire/retirer (DQ) quelqu'un du tournoi *(paramètre : @mention | liste)*.
:white_small_square: `!add` : ajouter quelqu'un au tournoi *(paramètre : @mention | liste)*.

:tv: **Commandes stream :**
:white_small_square: `!stream` : obtenir toutes les informations relatives au stream (IDs, on stream, queue).
:white_small_square: `!setstream` : mettre en place l'arène de stream *(2 paramètres : ID MDP)*.
:white_small_square: `!addstream` : ajouter un set à la stream queue *(paramètre : n° | liste de n°)*.
:white_small_square: `!rmstream` : retirer un set de la stream queue *(paramètre : n° | queue | now)*.

*Version {version}, made by Wonderfall with :heart:*
"""

lag_text=f"""
:satellite: **Un lag a été constaté**, les <@&{to_id}> sont contactés.

:one: En attendant, chaque joueur peut :
:white_small_square: Vérifier qu'aucune autre connexion locale ne pompe la connexion.
:white_small_square: S'assurer que la connexion au réseau est, si possible, câblée.
:white_small_square: S'assurer qu'il/elle n'emploie pas un partage de connexion de réseau mobile (passable de DQ).

:two: Si malgré ces vérifications la connexion n'est pas toujours pas satisfaisante, chaque joueur doit :
:white_small_square: Préparer un test de connexion *(Switch pour Ultimate, Speedtest pour Project+)*.
:white_small_square: Décrire sa méthode de connexion actuelle *(Wi-Fi, Ethernet direct, CPL -> ADSL, FFTH, 4G...)*.

:three: Si nécessaire, un TO s'occupera de votre cas et proposera une arène avec le/les joueur(s) problématique(s).
"""

desync_text=f"""
:one: **Détecter une desync sur Project+ (Dolphin Netplay) :**
:white_small_square: Une desync résulte dans des inputs transmis au mauvais moment (l'adversaire SD à répétition, etc.).
:white_small_square: Si Dolphin affiche qu'une desync a été détectée, c'est probablement le cas.

:two: **Résoudre une desync, les 2 joueurs : **
:white_small_square: Peuvent avoir recours à une __personne de tierce partie__ pour déterminer le fautif.
:white_small_square: S'assurent qu'ils ont bien procédé à __l'ECB fix__ tel que décrit dans le tutoriel FR.
:white_small_square: Vérifient depuis la fenêtre netplay que leur carte SD virtuelle a un hash MD5 égal à :
```
9b1bf61cf106b70ecbc81c1e70aed0f7
```
:white_small_square: Doivent vérifier que leur __ISO possède un hash MD5 inclus__ dans la liste compatible :
```
d18726e6dfdc8bdbdad540b561051087
d8560b021835c9234c28be7ff9bcaaeb
5052e2e15f22772ab6ce4fd078221e96
52ce7160ced2505ad5e397477d0ea4fe
9f677c78eacb7e9b8617ab358082be32
1c4d6175e3cbb2614bd805d32aea7311
```
*ISO : clic droit sur \"Super Smash Bros Brawl\" > Onglet \"Info\" > Ligne \"MD5 Checksum\".
SD : en haut à droite d'une fenêtre netplay, cliquer sur \"MD5 Check\" et choisir \"SD card\".*

:three: **Si ces informations ne suffisent pas, contactez un TO.**
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

### Accès stream
def get_access_stream():
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if tournoi['game'] == 'Project+':
        return f":white_small_square: **Accès host Dolphin Netplay** : `{tournoi['stream'][0]}`"

    elif tournoi['game'] == 'Super Smash Bros. Ultimate':
        return f":white_small_square: **ID** : `{tournoi['stream'][0]}`\n:white_small_square: **MDP** : `{tournoi['stream'][1]}`"


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
    except:
        await bot.get_channel(blabla_channel_id).send(f"{message} {welcome_text}")
    else:
        await bot.get_channel(blabla_channel_id).send(message) # Avoid sending welcome_text to the channel if possible


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
        "game": bracket["game_name"].title(), # Non-recognized games are lowercase for Challonge
        "url": url,
        "id": bracket["id"],
        "limite": bracket["signup_cap"],
        "statut": bracket["state"],
        "début_tournoi": dateutil.parser.parse(str(bracket["start_at"])).replace(tzinfo=None),
        "début_check-in": dateutil.parser.parse(str(bracket["start_at"])).replace(tzinfo=None) - datetime.timedelta(hours = 1),
        "fin_check-in": dateutil.parser.parse(str(bracket["start_at"])).replace(tzinfo=None) - datetime.timedelta(minutes = 10),
        "on_stream": None,
        "stream": ["N/A", "N/A"],
        "warned": [],
        "timeout": []
    }

    return tournoi


### Ajouter un tournoi
@bot.event
async def setup_tournament(message):

    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    url = message.content.replace("!setup ", "")
    tournoi = await get_tournament(url)

    if tournoi == None:
        await message.add_reaction("⚠️")
        return

    elif datetime.datetime.now() > tournoi["début_tournoi"]:
        await message.add_reaction("🕐")
        return

    elif tournoi['game'] not in stagelist:
        await message.add_reaction("❔")
        return

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
    with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
    with open(waiting_list_path, 'w') as f: json.dump({}, f, indent=4)
    with open(stream_path, 'w') as f: json.dump([], f, indent=4)

    await annonce_inscription()

    scheduler.add_job(start_check_in, id='start_check_in', run_date=tournoi["début_check-in"], replace_existing=True)
    scheduler.add_job(end_check_in, id='end_check_in', run_date=tournoi["fin_check-in"], replace_existing=True)
    scheduler.add_job(check_tournament_state, 'interval', id='check_tournament_state', minutes=2, replace_existing=True)

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
        scheduler.add_job(check_tournament_state, 'interval', id='check_tournament_state', minutes=2, replace_existing=True)

        if tournoi["statut"] == "underway":
            scheduler.add_job(launch_matches, 'interval', id='launch_matches', minutes=1, replace_existing=True)
            scheduler.add_job(rappel_matches, 'interval', id='rappel_matches', minutes=1, replace_existing=True)

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

    except:
        print("No tournament had to be reloaded.")
        pass


### Annonce l'inscription
@bot.event
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


### Inscription
@bot.event
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
        except:
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
        except:
            pass


### Mettre à jour la liste d'attente
@bot.event
async def update_waiting_list():

    with open(waiting_list_path, 'r+') as f: waiting_list = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    old_waiting_list = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["waiting_list_id"])

    new_waiting_list = ":hourglass: __Liste d'attente__ :\n"

    for joueur in waiting_list:
        new_waiting_list += f":white_small_square: {waiting_list[joueur]['display_name']}\n"

    await old_waiting_list.edit(content=new_waiting_list)


### Désinscription
@bot.event
async def desinscrire(member):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(waiting_list_path, 'r+') as f: waiting_list = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if member.id in participants:
        challonge.participants.destroy(tournoi["id"], participants[member.id]['challonge'])

        if datetime.datetime.now() > tournoi["début_check-in"]:
            try:
                await member.remove_roles(member.guild.get_role(challenger_id))
            except:
                pass

        if datetime.datetime.now() < tournoi["fin_check-in"]:

            try:
                inscription = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
                await inscription.remove_reaction("✅", member)
            except:
                pass

            del participants[member.id]

            try:
                next_waiting_player = next(iter(waiting_list))

            except StopIteration:
                pass

            else:
                participants[next_waiting_player] = waiting_list[next_waiting_player]
                participants[next_waiting_player]["checked_in"] = False
                participants[next_waiting_player]["challonge"] = challonge.participants.create(tournoi["id"], participants[next_waiting_player]["display_name"])['id']

                del waiting_list[next_waiting_player]
                with open(waiting_list_path, 'w') as f: json.dump(waiting_list, f, indent=4)

                await update_waiting_list()

                try:
                    await member.guild.get_member(next_waiting_player).send(f"Bonne nouvelle, une place s'est libérée ! Tu es inscrit(e) pour le tournoi **{tournoi['name']}**.")
                except:
                    pass

            with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)

            await update_annonce()

            try:
                await member.send(f"Tu es désinscrit(e) du tournoi **{tournoi['name']}**. À une prochaine fois peut-être !")
            except:
                pass

    elif member.id in waiting_list:
        del waiting_list[member.id]
        with open(waiting_list_path, 'w') as f: json.dump(waiting_list, f, indent=4)
        await update_waiting_list()


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

    await bot.get_channel(inscriptions_channel_id).send(f":information_source: Le check-in a commencé dans <#{check_in_channel_id}>. "
                                                        f"Vous pouvez toujours vous inscrire ici jusqu'à **{format_time(tournoi['fin_check-in'], format='short', locale=language)}** tant qu'il y a de la place.")

    await bot.get_channel(check_in_channel_id).send(f"<@&{challenger_id}> Le check-in pour **{tournoi['name']}** a commencé : "
                                                    f"vous avez jusqu'à **{format_time(tournoi['fin_check-in'], format='short', locale=language)}** pour signaler votre présence :\n"
                                                    f":white_small_square: Utilisez `!in` pour confirmer votre inscription\n:white_small_square: Utilisez `!out` pour vous désinscrire\n\n"
                                                    f"*Si vous n'avez pas check-in à temps, vous serez désinscrit automatiquement du tournoi.*")


### Rappel de check-in
@bot.event
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
                except:
                    pass

    if rappel_msg != "":
        await bot.get_channel(check_in_channel_id).send(f":clock1: **Rappel de check-in !**\n{rappel_msg}\n"
                                                        f"*Vous avez jusqu'à {format_time(tournoi['fin_check-in'], format='short', locale=language)}, sinon vous serez désinscrit(s) automatiquement.*")


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

    for inscrit in list(participants):
        if participants[inscrit]["checked_in"] == False:
            challonge.participants.destroy(tournoi["id"], participants[inscrit]['challonge'])
            try:
                to_dq = guild.get_member(inscrit)
                await to_dq.remove_roles(guild.get_role(challenger_id))
                await to_dq.send(f"Tu as été DQ du tournoi {tournoi['name']} car tu n'as pas check-in à temps, désolé !")
            except:
                pass
            del participants[inscrit]

    with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
    await update_annonce()

    annonce = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
    await annonce.clear_reaction("✅")

    await bot.get_channel(check_in_channel_id).send(":clock1: **Le check-in est terminé.** Les personnes n'ayant pas check-in ont été retirées du bracket. Contactez les TOs en cas de besoin.")
    await bot.get_channel(inscriptions_channel_id).send(":clock1: **Les inscriptions sont fermées.** Le tournoi débutera dans les minutes qui suivent : le bracket est en cours de finalisation. Contactez les TOs en cas de besoin.")


### Prise en charge du check-in et check-out
@bot.event
async def check_in(message):

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    if (message.author.id in participants) and (tournoi["fin_check-in"] > datetime.datetime.now() > tournoi["début_check-in"]):

        if message.content == "!in":
            participants[message.author.id]["checked_in"] = True
            with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
            await message.add_reaction("✅")

        elif message.content == "!out":
            challonge.participants.destroy(tournoi["id"], participants[message.author.id]['challonge'])
            await message.author.remove_roles(message.guild.get_role(challenger_id))
            del participants[message.author.id]
            with open(participants_path, 'w') as f: json.dump(participants, f, indent=4)
            inscription = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
            await inscription.remove_reaction("✅", message.author)
            await message.add_reaction("✅")

        else:
            return

        await update_annonce()


### Régulièrement executé
@bot.event
async def check_tournament_state():

    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    bracket = challonge.tournaments.show(tournoi["id"])

    ### Dès que le tournoi commence
    if (tournoi["statut"] == "pending") and (bracket['state'] == "underway"):

        await calculate_top8()

        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser) # Refresh to get top 8
        with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

        await bot.get_channel(annonce_channel_id).send(f"{server_logo} Le tournoi **{tournoi['name']}** est officiellement lancé, voici le bracket : {tournoi['url']} *(vous pouvez y accéder à tout moment avec la commande `!bracket` sur Discord et Twitch)*")

        scorann = (f":information_source: La prise en charge des scores pour le tournoi **{tournoi['name']}** est automatisée :\n"
                   f":white_small_square: Seul **le gagnant du set** envoie le score de son set, précédé par la **commande** `!win`.\n"
                   f":white_small_square: Le message du score doit contenir le **format suivant** : `!win 2-0, 3-2, 3-1, ...`.\n"
                   f":white_small_square: Un mauvais score intentionnel, perturbant le déroulement du tournoi, est **passable de DQ et ban**.\n"
                   f":white_small_square: Consultez le bracket afin de **vérifier** les informations : {tournoi['url']}\n"
                   f":white_small_square: En cas de mauvais score : contactez un TO pour une correction manuelle.")

        await bot.get_channel(scores_channel_id).send(scorann)

        queue_annonce = ":information_source: Le lancement des sets est automatisé. **Veuillez suivre les consignes de ce channel**, que ce soit par le bot ou les TOs. Notez que tout passage on stream sera notifié à l'avance, ici et/ou par DM."

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

        tournoi["statut"] = "underway"
        with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)

        scheduler.add_job(launch_matches, 'interval', id='launch_matches', minutes=1, replace_existing=True)
        scheduler.add_job(rappel_matches, 'interval', id='rappel_matches', minutes=1, replace_existing=True)


    ### Dès que le tournoi est terminé
    elif bracket['state'] in ["complete", "ended"]:

        scheduler.remove_job('launch_matches')
        scheduler.remove_job('rappel_matches')

        scheduler.remove_job('check_tournament_state')

        await annonce_resultats()

        await bot.get_channel(annonce_channel_id).send(f"{server_logo} Le tournoi **{tournoi['name']}** est terminé, merci à toutes et à tous d'avoir participé ! J'espère vous revoir bientôt.")

        guild = bot.get_guild(id=guild_id)
        challenger = guild.get_role(challenger_id)

        for inscrit in participants:
            try:
                await guild.get_member(inscrit).remove_roles(challenger)
            except:
                pass

        with open(participants_path, 'w') as f: json.dump({}, f, indent=4)
        with open(waiting_list_path, 'w') as f: json.dump({}, f, indent=4)
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


### Ajout manuel
@bot.event
async def add_inscrit(message):

    try:
        with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
        with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

        if datetime.datetime.now() > tournoi["fin_check-in"]:
            await message.add_reaction("🚫")
            return

    except:
        await message.add_reaction("⚠️")
        return

    for member in message.mentions: await inscrire(member)
    await message.add_reaction("✅")


### Suppression/DQ manuel
@bot.event
async def remove_inscrit(message):
    for member in message.mentions: await desinscrire(member)
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

        if datetime.datetime.now() < tournoi["fin_check-in"]:
            inscription = await bot.get_channel(inscriptions_channel_id).fetch_message(tournoi["annonce_id"])
            await inscription.remove_reaction("✅", message.author)

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

        if match[0]["underway_at"] == None:
            await message.channel.send(f"<@{message.author.id}> Huh, le set pour lequel tu as donné le score n'a **pas encore commencé** !")
            return

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

        if is_top8(match[0]["round"]):
            aimed_score, looser_score, temps_min = 3, [0, 1, 2], 10
        else:
            aimed_score, looser_score, temps_min = 2, [0, 1], 5

        debut_set = dateutil.parser.parse(str(match[0]["underway_at"])).replace(tzinfo=None)

        if (int(score[0]) < aimed_score) or (int(score[2]) not in looser_score) or (datetime.datetime.now() - debut_set < datetime.timedelta(minutes = temps_min)):
            await message.add_reaction("⚠️")
            await message.channel.send(f"<@{message.author.id}> **Score incorrect**, ou temps écoulé trop court. Rappel : BO3 jusqu'au top 8 qui a lieu en BO5.")
            return

        for joueur in participants:
            if participants[joueur]["challonge"] == match[0]["player1_id"]: player1 = joueur
            if participants[joueur]["challonge"] == match[0]["player2_id"]: player2 = joueur

        og_score = score

        if winner == participants[player2]["challonge"]:
            score = score[::-1] # Le score doit suivre le format "player1-player2" pour scores_csv

    try:
        challonge.matches.update(tournoi['id'], match[0]["id"], scores_csv=score, winner_id=winner)
        await message.add_reaction("✅")

    except:
        await message.add_reaction("⚠️")

    else:
        gaming_channel = discord.utils.get(message.guild.text_channels, name=str(match[0]["suggested_play_order"]))

        if gaming_channel != None:
            await gaming_channel.send(f":bell: __Score rapporté__ : **{participants[message.author.id]['display_name']}** gagne **{og_score}** !\n"
                                      f"*En cas d'erreur, appelez un TO ! Un mauvais score intentionnel est passable de DQ et ban du tournoi.*")

        if match[0]["suggested_play_order"] == tournoi["on_stream"]:
            tournoi["on_stream"] = None
            with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
            await call_stream()


### Lancer matchs ouverts
@bot.event
async def launch_matches():

    guild = bot.get_guild(id=guild_id)

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    bracket = challonge.matches.index(tournoi["id"], state="open")

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

                with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

                gaming_channel_annonce = (f":arrow_forward: Ce channel a été créé pour le set suivant : <@{player1.id}> vs <@{player2.id}>\n"
                                          f":white_small_square: Les règles du set doivent suivre celles énoncées dans <#{stagelist[tournoi['game']]['ruleset']}> (doit être lu au préalable).\n"
                                          f":white_small_square: La liste des stages légaux à l'heure actuelle est toujours disponible via la commande `!stages`.\n"
                                          f":white_small_square: En cas de lag qui rend la partie injouable, utilisez la commande `!lag` pour résoudre la situation.\n"
                                          f":white_small_square: **Dès que le set est terminé**, le gagnant envoie le score dans <#{scores_channel_id}> avec la commande `!win`.\n\n"
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

            sets += f":arrow_forward: **{nom_round(match['round'])}** : <@{player1.id}> vs <@{player2.id}> {on_stream}\n{gaming_channel_txt} {top_8}\n\n"

    if sets != "": await bot.get_channel(queue_channel_id).send(sets)


### Ajout ID et MDP d'arène de stream
@bot.event
async def setup_stream(message):

    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    arene = message.content.replace("!setstream ", "").split()

    if tournoi['game'] == 'Super Smash Bros. Ultimate' and len(arene) == 2:
        tournoi["stream"] = arene

    elif tournoi['game'] == 'Project+' and len(arene) == 1:
        tournoi["stream"] = arene

    else:
        await message.add_reaction("⚠️")
        return

    with open(tournoi_path, 'w') as f: json.dump(tournoi, f, indent=4, default=dateconverter)
    await message.add_reaction("✅")


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

    await message.channel.send(msg)


### Appeler les joueurs on stream
@bot.event
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


### Lancer un rappel de matchs
@bot.event
async def rappel_matches():

    guild = bot.get_guild(id=guild_id)

    with open(stream_path, 'r+') as f: stream = json.load(f)
    with open(participants_path, 'r+') as f: participants = json.load(f, object_pairs_hook=int_keys)
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)

    bracket = challonge.matches.index(tournoi["id"], state="open")

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
                                except:
                                    winner, winner_last_activity = message.author, message.created_at # Le premier résultat sera assigné à winner
                                else:
                                    if message.author != winner:
                                        looser, looser_last_activity = message.author, message.created_at # Le second résultat sera assigné à looser
                                        break
                        
                        try:
                            winner
                        except: # S'il n'y a jamais eu de résultat, aucun joueur n'a donc été actif : DQ des deux 
                            await gaming_channel.send(f"<@&{to_id}> **DQ automatique des __2 joueurs__ pour inactivité : <@{player1.id}> & <@{player2.id}>**")
                            challonge.participants.destroy(tournoi["id"], participants[player1.id]['challonge'])
                            challonge.participants.destroy(tournoi["id"], participants[player2.id]['challonge'])
                            continue

                        try:
                            looser
                        except: # S'il n'y a pas eu de résultat pour un second joueur différent : DQ de l'inactif
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
@bot.event
async def get_stagelist(message):
    with open(tournoi_path, 'r+') as f: tournoi = json.load(f, object_hook=dateparser)
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    try:
        msg = f":map: **Stages légaux pour {tournoi['game']} :**\n:white_small_square: __Starters__ :\n"
        for stage in stagelist[tournoi['game']]['starters']: msg += f"- {stage}\n"

        if 'counterpicks' in stagelist[tournoi['game']]:
            msg += ":white_small_square: __Counterpicks__ :\n"
            for stage in stagelist[tournoi['game']]['counterpicks']: msg += f"- {stage}\n"

        await message.channel.send(msg)

    except:
        await message.channel.send(":warning: Aucun tournoi n'est en cours, je ne peux pas fournir de stagelist pour un jeu inconnu.")


### Lag
@bot.event
async def send_lag_text(message):
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
                    "- Le ping doit rester en-dessous de 40ms si possible, si ce n'est pas le cas : augmenter le buffer à 6 ou 8.\n"
                    "- Suivre les étapes génériques contre le lag, citées ci-dessus.\n"
                    ":white_small_square: Utilisez la commande `!desync` en cas de desync suspectée.")
    except:
        pass

    await message.channel.send(msg)


### Si administrateur
@bot.event
async def author_is_admin(message):

    if to_id in [y.id for y in message.author.roles]:
        return True

    else:
        await message.add_reaction("🚫")
        return False


### Annoncer les résultats
@bot.event
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
    
    classement = (f"{server_logo} **Résultats du {tournoi['name']}** ({len(participants)} entrants) :\n\n"
                  f":trophy: **{resultats[0][1]}**\n"
                  f":second_place: {resultats[1][1]}\n"
                  f":third_place: {resultats[2][1]}\n"
                  f"**4e** : {resultats[3][1]}\n"
                  f"**5e** : {fifth[0]} / {fifth[1]}\n"
                  f"**7e** : {seventh[0]} / {seventh[1]}\n\n"
                  f"{stagelist[tournoi['game']]['icon']} {tournoi['game']}\n"
                  f":link: **Bracket :** {tournoi['url']}\n\n"
                  f"{ending}")
    
    await bot.get_channel(resultats_channel_id).send(classement)


### Ajouter un rôle
@bot.event
async def attribution_role(event):
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    for game in stagelist:

        if event.emoji.name == re.search(r'\:(.*?)\:', stagelist[game]['icon']).group(1):
            role = event.member.guild.get_role(stagelist[game]['role'])

            try:
                await event.member.add_roles(role)
                await event.member.send(f"Le rôle **{role.name}** t'a été attribué avec succès : tu recevras des informations concernant les tournois *{game}* !")
            except:
                pass

        elif event.emoji.name == stagelist[game]['icon_1v1']:
            role = event.member.guild.get_role(stagelist[game]['role_1v1'])

            try:
                await event.member.add_roles(role)
                await event.member.send(f"Le rôle **{role.name}** t'a été attribué avec succès : tu seras contacté si un joueur cherche des combats sur *{game}* !")
            except:
                pass


### Enlever un rôle
@bot.event
async def retirer_role(event):
    with open(stagelist_path, 'r+') as f: stagelist = yaml.full_load(f)

    guild = bot.get_guild(id=guild_id) # due to event.member not being available

    for game in stagelist:

        if event.emoji.name == re.search(r'\:(.*?)\:', stagelist[game]['icon']).group(1):
            role, member = guild.get_role(stagelist[game]['role']), guild.get_member(event.user_id)

            try:
                await member.remove_roles(role)
                await member.send(f"Le rôle **{role.name}** t'a été retiré avec succès : tu ne recevras plus les informations concernant les tournois *{game}*.")
            except:
                pass

        elif event.emoji.name == stagelist[game]['icon_1v1']:
            role, member = guild.get_role(stagelist[game]['role_1v1']), guild.get_member(event.user_id)

            try:
                await member.remove_roles(role)
                await member.send(f"Le rôle **{role.name}** t'a été retiré avec succès : tu ne seras plus contacté si un joueur cherche des combats sur *{game}*.")
            except:
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
    elif message.content == '!desync': await message.channel.send(desync_text)
    elif message.content == '!lag': await send_lag_text(message)
    elif message.content == '!stages': await get_stagelist(message)

    # Commandes admin
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

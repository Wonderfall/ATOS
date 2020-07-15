import yaml

with open('config/config.yml', 'r+') as f: config = yaml.safe_load(f)

### System
debug_mode                          = config["system"]["debug"]

### File paths
tournoi_path                        = config["paths"]["tournoi"]
participants_path                   = config["paths"]["participants"]
stream_path                         = config["paths"]["stream"]
gamelist_path                       = config["paths"]["gamelist"]
auto_mode_path                      = config["paths"]["auto_mode"]
ranking_path                        = config["paths"]["ranking"]
preferences_path                    = config["paths"]["preferences"]

### Locale
language                            = config["system"]["language"]

### Discord prefix
bot_prefix                          = config["discord"]["prefix"]

### System preferences
greet_new_members                   = config["system"]["greet_new_members"]
manage_game_roles                   = config["system"]["manage_game_roles"]
show_unknown_command                = config["system"]["show_unknown_command"]

#### Discord IDs
guild_id                            = int(config["discord"]["guild"])

### Server channels
blabla_channel_id                   = int(config["discord"]["channels"]["blabla"])
annonce_channel_id                  = int(config["discord"]["channels"]["annonce"])
check_in_channel_id                 = int(config["discord"]["channels"]["check_in"])
inscriptions_channel_id             = int(config["discord"]["channels"]["inscriptions"])
inscriptions_vip_channel_id         = int(config["discord"]["channels"]["inscriptionsvip"])
scores_channel_id                   = int(config["discord"]["channels"]["scores"])
stream_channel_id                   = int(config["discord"]["channels"]["stream"])
queue_channel_id                    = int(config["discord"]["channels"]["queue"])
tournoi_channel_id                  = int(config["discord"]["channels"]["tournoi"])
resultats_channel_id                = int(config["discord"]["channels"]["resultats"])
roles_channel_id                    = int(config["discord"]["channels"]["roles"])
to_channel_id                       = int(config["discord"]["channels"]["to"])

### Info, non-interactive channels
deroulement_channel_id              = int(config["discord"]["channels"]["deroulement"])
faq_channel_id                      = int(config["discord"]["channels"]["faq"])

### Server categories
tournoi_cat_id                      = int(config["discord"]["categories"]["tournoi"])

### Role IDs
challenger_id                       = int(config["discord"]["roles"]["challenger"])
to_id                               = int(config["discord"]["roles"]["to"])
streamer_id                         = int(config["discord"]["roles"]["streamer"])

### Custom emojis
server_logo                         = config["discord"]["emojis"]["logo"]

#### Challonge
challonge_user                      = config["challonge"]["user"]

### Tokens
bot_secret                          = config["discord"]["secret"]
challonge_api_key                   = config["challonge"]["api_key"]

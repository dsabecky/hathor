import discord
from discord.ext import commands
from datetime import datetime
import json
import random

import config

####################################################################
# variable: LoadSettings()
# ----
# Our database of errors and fun quotes.
####################################################################
err = {
    'quote': [
        "You must construct additional pylons.",
        "Not enough mana.",
        "Minions have spawned.",
        "You can't sleep right now, there are monsters nearby.",
        "Not enough lumber.",
        "Sorry, but our princess is in another castle!",
        "You cannot fast travel when enemies are nearby.",
        "Mission failure, we'll get them next time."
    ],
    'code': {
        "API_ERROR":            "An API error has occured. Sadge",
        'AUTHOR_NO_VOICE':      "You are not in a voice channel",
        'AUTHOR_PERMS':         "Insufficient permissions",
        'BUMP_SHORT':           "Bump failed: queue too short",
        'BOT_EXIST_VOICE':      "Already in a voice channel",
        'BOT_NO_SOURCE':        "I have no audio source for this server",
        'BOT_NO_VOICE':         "I am not in a voice channel",
        'DISABLED_FEATURE':     "This feature is not currently enabled",
        'NO_HELP':              "There is no help documentation for this command",
        'NO_PERMISSIONS_EXIST': "Those permissions do not exist",
        'NO_QUEUE':             "There is no queue",
        'NO_PLAYING':           "There is nothing playing",
        'PERMISSIONS_EXIST':    "Those permissions already exist",
        'QUEUE_RANGE':          "Request is out of range",
        'SHORT':                "Message is too short",
        "SHUFFLE_NO_PLAYLIST":  "Playlists are not allowed in playnext, don't be greedy.",
        'SONG_LENGTH':          "Requested song is too long!",
        'SYNTAX':               "Syntax error",
        "VOICE_MISMATCH":       "You must be in the same voice channel to do this",
        "VOICE_FULL":           "That voice channel is full",
        'VOL_RANGE':            "Invalid! Volume range is 1-100",
        'YTMD':                 "You're the man now, dog!"
    }
}

####################################################################
# function: LoadSettings()
# ----
# Returns persistent settings.
####################################################################
def LoadSettings():
    try:
        with open('settings.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('settings.json', 'w') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default

####################################################################
# function: SaveSettings()
# ----
# Writes persistent settings to settings.json
####################################################################
def SaveSettings():
    with open('settings.json', 'w') as file:
        json.dump(settings, file, indent=4)


# load settings
settings = LoadSettings()

####################################################################
# function: CheckPermissions(bot, guild_id, user_id, user_roles)
# ----
# bot:        bot variable
# guild_id:   guildID of server
# user_id:    userID of user being checked
# user_roles: roles of user being checked
# ----
# Checks if a user has elevated permissions in a server.
####################################################################
async def CheckPermissions(bot, guild_id, user_id, user_roles):
    guild = await bot.fetch_guild(guild_id) # why cant i get this from ctx.guild???
    
    guild_id, guild_str = guild.id, str(guild.id)
    owner = await bot.fetch_user(guild.owner_id)

    if user_id == config.BOT_ADMIN:
        return True
    
    elif user_id == owner.id:
        return True
    
    elif user_id in settings[guild_str]['perms']['user_id']:
        return True
    
    elif any(role.id in settings[guild_str]['perms']['role_id'] for role in user_roles):
        return True
    
    else:
        return False
    
####################################################################
# function: FancyErrors(error)
# ----
# error: valid error code (see code).
# ----
# Returns prewritten errors.
####################################################################
async def FancyErrors(error, channel):
    if error in err["code"]:
        await channel.send(f'{random.choice(err["quote"])} ({err["code"][error]})')
    else:
        await channel.send(f'{random.choice(err["quote"])} (An unfamiliar error has occured. Sadge)')
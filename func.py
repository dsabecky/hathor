####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# system level stuff
import json

# date, time, numbers
from datetime import datetime
import random

# hathor internals
import config

###############################################################
# Quotable References
###############################################################

error_flavor = [
        "You must construct additional pylons.",
        "Not enough mana.",
        "Minions have spawned.",
        "You can't sleep right now, there are monsters nearby.",
        "Not enough lumber.",
        "Sorry, but our princess is in another castle!",
        "You cannot fast travel when enemies are nearby.",
        "Mission failure, we'll get them next time.",
        "What do the numbers mean, Mason?",
        "What a horrible night to have a curse..."
]

###############################################################
# Errors: Cases & Linker References
###############################################################

class Error(commands.CommandError):
    pass
class err_author_no_voice(Error):
    code = "You are not in a voice channel"
class err_author_perms(Error):
    code = "Insufficient permissions"
class err_bot_exist_voice(Error):
    code = "Already in a voice channel"
class err_bot_no_voice(Error):
    code = "I am not in a voice channel"
class err_bump_short(Error):
    code = "Bump failed: queue too short"  
class err_duplicate_song(Error):
    code = "This song already exists in the destination"
class err_message_short(Error):
    code = "Message is too short"
class err_no_image(Error):
    code = "No images attached"
class err_no_queue(Error):
    code = "There is no queue"
class err_no_playing(Error):
    code = "There is nothing playing"
class err_no_radio(Error):
    code = "There is no active radio"
class err_no_song_found(Error):
    code = "I couldn't find that song."
class err_queue_range(Error):
    code = "Request is out of range"
class err_permissions_exist(Error):
    code = "Permissions already exist"
class err_radio_exist(Error):
    code = "Radio station already exists"
class err_shuffle_no_playlist(Error):
    code = "Playlists are not allowed in playnext, don't be greedy."
class err_song_length(Error):
    code = "Requested song is too long!"
class err_syntax(Error):
    code = "Syntax error"
class err_voice_full(Error):
    code = "That voice channel is full"
class err_voice_mismatch(Error):
    code = "You must be in the same voice channel to do this"
class err_vol_range(Error):
    code = "Invalid! Volume range is 1-100"
class err_wrong_fuse(Error):
    code = "That station is not fused"

def requires_author_perms():
    async def predicate(ctx: commands.Context):

        allowed = await CheckPermissions(ctx.bot, ctx.guild.id, ctx.author.id, ctx.author.roles)

        if not allowed:
            raise err_author_perms()
        return True
    return commands.check(predicate)

def requires_author_voice():
    def predicate(ctx: commands.Context):
        if not ctx.author.voice:
            raise err_author_no_voice()
        return True
    return commands.check(predicate)

def requires_bot_playing():
    async def predicate(ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            raise err_no_playing()
        return True
    return commands.check(predicate)

def requires_bot_voice():
    def predicate(ctx: commands.Context):
        if not ctx.guild.voice_client:
            raise err_bot_no_voice()
        return True
    return commands.check(predicate)

def requires_message_length(min_len: int):
    def predicate(ctx: commands.Context):
        args = ctx.message.content.split(" ", 1)
        val = args[1] if len(args) > 1 else ""
        if len(val.strip()) < min_len:
            raise err_message_short()
        return True
    return commands.check(predicate)

def requires_owner_perms():
    async def predicate(ctx: commands.Context):
        if ctx.author.id == config.BOT_ADMIN:
            return True
        else:
            raise err_author_perms()
    return commands.check(predicate)

def requires_queue():
    async def predicate(ctx: commands.Context):
        cog = ctx.bot.get_cog("Music")
        if cog is None:
            raise err_no_queue()

        allstates = cog.settings[ctx.guild.id]

        if not allstates.queue:
            raise err_no_queue()
        return True
    return commands.check(predicate)


###############################################################
# Internal Functions
###############################################################
async def CheckPermissions(bot, guild_id, user_id, user_roles):
    guild = await bot.fetch_guild(guild_id) # why cant i get this from ctx.guild???
    
    guild_id, guild_str = guild.id, str(guild.id)
    owner = await bot.fetch_user(guild.owner_id)

    if user_id == config.BOT_ADMIN:
        return True
    
    elif user_id == owner.id:
        return True
    
    elif user_id in config.settings[guild_str]['perms']['user_id']:
        return True
    
    elif any(role.id in config.settings[guild_str]['perms']['role_id'] for role in user_roles):
        return True
    
    else:
        return False
    
####################################################################
# function: FancyErrors(error)
# ----
# Returns prewritten errors.
####################################################################
async def FancyErrors(error: str, channel):
    flavor = random.choice(error_flavor)
    await channel.send(f'{flavor} ({error})')
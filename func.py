####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# system level stuff
import json
from typing import TypedDict, Any

# date, time, numbers
import random

# hathor internals
import config


####################################################################
# Classes
####################################################################

class CurrentlyPlaying(TypedDict):
    """
    Dictionary structure for CurrentlyPlaying.
    """

    title: str
    song_artist: str
    song_title: str

    file_path: str
    thumbnail: str
    duration: int

class Settings:
    """
    Volatile settings, called as 'allstates' in functions.
    """

    def __init__(self):
        self.perms: dict[str, list[int]] = { 'user_id': [], 'role_id': [], 'channel_id': [] }

        self.currently_playing: CurrentlyPlaying | None = None
        self.queue: list[str] = []

        self.volume: int = 100
        self.repeat: bool = False
        self.shuffle: bool = False

        self.radio_station: str | None = None
        self.radio_fusions: list[str] = []
        self.radio_fusions_playlist: list[str] = []
        self.radio_intro: bool = True

        self.voice_idle: int = 300
        self.start_time: float | None = None
        self.pause_time: float | None = None
        self.last_active: float | None = None
        self.intro_playing: bool = False

    def load_settings_from_json(self, data: dict[str, Any]):
        if perms := data.get("perms"):
            self.perms.update(perms)
        if vol := data.get("volume"):
            self.volume = vol
        if voice_idle := data.get("voice_idle"):
            self.voice_idle = voice_idle
        if radio_intro := data.get("radio_intro"):
            self.radio_intro = radio_intro

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
# Error Classes
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
class err_voice_join(Error):
    code = "I can't join that voice channel"
class err_voice_mismatch(Error):
    code = "You must be in the same voice channel to do this"
class err_vol_range(Error):
    code = "Invalid! Volume range is 1-100"
class err_wrong_fuse(Error):
    code = "That station is not fused"

###############################################################
# Permission Checks (decorators)
###############################################################

def requires_author_perms():
    async def predicate(message: discord.Message):

        allowed = await CheckPermissions(message.bot, message.guild.id, message.author.id, message.author.roles)

        if not allowed:
            raise err_author_perms()
        return True
    return commands.check(predicate)

def requires_author_voice():
    def predicate(message: discord.Message):
        if not message.author.voice:
            raise err_author_no_voice()
        return True
    return commands.check(predicate)

def requires_bot_playing():
    async def predicate(message: discord.Message):
        vc = message.guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            raise err_no_playing()
        return True
    return commands.check(predicate)

def requires_bot_voice():
    def predicate(message: discord.Message):
        if not message.guild.voice_client:
            raise err_bot_no_voice()
        return True
    return commands.check(predicate)

def requires_message_length(min_len: int):
    def predicate(message: discord.Message):
        args = message.content.split(" ", 1)
        val = args[1] if len(args) > 1 else ""
        if len(val.strip()) < min_len:
            raise err_message_short()
        return True
    return commands.check(predicate)

def requires_owner_perms():
    async def predicate(message: discord.Message):
        if message.author.id == config.BOT_ADMIN:
            return True
        else:
            raise err_author_perms()
    return commands.check(predicate)

def requires_queue():
    async def predicate(message: discord.Message):
        allstates = message.bot.settings[message.guild.id]

        if not allstates.queue:
            raise err_no_queue()
        
        return True
    return commands.check(predicate)

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
    
###############################################################
# Functions
###############################################################
 
async def FancyErrors(error: str, channel):
    flavor = random.choice(error_flavor)

    embed = discord.Embed(title=flavor, description=error, color=discord.Color.red())
    await channel.send(embed=embed)
####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# system level stuff
import json                       # json db handling
from typing import Any,TypedDict  # type hints
from pathlib import Path          # pathlib

# data analysis
import random   # error flavor text randomizer

# hathor internals
import config

####################################################################
# Global Variables
####################################################################

SETTINGS_FILE = Path(__file__).parent / "settings.json"


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

class Error(commands.CommandError):
    """
    Custom error class.
    """

    def __init__(self, code: str | Exception = None):
        if isinstance(code, str) and code:  # known error code
            msg = code
        else:   # unknown error code, dump the exception
            msg = str(code)

        super().__init__(msg)
        self.code = msg

class Settings:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id

        self.perms = {"user_id": [], "role_id": [], "channel_id": []}

        self.currently_playing = None
        self.queue = []

        self.volume = 20
        self.repeat = False
        self.shuffle = False

        self.radio_intro = True
        self.radio_station = None
        self.radio_fusions = []
        self.radio_fusions_playlist = []

        self.voice_idle = 300
        self.start_time = None
        self.pause_time = None
        self.last_active = None
        self.intro_playing = False

        # load saved overrides
        self._load_settings()

    def _load_settings(self) -> None:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return

        saved = data.get(str(self.guild_id), {})
        for key, val in saved.items():
            # only set attributes that already exist
            if hasattr(self, key):
                setattr(self, key, val)

    def _save_settings(self) -> None:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        data[str(self.guild_id)] = {
            key: getattr(self, key)
            for key in self.__dict__
            if key != "guild_id"
        }
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=4),
            encoding="utf-8"
        )

class SongDB:
    def __init__(self, path: str = "song_db.json"):
        self.path = Path(path)
        self._db: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self):
        try:
            with self.path.open("r", encoding="utf-8") as f:
                self._db = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._db = {}
            self.save()  # create the file if missing or invalid

    def save(self):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._db, f, ensure_ascii=False, indent=4)

    def __getitem__(self, song_id: str) -> dict[str, Any]:
        return self._db[song_id]

    def __setitem__(self, song_id: str, value: dict[str, Any]):
        self._db[song_id] = value

    def __contains__(self, song_id: str) -> bool:
        return song_id in self._db

    def get(self, song_id: str, default=None):
        return self._db.get(song_id, default)

    def all(self):
        return self._db.values()


###############################################################
# Functions
###############################################################

async def CheckPermissions(
    bot: commands.Bot,
    guild_id: int,
    user_id: int,
    user_roles: list[discord.Role]
) -> bool:
    """
    Check if a user has permissions to use elevated commands.
    """

    guild = await bot.fetch_guild(guild_id) # required to get the owner_id
    
    guild_str = str(guild.id)
    owner = await bot.fetch_user(guild.owner_id)

    if user_id == config.BOT_ADMIN:
        return True
    
    elif user_id == owner.id:
        return True
    
    elif user_id in bot.settings[guild_str]['perms']['user_id']:
        return True
    
    elif any(role.id in bot.settings[guild_str]['perms']['role_id'] for role in user_roles):
        return True
    
    else:
        return False
 
async def FancyErrors(
    error: str,
    channel: discord.TextChannel
) -> None:
    """
    Send a formatted error message to a channel.
    """

    embed = discord.Embed(title=random.choice(ERROR_FLAVOR), description=error, color=discord.Color.red())
    await channel.send(embed=embed)


###############################################################
# Quotable References
###############################################################

ERROR_FLAVOR = [
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

ERROR_CODES = {
    "author_no_voice": "You are not in a voice channel",
    "author_perms": "Insufficient permissions",
    "bot_exist_voice": "Already in a voice channel",
    "bot_no_voice": "I am not in a voice channel",
    "bump_short": "Queue too short",
    "duplicate_song": "This song already exists in the destination",
    "message_short": "Message is too short",
    "no_image": "No images attached",
    "no_playing": "There is nothing playing",
    "no_queue": "There is no queue",
    "no_radio": "There is no active radio",
    "no_song_found": "I couldn't find that song.",
    "permissions_exist": "Permissions already exist",
    "queue_range": "Request is out of range",
    "radio_exist": "Radio station already exists",
    "shuffle_no_playlist": "Playlists are not allowed in playnext, don't be greedy.",
    "song_length": "Requested song is too long!",
    "syntax": "Syntax error",
    "voice_join": "I can't join that voice channel",
    "voice_mismatch": "You must be in the same voice channel to do this",
    "vol_range": "Invalid! Volume range is 1-100",
    "wrong_fuse": "That station is not fused"
}


###############################################################
# Permission Checks (decorators)
###############################################################

def requires_author_perms():
    async def predicate(message: discord.Message):

        allowed = await CheckPermissions(message.bot, message.guild.id, message.author.id, message.author.roles)

        if not allowed:
            raise Error(ERROR_CODES["author_perms"])
        return True
    return commands.check(predicate)

def requires_author_voice():
    def predicate(message: discord.Message):
        if not message.author.voice:
            raise Error(ERROR_CODES["author_no_voice"])
        return True
    return commands.check(predicate)

def requires_bot_playing():
    async def predicate(message: discord.Message):
        vc = message.guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            raise Error(ERROR_CODES["no_playing"])
        return True
    return commands.check(predicate)

def requires_bot_voice():
    def predicate(message: discord.Message):
        if not message.guild.voice_client:
            raise Error(ERROR_CODES["bot_no_voice"])
        return True
    return commands.check(predicate)

def requires_owner_perms():
    async def predicate(message: discord.Message):
        if message.author.id == config.BOT_ADMIN:
            return True
        else:
            raise Error(ERROR_CODES["author_perms"])
    return commands.check(predicate)

def requires_queue():
    async def predicate(message: discord.Message):
        allstates = message.bot.settings[message.guild.id]

        if not allstates.queue:
            raise Error(ERROR_CODES["no_queue"])
        
        return True
    return commands.check(predicate)
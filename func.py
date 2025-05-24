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
    Custom error class (will be logged to the console only).
    """

    def __init__(self, code: str | Exception = None):
        super().__init__(code)
        self.code = code

class FancyError(commands.CommandError):
    """
    Custom error class (will be formatted as an embed and sent to the channel).
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

        map = [
            'currently_playing', 'guild_id', 'intro_playing', 'last_active',
            'pause_time', 'queue', 'radio_fusions', 'radio_fusions_playlist',
            'radio_station', 'repeat', 'start_time'
        ]

        data[str(self.guild_id)] = {
            key: getattr(self, key)
            for key in self.__dict__
            if key not in map
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

async def _check_permissions(
    bot: commands.Bot,
    guild_id: int,
    user_id: int,
    user_roles: list[discord.Role]
) -> bool:
    """
    Check if a user has permissions to use elevated commands.
    """

    allstates = bot.settings[guild_id]
    guild = await bot.fetch_guild(guild_id) # required to get the owner_id
    owner = await bot.fetch_user(guild.owner_id)

    if user_id == config.BOT_ADMIN:
        return True
    
    elif user_id == owner.id:
        return True
    
    elif user_id in allstates.perms['user_id']:
        return True
    
    elif any(role.id in allstates.perms['role_id'] for role in user_roles):
        return True
    
    else:
        return False
    
def _build_embed(
    title: str,
    description: str,
    color: str = "p",
    fields: list[tuple[str, str, bool]] = None
) -> discord.Embed:
    """
    Builds an embed with a title, description, and color.
    """

    map = {
        'p': discord.Color.dark_purple(),
        'r': discord.Color.red(),
        'g': discord.Color.green(),
        'err': random.choice(ERROR_FLAVOR),
        'img': f'Image generated using the **{config.GPTIMAGE_MODEL}** model.',
        'imgtxt': f'Image and text generated using the **{config.CHATGPT_MODEL}** and **{config.GPTIMAGE_MODEL}** models.',
        'txt': f'Text generated using the **{config.CHATGPT_MODEL}** model.'
    }

    title = map[title.lower()] if title.lower() in map.keys() else title
    description = map[description.lower()] if description.lower() in map.keys() else description
    embed = discord.Embed(title=title, description=description, color=map[color.lower()])

    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed

    
async def _get_random_radio_intro(bot: commands.Bot, guild_name: str, title: str, artist: str) -> str:
    """
    Returns a random radio intro for a given guild.
    """

    repls = { "%SERVER%": guild_name, "%BOT%": bot.user.display_name or bot.user.name, "%TITLE%": title, "%ARTIST%": artist }
    intro = random.choice(RADIO_INTROS)
    for placeholder, value in repls.items():
        intro = intro.replace(placeholder, value)
    return intro


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

RADIO_INTROS = [
    f"Ladies and gentlemen, hold onto your seats because we're about to unveil the magic of %TITLE% by %ARTIST%. Only here at %SERVER% radio.",
    f"Turning it up to 11! brace yourselves for %ARTIST%'s masterpiece %TITLE%. Here on %SERVER% radio.",
    f"Rock on, warriors! We're cranking up the intensity with %TITLE% by %ARTIST% on %SERVER% radio.",
    f"Welcome to the virtual airwaves! Get ready for a wild ride with a hot track by %ARTIST% on %SERVER% radio.",
    f"Buckle up, folks! We're about to take you on a musical journey through the neon-lit streets of %SERVER% radio.",
    f"Hello, virtual world! It's your DJ, %BOT%, in the house, spinning %TITLE% by %ARTIST%. Only here on %SERVER% radio.",
    f"Greetings from the digital realm! Tune in, turn up, and let the beats of %ARTIST% with %TITLE% take over your senses, here on %SERVER% radio.",
    f"Time to crank up the volume and immerse yourself in the eclectic beats of %SERVER% radio. Let the madness begin with %TITLE% by %ARTIST%!"
]


###############################################################
# Permission Checks (decorators)
###############################################################

def requires_author_perms():
    async def predicate(message: discord.Message):

        allowed = await _check_permissions(message.bot, message.guild.id, message.author.id, message.author.roles)

        if not allowed:
            raise FancyError(ERROR_CODES["author_perms"])
        return True
    return commands.check(predicate)

def requires_author_voice():
    def predicate(message: discord.Message):
        if not message.author.voice:
            raise FancyError(ERROR_CODES["author_no_voice"])
        return True
    return commands.check(predicate)

def requires_bot_playing():
    async def predicate(message: discord.Message):
        vc = message.guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            raise FancyError(ERROR_CODES["no_playing"])
        return True
    return commands.check(predicate)

def requires_bot_voice():
    def predicate(message: discord.Message):
        if not message.guild.voice_client:
            raise FancyError(ERROR_CODES["bot_no_voice"])
        return True
    return commands.check(predicate)

def requires_owner_perms():
    async def predicate(message: discord.Message):
        if message.author.id == config.BOT_ADMIN:
            return True
        else:
            raise FancyError(ERROR_CODES["author_perms"])
    return commands.check(predicate)

def requires_queue():
    async def predicate(message: discord.Message):
        allstates = message.bot.settings[message.guild.id]

        if not allstates.queue:
            raise FancyError(ERROR_CODES["no_queue"])
        
        return True
    return commands.check(predicate)
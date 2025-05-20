####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands
from discord.ext.commands import Context

# system level stuff
import asyncio             # prevents thread locking
from pathlib import Path   # cog discovery

# data analysis
import inspect  # inspect config variables
import re       # various regex filters
import time     # last active time updater

# hathor internals
import config
from func import Error, ERROR_CODES, FancyErrors, Settings
from logs import log_sys, log_msg, log_voice


####################################################################
# Configuration Validation
####################################################################

def _validate_config() -> None:
    """
    Ensure all config variables are defined.
    """
    missing = []
    pattern = re.compile(r"^[A-Z][A-Z0-9_]+$")
    for name, val in inspect.getmembers(config):
        if pattern.match(name):
            if not val and val != 0:
                missing.append(name)
    if missing:
        raise RuntimeError(f"Missing config values: {', '.join(missing)}")
    
log_sys.info("Validating configurations from config.py...")
_validate_config()


####################################################################
# Bot initialization
####################################################################

class Hathor(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True

        super().__init__(
            command_prefix=config.BOT_PREFIX,
            intents=intents,
            case_insensitive=True
        )

        self.cog_list = [   # dynamic cog discovery
            f"cogs.{p.stem}"
            for p in (Path(__file__).parent / "cogs").glob("*.py")
            if p.stem != "__init__" # ignore __init__.py
        ]

        self.settings: dict[int, Settings] = {}

        self._patch_context()   # load patcher for embed logging

    async def start_bot(self):
        await self.start(config.DISCORD_BOT_TOKEN)

    def _patch_context(self):    # patch Context.send and Context.reply to log embeds
        source_send = Context.send
        source_reply = Context.reply

        async def send(self, *a, **kw):
            if kw.get("embed"):
                log_msg.info("EMBED:\n%s", kw["embed"].to_dict())
            return await source_send(self, *a, **kw)

        async def reply(self, *a, **kw):
            if kw.get("embed"):
                log_msg.info("EMBED:\n%s", kw["embed"].to_dict())
            return await source_reply(self, *a, **kw)

        Context.send = send
        Context.reply = reply

    async def setup_hook(self): # load extensions
        for ext in self.cog_list:
            await self.load_extension(ext)


    ####################################################################
    # 'on_' listeners
    ####################################################################

    async def on_ready(self) -> None:
        """
        Runs when the bot is ready.
        """

        if config.MAINTENANCE:  # am i in maintenance mode? ### TODO: customize maintenance message
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.competing, name="maintenance!!!1"), status=discord.Status.do_not_disturb)

        ###
        ### TODO: implement some kind of songDB trim
        ###

        log_sys.info(f"connected as \033[38;2;152;255;152m{self.user}\033[0m")   # log connection to console

        for guild in self.guilds:
            self.settings.setdefault(guild.id, Settings(guild.id))

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound): # ignore command not found errors
            return
        
        if isinstance(error, Error):   # handle known errors
            log_sys.warning(f"Caught known error: {error.code}")
            return await FancyErrors(error.code, ctx.channel)
        
        else:   # dump unknown errors
            raise error
        
    async def on_guild_join(self, guild: discord.Guild):
        allstates = self.settings.setdefault(guild.id, Settings(guild.id))
        allstates._save_settings()
        

    async def on_message(self, message: discord.Message) -> None:
        """
        Runs when a message is sent in a server or DM.
        """

        allstates = self.settings[message.guild.id]

        if message.guild:   # log server messages to console
            log_msg.info(f"\033[38;2;152;255;152m{message.author}@{message.guild.name}#{message.channel.name}\033[0m: {message.content}")
        else:   # log DMs to console
            log_msg.info(f"\033[38;2;152;255;152m{message.author}\033[0m: {message.content}")
        
        if message.author == self.user: # ignore messages from self
            return
        
        if message.author.bot: # ignore messages from bots
            return

        if not message.guild:    # ignore DMs
            return
        
        if len(allstates.perms['channel_id']) > 0 and message.channel.id not in allstates.perms['channel_id']:
            return

        if message.content.lower() == "foxtest":    # test message
            await message.reply(f'The quick brown fox jumps over the lazy dog 1234567890 ({self.latency * 1000:.2f}ms)')

        await self.process_commands(message) # required to process @bot.command

    async def on_voice_state_update(self, author: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel is None and after.channel is not None: # joined
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: joined {after.channel.guild.name}/{after.channel}")
        elif before.channel is not None and after.channel is None: # left
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: left {before.channel.guild.name}/{before.channel}")
        elif before.channel != after.channel: # changed
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: moved in {before.channel.guild.name}: {before.channel} -> {after.channel}")


    ####################################################################
    # Functions
    ####################################################################

    async def _join_voice(self, ctx: commands.Context):
        allstates = self.settings[ctx.guild.id]

        try:
            if ctx.voice_client:
                await ctx.voice_client.move_to(ctx.author.voice.channel)
            else:
                await ctx.author.voice.channel.connect()
            allstates.last_active = time.time() # update the last active time
        except Exception:
            raise Error(ERROR_CODES["voice_join"])


####################################################################
# Launch
####################################################################

if __name__ == "__main__":
    bot = Hathor()
    try:
        asyncio.run(bot.start_bot())
    except KeyboardInterrupt:
        log_sys.info("Shutting down...")
    except Exception as e:
        log_sys.error(f"Error: {e}")
        raise e

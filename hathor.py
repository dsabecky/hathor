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
import logging

# data analysis
import inspect  # inspect config variables
import re       # various regex filters
import time     # last active time updater
import random   # random error flavor
from rich.markup import escape

# hathor internals
import data.config as config
from func import Error, ERROR_CODES, FancyError # error handling
from func import Settings # class loading
from func import build_embed # functions
from logs import log_sys, log_msg # logging


####################################################################
# Mute regular INFO logging
####################################################################

log_names = [ "discord.player", "discord.voice_client", "pylast", "requests", "urllib3" ]

for logger_name in log_names:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.WARNING)
    logger.propagate = True


####################################################################
# Configuration Validation
####################################################################

def validate_config() -> None:
    """
    Ensure all config variables are defined.
    """

    missing = []
    pattern = re.compile(r"^[A-Z][A-Z0-9_]+$")
    for name, val in inspect.getmembers(config):
        if pattern.match(name) and not name.startswith("LASTFM_"):
            if not val and val != 0:
                missing.append(name)
    if missing:
        raise Error(f"Missing config values: {', '.join(missing)}")


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

    def _patch_context(self):    # patch Context.send to log embeds
        source_send = Context.send

        async def send(self, *a, **kw):
            if kw.get("embed"):
                log_msg.info(f"[dark_violet]{self.bot.user}[/]@{self.guild.name}#{self.channel.name}:\n{kw['embed'].to_dict()}")
            return await source_send(self, *a, **kw)

        Context.send = send

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

        ###
        ### TODO: implement some kind of songDB trim
        ###

        log_sys.info(f"connected as [dark_violet]{self.user}[/].")   # log connection to console

        for guild in self.guilds:
            self.settings.setdefault(guild.id, Settings(guild.id))

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound): # ignore command not found errors
            return

        elif isinstance(error, commands.BadArgument): # incorrect syntax
            error_text = ERROR_CODES['syntax']

        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, IndexError): # out of range errors
            error_text = ERROR_CODES['range']

        elif isinstance(error, commands.MissingRequiredArgument): # missing arguments
            error_text = ERROR_CODES['syntax']

        elif isinstance(error, FancyError): # send parsed errors to channel
            error_text = str(error)

        elif isinstance(error, Error): # log errors to console
            log_sys.error(f"[red]{escape(error.code)}[/]")
            raise error

        else: # dump unknown errors
            log_sys.error(f"Unhandled error: {error}")
            raise error

        await ctx.reply(embed=build_embed('err', error_text, 'r'))
        
    async def on_guild_join(self, guild: discord.Guild):
        allstates = self.settings.setdefault(guild.id, Settings(guild.id))
        allstates.save()
        

    async def on_message(self, message: discord.Message) -> None:
        """
        Runs when a message is sent in a server or DM.
        """

        if message.author == self.user or message.author.bot or not message.guild or not message.content: # ignore [self, bot, dm, empty]
            return

        allstates = self.settings[message.guild.id]
        log_msg.info(f"[dark_violet]{message.author}[/]@{message.guild.name}#{message.channel.name}: {escape(message.content)}")
        
        if len(allstates.perms['channel_id']) > 0 and message.channel.id not in allstates.perms['channel_id']:
            return

        if message.content.lower() == "foxtest":    # test message
            await message.reply(f'The quick brown fox jumps over the lazy dog 1234567890 ({self.latency * 1000:.2f}ms)')

        await self.process_commands(message) # required to process @bot.command

    async def on_voice_state_update(self, author: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel is None and after.channel is not None: # joined
            log_sys.info(f"[dark_violet]{author}[/]@{after.channel.guild.name}: [firebrick]{after.channel}[/] 👋")
        elif before.channel is not None and after.channel is None: # left
            log_sys.info(f"[dark_violet]{author}[/]@{before.channel.guild.name}: [firebrick]{before.channel}[/] ✌️")
        elif before.channel != after.channel: # changed
            log_sys.info(f"[dark_violet]{author}[/]@{before.channel.guild.name}: [firebrick]{before.channel}[/] -> [firebrick]{after.channel}[/]")


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
            raise FancyError(ERROR_CODES["voice_join"])

async def main():
    bot = Hathor()
    try:
        await bot.start_bot()
    except asyncio.CancelledError:
        log_sys.info("Shutting down…")
    except Exception as e:
        raise e
    finally:
        await bot.close()

####################################################################
# Launch
####################################################################

if __name__ == "__main__":
    log_sys.info("Validating configurations from [dark_orange]config.py[/]…")
    validate_config()

    log_sys.info("Validation [green]complete[/]. Starting up…")
    asyncio.run(main())
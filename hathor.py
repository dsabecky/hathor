####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context

# system level stuff
import asyncio             # prevents thread locking
from pathlib import Path   # cog discovery

# data analysis
from collections import defaultdict   # type hints
import time

# hathor internals
import config                                 # bot config
import func                                   # bot specific functions (@decorators, err_ classes, etc)
from func import FancyErrors, Settings        # error handling
from logs import log_sys, log_msg, log_voice  # logging


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

        self.cog_list = [
            f"cogs.{p.stem}"
            for p in (Path(__file__).parent / "cogs").glob("*.py")
            if p.stem != "__init__"
        ]

        self.settings: dict[int, Settings] = defaultdict(Settings)

        self._patch_context()   # load patcher for embed logging

    async def start_bot(self):
        await self.start(config.BOT_TOKEN)

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

    async def on_ready(self):
        if config.MAINTENANCE:  # am i in maintenance mode?
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.competing, name="maintenance!!!1"), status=discord.Status.do_not_disturb)

        ### TODO: implement some kind of songDB trim

        log_sys.info(f"connected as \033[38;2;152;255;152m{self.user}\033[0m")   # log connection to console

        for guild in self.guilds:
            allstates = self.settings[guild.id] # load defaults
            allstates.load_settings_from_json(config.settings.setdefault(str(guild.id), {}))    # load saved settings if present
            
        config.SaveSettings()   # save settings

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound): # ignore command not found errors
            return
        
        if isinstance(error, func.Error):   # handle known errors
            return await FancyErrors(error.code, ctx.channel)
        
        else:   # dump unknown errors
            raise error
        
    async def on_guild_join(self, guild: discord.Guild):
        allstates = self.settings[guild.id] # load defaults
        allstates.load_settings_from_json(config.settings.setdefault(str(guild.id), {}))    # load saved settings if present (maybe we rejoined a server)
        
        config.SaveSettings()   # save settings

    async def on_voice_state_update(self, author: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel is None and after.channel is not None: # joined
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: joined {after.channel.guild.name}/{after.channel}")
        elif before.channel is not None and after.channel is None: # left
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: left {before.channel.guild.name}/{before.channel}")
        elif before.channel != after.channel: # changed
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: moved in {before.channel.guild.name}: {before.channel} -> {after.channel}")

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
        
        if not message.guild:    # ignore DMs
            return
        
        if len(allstates.perms['channel_id']) > 0 and message.channel.id not in allstates.perms['channel_id']:
            print(f"ignoring {message.channel.name} ({message.channel.id})")
            return

        if message.content.lower() == "foxtest":    # test message
            await message.reply(f'The quick brown fox jumps over the lazy dog 1234567890 ({self.latency * 1000:.2f}ms)')

        await self.process_commands(message) # required to process @bot.command


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
            raise func.err_voice_join()


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

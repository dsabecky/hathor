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
from typing import Literal # legacy type hints

# hathor internals
import config                                 # bot config
import func                                   # bot specific functions (@decorators, err_ classes, etc)
from func import FancyErrors                  # error handling
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

    async def on_ready(self):
        if config.MAINTENANCE:  # am i in maintenance mode?
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.competing, name="maintenance!!!1"), status=discord.Status.do_not_disturb)

        ### TODO: implement some kind of songDB trim

        log_sys.info(f"connected as \033[38;2;152;255;152m{self.user}\033[0m")   # log connection to console

        for guild in self.guilds:    # build default settings into config if neccesary
            guild_str = str(guild.id)

            if guild_str not in config.settings:
                config.settings[guild_str] = {}
            if 'perms' not in config.settings[guild_str]:
                config.settings[guild_str]['perms'] = {}
                config.settings[guild_str]['perms'] = { 'user_id': [], 'role_id': [], 'channel_id': [] }
            if 'volume' not in config.settings[guild_str]:
                config.settings[guild_str]['volume'] = 20
            if 'voice_idle' not in config.settings[guild_str]:
                config.settings[guild_str]['voice_idle'] = 300
            if 'radio_intro' not in config.settings[guild_str]:
                config.settings[guild_str]['radio_intro'] = True
            
        config.SaveSettings()   # save settings

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            return
        
        if isinstance(error, func.Error):
            return await FancyErrors(error.code, ctx.channel)
        
        else:
            raise error
        
    async def on_guild_join(self, guild: discord.Guild):
        for guild in self.guilds:    # build default settings into config if neccesary
            guild_str = str(guild.id)

            if guild_str not in config.settings:
                config.settings[guild_str] = {}
            if 'perms' not in config.settings[guild_str]:
                config.settings[guild_str]['perms'] = {}
                config.settings[guild_str]['perms'] = { 'user_id': [], 'role_id': [], 'channel_id': [] }
            if 'volume' not in config.settings[guild_str]:
                config.settings[guild_str]['volume'] = 20
            if 'voice_idle' not in config.settings[guild_str]:
                config.settings[guild_str]['voice_idle'] = 300
            if 'radio_intro' not in config.settings[guild_str]:
                config.settings[guild_str]['radio_intro'] = True
                
        config.SaveSettings()

    async def on_voice_state_update(self, author: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel is None and after.channel is not None: # joined
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: joined {after.channel.guild.name}/{after.channel}")
        elif before.channel is not None and after.channel is None: # left
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: left {before.channel.guild.name}/{before.channel}")
        elif before.channel != after.channel: # changed
            log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: moved in {before.channel.guild.name}: {before.channel} -> {after.channel}")

    async def on_message(self, ctx: commands.Context) -> None:
        """
        Runs when a message is sent in a server or DM.
        """

        if ctx.guild:   # log server messages to console
            log_msg.info(f"\033[38;2;152;255;152m{ctx.author}@{ctx.guild.name}#{ctx.channel.name}\033[0m: {ctx.content}")
        else:   # log DMs to console
            log_msg.info(f"\033[38;2;152;255;152m{ctx.author}\033[0m: {ctx.content}")
        
        if ctx.author == bot.user or not ctx.guild or (len(config.settings[str(ctx.guild.id)]['perms']['channel_id']) > 0 and ctx.channel.id not in config.settings[str(ctx.guild.id)]['perms']['channel_id']):
            return

        if ctx.content.lower() == "foxtest":    # test message
            await ctx.reply(f'The quick brown fox jumps over the lazy dog 1234567890 ({bot.latency * 1000:.2f}ms)')

        await self.process_commands(ctx) # required to process @bot.command


    ####################################################################
    # Command triggers
    ####################################################################

    @commands.command(name="botleave")
    @func.requires_owner_perms()
    async def trigger_botleave(
        self,
        ctx: commands.Context,
        guild_id: int | None = None
    ) -> None:
        """
        BOT OWNER. Leave the provided discord server.
        
        Syntax:
            !botleave <guildID>
        """

        if not guild_id:
            await FancyErrors("SYNTAX", ctx.channel)
            return

        guild = bot.get_guild(guild_id)

        # let them know
        await ctx.send(f"👋 Leaving **{guild.name}** (ID: {guild.id})…")

        # bye felicia
        await guild.leave()

    @commands.command(name="botservers")
    @func.requires_owner_perms()
    async def trigger_botservers(
        self,
        ctx: commands.Context
    ) -> None:
        """
        BOT OWNER. Lists all guilds the bot is currently in.

        Syntax:
            !botservers
        """

        # build a list of lines "Name (ID: ...)"
        lines = [f"{g.name} (ID: {g.id})" for g in bot.guilds]

        # assemble embed
        embed = discord.Embed(
            title="🤖 Bot is in the following guilds:",
            description="\n".join(lines) or "None",
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Total guilds: {len(lines)}")

        # send to channel
        await ctx.send(embed=embed)

    @commands.command(name="botsync")
    @func.requires_owner_perms()
    async def trigger_botsync(
        self,
        ctx: Context,
        guilds: Greedy[discord.Object],
        spec: Literal["guild", "globalguild", "clearguild"] | None = None
    ) -> None:
        """
        BOT OWNER. Syncronizes /slash commands.

        Syntax:
            !botsync [ guild | globalguild | clearguild ]
        """

        if not guilds:
            if spec == "guild":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "globalguild":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "clearguild":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}")
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @commands.command(name='permissions', aliases=['perms', 'roles'])
    @func.requires_author_perms()
    async def trigger_permissions(
        self,
        ctx: commands.Context,
        action: Literal["add", "remove"] | None = None,
        group: Literal["channel", "role", "user"] | None = None,
        target: int | None = None
    ) -> None:
        """
        BOT MOD. Modifies bot permissions for the server.

        Syntax:
            !permissions [ add | remove ] user <userID>
            !permissions [ add | remove ] role <roleID>
            !permissions [ add | remove ] channel <chanID>
        """
        global settings

        guild_str = str(ctx.guild.id)

        if not action:    # print permissions for server
            user_lines = [   # build users list
                f"{(await bot.fetch_user(u)).display_name} (id:{u})"
                for u in config.settings[guild_str]["perms"]["user_id"]
            ]
            owner = await bot.fetch_user(ctx.guild.owner_id)    # required to get the owner's name
            user_lines.insert(0, f"{owner.display_name} (id: {ctx.guild.owner_id})")
            users = "\n".join(user_lines)

            roles = "\n".join(   # build roles list
                f"{(role := discord.utils.get(ctx.guild.roles, id=id)).name} (id: {id})"
                for id in config.settings[guild_str]["perms"]["role_id"]
            )

            channels = "\n".join(   # build channels list
                f"#{(channel := bot.get_channel(id)).name} (id: {id})"
                for id in config.settings[guild_str]["perms"]["channel_id"]
            )

            embed = discord.Embed(    # build embed
                title=f"Permissions for {ctx.guild.name}",
                description="The following channels are enabled for bot commands, and the following users and roles are permitted for elevated permissions."
            )
            embed.add_field(name="Users:", value=users, inline=False)
            embed.add_field(name="Roles:", value=roles, inline=False)
            embed.add_field(name="Channels:", value=channels, inline=False)
            await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none()); return


        if not group or not target:    # syntax error
            raise func.err_syntax(); return

        target = int(target)    # convert to int
        
        if action == "add":    # add permission
            if target in config.settings[guild_str]["perms"][f"{group}_id"]:
                raise func.err_permissions_exist(); return

            config.settings[guild_str]["perms"][f"{group}_id"].append(target)
            config.SaveSettings()

        elif action == "remove":    # remove permission
            if target not in config.settings[guild_str]["perms"][f"{group}_id"]:
                raise func.err_permissions_exist(); return

            config.settings[guild_str]["perms"][f"{group}_id"].remove(target)
            config.SaveSettings()

        else:    # syntax error
            raise func.err_syntax(); return
        
        await ctx.reply(f"Successfully {action}ed {target} to {group}.", allowed_mentions=discord.AllowedMentions.none()); return


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

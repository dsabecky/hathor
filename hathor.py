####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands
from discord.ext.commands import Greedy, Context

# system level stuff
import asyncio  # prevents thread locking
import os       # system access

# data analysis
from typing import Literal, Optional     # legacy type hints
import pprint                            # pretty print

# hathor internals
import config                                           # bot config
import func                                             # bot specific functions (@decorators, err_ classes, etc)
from func import FancyErrors                            # error handling
from logs import log_sys, log_cogs, log_msg, log_voice  # logging
from cogs.voice import Voice                            # voice handling
from cogs.music import Music                            # music handling
from cogs.chatgpt import ChatGPT                        # chatgpt handling
from cogs.raiderio import RaiderIO                      # raiderio handling
from cogs.gamba import Gamba                            # gamba handling


####################################################################
# Console logging
####################################################################

osend  = Context.send
oreply = Context.reply

async def lsend(self, *args, **kwargs):
    embed = kwargs.get("embed")
    if embed:
        log_msg.info("EMBED:\n%s", pprint.pformat(embed.to_dict()))
    return await osend(self, *args, **kwargs)

async def lreply(self, *args, **kwargs):
    embed = kwargs.get("embed")
    if embed:
        log_msg.info("EMBED:\n%s", pprint.pformat(embed.to_dict()))
    return await oreply(self, *args, **kwargs)

Context.send  = lsend
Context.reply = lreply


####################################################################
# Bot initialization
####################################################################

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=config.BOT_PREFIX, intents=intents, case_insensitive=True)

extensions = [
    "cogs.voice",
    "cogs.music",
    "cogs.chatgpt",
    "cogs.raiderio",
    "cogs.gamba"
]
async def main():
  for ext in extensions:
    await bot.load_extension(ext)
  await bot.start(config.BOT_TOKEN)


####################################################################
# 'on_' listeners
####################################################################

@bot.event
async def on_ready() -> None:
    """
    Runs when the bot is ready.
    """

    if config.MAINTENANCE:  # am i in maintenance mode?
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.competing, name="maintenance!!!1"), status=discord.Status.do_not_disturb)

    log_sys.info(f"connected as \033[38;2;152;255;152m{bot.user}\033[0m")   # log connection to console

    ### TODO: change this to some kind of limit
    # log_sys.info(f"removing \033[38;2;152;255;152m{len([f for f in os.listdir('db/')])}\033[0m stale song files")
    # for filename in os.listdir("db/"):
    #     os.remove(f"db/{filename}")

    for guild in bot.guilds:    # build default settings into config if neccesary
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

@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    """
    Runs when the bot joins a new guild.
    """

    for guild in bot.guilds:    # build default settings into config if neccesary
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

@bot.event
async def on_voice_state_update(author: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    """
    Runs when a user joins or leaves a voice channel.
    """

    if before.channel is None and after.channel is not None: # joined
        log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: joined {after.channel.guild.name}/{after.channel}")
    elif before.channel is not None and after.channel is None: # left
        log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: left {before.channel.guild.name}/{before.channel}")
    elif before.channel != after.channel: # changed
        log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: moved in {before.channel.guild.name}: {before.channel} -> {after.channel}")

@bot.event
async def on_message(ctx: commands.Context) -> None:
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

    await bot.process_commands(ctx) # required to process @bot.command

@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    """
    Runs when an error occurs during a command.
    """

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, func.Error):
        return await FancyErrors(error.code, ctx.channel)
    else:
        raise error


####################################################################
# Command triggers
####################################################################

@bot.command(name="botleave")
@func.requires_owner_perms()
async def trigger_botleave(
    ctx: commands.Context,
    guild_id: Optional[int] = None
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

@bot.command(name="botservers")
@func.requires_owner_perms()
async def trigger_botservers(
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

@bot.command(name="botsync")
@func.requires_owner_perms()
async def trigger_botsync(
    ctx: Context,
    guilds: Greedy[discord.Object],
    spec: Optional[Literal["guild", "globalguild", "clearguild"]] = None
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

@bot.command(name='permissions', aliases=['perms', 'roles'])
@func.requires_author_perms()
async def trigger_permissions(
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
    asyncio.run(main())
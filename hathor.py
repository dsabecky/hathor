import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Greedy, Context

# extra functionality to manage bot / system files
import asyncio
import os
import json
from typing import Literal, Optional

# logging
import pprint
import logging
from logs import log_sys, log_cogs, log_msg, log_voice, log_gamba

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

# we need our config
import config

# get our special functions
import func
from func import FancyErrors, CheckPermissions

# set intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# intialize
bot = commands.Bot(command_prefix=config.BOT_PREFIX, intents=intents, case_insensitive=True)

# add voice category
log_cogs.info("loading 'Voice' cog")
from cogs.voice import Voice
asyncio.run(bot.add_cog(Voice(bot)))

# add music category
if config.BOT_YOUTUBE_KEY and config.BOT_SPOTIFY_CLIENT and config.BOT_SPOTIFY_SECRET:
    log_cogs.info("loading 'Music' cog")
    from cogs.music import Music
    asyncio.run(bot.add_cog(Music(bot)))

# add chatgpt category (if enabled)
if config.BOT_OPENAI_KEY:
    log_cogs.info("loading 'ChatGPT' cog")
    from cogs.chatgpt import ChatGPT
    asyncio.run(bot.add_cog(ChatGPT(bot)))

# add raiderio category
log_cogs.info("loading 'RaiderIO' cog")
from cogs.raiderio import RaiderIO
asyncio.run(bot.add_cog(RaiderIO(bot)))

# add gamba category
log_cogs.info("loading 'Gamba' cog")
from cogs.gamba import Gamba
asyncio.run(bot.add_cog(Gamba(bot)))

####################################################################
# on_ready()
####################################################################
@bot.event
async def on_ready():

    # am i in maintenance mode?
    if config.MAINTENANCE:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.competing, name="maintenance!!!1"), status=discord.Status.do_not_disturb)

    # log connection to console
    log_sys.info(f"connected as \033[38;2;152;255;152m{bot.user}\033[0m")

    # clean up temp folder
    log_sys.info(f"removing \033[38;2;152;255;152m{len([f for f in os.listdir('db/')])}\033[0m stale song files")
    for filename in os.listdir("db/"):
        os.remove(f"db/{filename}")

    # build default settings into config if neccesary
    for guild in bot.guilds:
        guild_str = str(guild.id)

        if guild_str not in config.settings:
            config.settings[guild_str] = {}
        if 'perms' not in config.settings[guild_str]:
            config.settings[guild_str]['perms'] = {}
            config.settings[guild_str]['perms'] = { 'user_id': [], 'role_id': [], 'channels': [] }
        if 'volume' not in config.settings[guild_str]:
            config.settings[guild_str]['volume'] = 20
        if 'voice_idle' not in config.settings[guild_str]:
            config.settings[guild_str]['voice_idle'] = 300
        if 'radio_intro' not in config.settings[guild_str]:
            config.settings[guild_str]['radio_intro'] = True
            
    config.SaveSettings()

####################################################################
# on_guild_join()
####################################################################
@bot.event
async def on_guild_join(guild):

    # build default settings into config if neccesary
    for guild in bot.guilds:
        guild_str = str(guild.id)

        if guild_str not in config.settings:
            config.settings[guild_str] = {}
        if 'perms' not in config.settings[guild_str]:
            config.settings[guild_str]['perms'] = {}
            config.settings[guild_str]['perms'] = { 'user_id': [], 'role_id': [], 'channels': [] }
        if 'volume' not in config.settings[guild_str]:
            config.settings[guild_str]['volume'] = 20
        if 'voice_idle' not in config.settings[guild_str]:
            config.settings[guild_str]['voice_idle'] = 300
        if 'radio_intro' not in config.settings[guild_str]:
            config.settings[guild_str]['radio_intro'] = True
            
    config.SaveSettings()

####################################################################
# on_voice_state_update()
####################################################################
@bot.event
async def on_voice_state_update(author, before, after):
    if before.channel is None and after.channel is not None: # joined
        log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: joined {after.channel.guild.name}/{after.channel}")
    elif before.channel is not None and after.channel is None: # left
        log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: left {before.channel.guild.name}/{before.channel}")
    elif before.channel != after.channel: # changed
        log_voice.info(f"\033[38;2;152;255;152m{author}\033[0m: moved in {before.channel.guild.name}: {before.channel} -> {after.channel}")

####################################################################
# on_message()
####################################################################
@bot.event
async def on_message(ctx):

    # log messages to console
    if ctx.guild:
        log_msg.info(f"\033[38;2;152;255;152m{ctx.author}@{ctx.guild.name}#{ctx.channel.name}\033[0m: {ctx.content}")
    else:
        log_msg.info(f"\033[38;2;152;255;152m{ctx.author}\033[0m: {ctx.content}")
    
    # new ignore
    if ctx.author == bot.user or not ctx.guild or (len(config.settings[str(ctx.guild.id)]['perms']['channels']) > 0 and ctx.channel.id not in config.settings[str(ctx.guild.id)]['perms']['channels']):
        return

    # test message
    if ctx.content.lower() == "foxtest":
        await ctx.reply(f'The quick brown fox jumps over the lazy dog 1234567890 ({bot.latency * 1000:.2f}ms)')

    # required to process @bot.command
    await bot.process_commands(ctx)

########################################################################################################################################


####################################################################
# trigger: !botleave
# ----
# Force the bot to leave a server.
####################################################################
@bot.command(name="botleave")
async def leave_guild(ctx: commands.Context, guild_id: Optional[int] = None):
    """
    BOT OWNER. Leave the provided discord server.
    
    Syntax:
        !botleave <guildID>
    """
    # permission check
    if ctx.author.id != config.BOT_ADMIN:
        await FancyErrors("AUTHOR_PERMS", ctx.channel)
        return

    if not guild_id:
        await FancyErrors("SYNTAX", ctx.channel)
        return

    guild = bot.get_guild(guild_id)

    # let them know
    await ctx.send(f"👋 Leaving **{guild.name}** (ID: {guild.id})…")

    # bye felicia
    await guild.leave()

####################################################################
# trigger: !botservers
# ----
# Displays all servers the bot is in.
####################################################################
@bot.command(name="botservers")
async def show_guilds(ctx: commands.Context):
    """
    BOT OWNER. Lists all guilds the bot is currently in.

    Syntax:
        !botservers
    """
    # permission check
    if ctx.author.id != config.BOT_ADMIN:
        await FancyErrors("AUTHOR_PERMS", ctx.channel)
        return

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

####################################################################
# trigger: !botsync
# ----
# Syncs /commands
####################################################################
@bot.command(name="botsync")
async def sync(
    ctx: Context,
    guilds: Greedy[discord.Object],
    spec: Optional[Literal["guild", "globalguild", "clearguild"]] = None
) -> None:
    """
    BOT OWNER. Syncronizes /slash commands.

    Syntax:
        !botsync [ guild | globalguild | clearguild ]
    """
    
    if ctx.author.id != config.BOT_ADMIN:
        FancyErrors("AUTHOR_PERMS", ctx.channel)

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

####################################################################
# trigger: !permissions
# alias: !perms, !roles
# ----
# TBD
####################################################################
@bot.command(name='permissions', aliases=['perms', 'roles'])
async def set_perms(ctx, opts=None, id_type=None, discord_id=None):
    """
    Modifies bot permissions for the server.

    Syntax:
        !permissions [ add | remove ] channel <chanID>
        !permissions [ add | remove ] group <groupID>
        !permissions [ add | remove ] user <userID>
    """
    global settings

    guild = await bot.fetch_guild(ctx.guild.id) # why cant i get this from ctx.guild???
    guild_id, guild_str = guild.id, str(guild.id)
    owner = await bot.fetch_user(guild.owner_id)
    owner_name = owner.name

    # are you even allowed to use this command?
    if not await CheckPermissions(bot, guild_id, ctx.author.id, ctx.author.roles):
        await FancyErrors("AUTHOR_PERMS", ctx.channel)
        return
    
    # display permissions for server
    if not opts:

        users, roles, channels = "", "", ""
        for id in config.settings[guild_str]['perms']['user_id']:
            user = await bot.fetch_user(id)
            users += f"{user.name} (id:{id})\n"
        users = users == "" and f"{owner_name} (id:{owner.id})" or f"{owner_name} (id:{owner.id})\n{users}"

        for id in config.settings[guild_str]['perms']['role_id']:
            role = discord.utils.get(guild.roles, id=id)
            roles += f" {role.name} (id:{role.id})\n"
        roles = roles == "" and "None" or roles

        for id in config.settings[guild_str]['perms']['channels']:
            channel = bot.get_channel(id)
            channels += f" #{channel.name} (id:{channel.id})\n"
        channels = channels == "" and "All channels." or channels

        output = discord.Embed(title=f"Permissions for {guild.name}", description="The following channels are enabled for bot commands, and the following users and roles are permitted for elevated permissions.")
        output.add_field(name="Channels:", value=channels, inline=False)
        output.add_field(name="Users:", value=users, inline=False)
        output.add_field(name="Roles:", value=roles, inline=False)
        await ctx.send(embed=output)
        return
    
    if (opts and not discord_id) or not discord_id.isdigit():
        await FancyErrors("SYNTAX", ctx.channel)
        return
    
    # make this an int cause python isnt smart enough to figure it out
    discord_id = int(discord_id)
    
    if opts == "add":

        if id_type == "user":
            # check if permissions already exist
            if discord_id in config.settings[guild_str]['perms']['user_id']:
                await FancyErrors("PERMISSIONS_EXIST", ctx.channel)
                return

            # update our settings and save file
            user = await bot.fetch_user(discord_id)
            config.settings[guild_str]['perms']['user_id'].append(discord_id)
            config.SaveSettings()

            # return a message so we know it works
            output = discord.Embed(title="Permissions Updated", description=f"Added {user.name} (id:{user.id}) to the permissions list.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        elif id_type == "group":
            # check if permissions already exist
            if discord_id in config.settings[guild_str]['perms']['role_id']:
                await FancyErrors("PERMISSIONS_EXIST", ctx.channel)
                return
            
            # update our settings and save file
            role = discord.utils.get(guild.roles, id=discord_id)
            config.settings[guild_str]['perms']['role_id'].append(discord_id)
            config.SaveSettings()

            # return a message so we know it works
            output = discord.Embed(title="Permissions Updated", description=f"Added {role.name} (id:{role.id}) to the permissions list.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        elif id_type == "channel":
            # check if permissions already exist
            if discord_id in config.settings[guild_str]['perms']['channels']:
                await FancyErrors("PERMISSIONS_EXIST", ctx.channel)
                return
            
            # update our settings and save file
            channel = bot.get_channel(discord_id)
            config.settings[guild_str]['perms']['channels'].append(discord_id)
            config.SaveSettings()

            # return a message so we know it works
            output = discord.Embed(title="Permissions Updated", description=f"Added #{channel.name} (id:{discord_id}) to the permissions list.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        else:
            await FancyErrors("SYNTAX", ctx.channel)

    if opts == "remove":

        if id_type == "user":
            # check if permission even exists
            if discord_id not in config.settings[guild_str]['perms']['user_id']:
                await FancyErrors("NO_PERMISSIONS_EXIST", ctx.channel)
                return
            
            # update our settings and save file
            user = await bot.fetch_user(discord_id)
            config.settings[guild_str]['perms']['user_id'].remove(discord_id)
            config.SaveSettings()

            # return a message so we know it works
            output = discord.Embed(title="Permissions Updated", description=f"Removed {user.name} (id:{user.id}) from the permissions list.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        elif id_type == "group":
            # check if permission even exists
            if discord_id not in config.settings[guild_str]['perms']['role_id']:
                await FancyErrors("NO_PERMISSIONS_EXIST", ctx.channel)
                return
            
            # update our settings and save file
            role = discord.utils.get(guild.roles, id=discord_id)
            config.settings[guild_str]['perms']['role_id'].remove(discord_id)
            config.SaveSettings()

            # return a message so we know it works
            output = discord.Embed(title="Permissions Updated", description=f"Removed {role.name} (id:{role.id}) from the permissions list.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        elif id_type == "group":
            # check if permission even exists
            if discord_id not in config.settings[guild_str]['perms']['channels']:
                await FancyErrors("NO_PERMISSIONS_EXIST", ctx.channel)
                return
            
            # update our settings and save file
            channel = bot.get_channel(discord_id)
            config.settings[guild_str]['perms']['channels'].remove(discord_id)
            config.SaveSettings()

            # return a message so we know it works
            output = discord.Embed(title="Permissions Updated", description=f"Removed {channel.name} (id:{discord_id}) from the permissions list.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

        else:
            await FancyErrors("SYNTAX", ctx.channel)


########################################################################################################################################

# all systems launch
bot.run(config.BOT_TOKEN)
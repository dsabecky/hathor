import discord
from discord.ext import commands
import datetime
import time
import asyncio
import yt_dlp
import os
import json

import config
import func
from func import LoadSettings, FancyErrors, CheckPermissions

def LoadSettings():
    try:
        with open('settings.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('settings.json', 'w') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default

settings = LoadSettings()

def SaveSettings():
    with open('settings.json', 'w') as file:
        json.dump(settings, file, indent=4)

queue = {}
currently_playing = {}
start_time = {}
last_activity_time = {}

# define the class
class Voice(commands.Cog, name="Voice"):
    def __init__(self, bot):
        self.bot = bot

    ####################################################################
    # on_ready()
    ####################################################################

    @commands.Cog.listener()
    async def on_ready(self):

        # build all our temp variables
        for guild in self.bot.guilds:
            guild_id, guild_str = guild.id, str(guild.id)

            if guild_str not in settings:
                settings[guild_str] = {}
            if 'volume' not in settings[guild_str]:
                settings[guild_str]['volume'] = 20
            if 'voice_idle' not in settings[guild_str]:
                settings[guild_str]['voice_idle'] = 300

            SaveSettings()

    ####################################################################
    # on_guild_join()
    ####################################################################
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        global settings

        # build default settings into config if neccesary
        guild_str = str(guild.id)
        if guild_str not in settings:
            settings[guild_str] = {}
        if 'volume' not in settings[guild_str]:
            settings[guild_str]['volume'] = 20
        if 'voice_idle' not in settings[guild_str]:
            settings[guild_str]['voice_idle'] = 300

        SaveSettings()

    ####################################################################
    # trigger: !idle
    # ----
    # idle_time: time (in minutes) that the bot will idle before d/c.
    # ----
    # Connects you to the users voice channel.
    ####################################################################
    @commands.command(name="idle")
    async def idle_time(self, ctx, idle_time=None):
        """
        Configure the time (mins) idle time before disconnecting.

        Syntax:
            !idle [1-30]
        """

        if not idle_time:
            output = discord.Embed(title="Idle Time", description=f"I will currently idle for {int(settings[str(ctx.guild.id)]['voice_idle'] / 60)} minutes.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())
            return

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, ctx.guild.id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return

        if not idle_time.isdigit():
            await FancyErrors("SYNTAX", ctx.channel)
            return
        
        idle_time = int(idle_time)

        if 1 <= idle_time <= 30:
            settings[str(ctx.guild.id)]['voice_idle'] = idle_time * 60
            SaveSettings()
            output = discord.Embed(title="Idle Time", description=f"Idle time is now {int(settings[str(ctx.guild.id)]['voice_idle'] / 60)} minutes.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())
        else:
            await FancyErrors("QUEUE_RANGE", ctx.channel)

    ####################################################################
    # trigger: !join
    # ----
    # Connects you to the users voice channel.
    ####################################################################
    @commands.command(name='join')
    async def join_voice(self, ctx):
        """
        Attempts to join the voice channel you reside.

        Syntax:
            !join
        """
        await JoinVoice(self.bot, ctx)

    ####################################################################
    # trigger: !leave
    # alias:   !part
    # ----
    # Leaves the current voice channel.
    ####################################################################
    @commands.command(name='leave', aliases=['part'])
    async def leave_voice(self, ctx):
        """
        Leaves the current voice channel the bot resides.

        Syntax:
            !leave
        """
        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, ctx.guild.id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return

        if ctx.guild.voice_client:
            await ctx.guild.voice_client.disconnect()

        else:
            await FancyErrors("BOT_NO_VOICE", ctx.channel)

    ####################################################################
    # trigger: !volume
    # alias: !vol
    # ----
    # args: [1-100]
    # ----
    # Adjusts the volume of the currently playing audio.
    ####################################################################
    @commands.command(name='volume', aliases=['vol'])
    async def song_volume(self, ctx, args=None):
        """
        Sets the bot volume for current server.

        Syntax:
            !volume <1-100>
        """
        guild_id, guild_str = ctx.guild.id, str(ctx.guild.id)
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

        if not args:
            await ctx.channel.send(f'Current volume is: {settings[guild_str]["volume"]}.')

        elif args.isdigit():
            if 0 <= int(args) <= 100:

                # are you even allowed to use this command?
                if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
                    await FancyErrors("AUTHOR_PERMS", ctx.channel)
                    return
                
                if guild_str in settings:
                    settings[guild_str]['volume'] = int(args)
                    SaveSettings()

                    if voice:
                        voice.source.volume = settings[guild_str]["volume"] / 100

                    await ctx.channel.send(f'Server volume changed to: {settings[guild_str]["volume"]}%.')

            else:
                await FancyErrors("VOL_RANGE", ctx.channel)


####################################################################
# function: JoinVoice(ctx)
# ----
# Joins the current voice channel.
####################################################################
async def JoinVoice(bot, ctx):
    if ctx.guild.voice_client and not await CheckPermissions(bot, ctx.guild.id, ctx.author.id, ctx.author.roles):
        await FancyErrors("BOT_EXIST_VOICE", ctx.channel)
    elif not ctx.author.voice:
        await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
    elif ctx.author.voice.channel.members >= ctx.author.voice.channel.user_limit:
        await FancyErrors("VOICE_FULL", ctx.channel)
    else:
        channel = ctx.author.voice.channel
        await channel.connect()
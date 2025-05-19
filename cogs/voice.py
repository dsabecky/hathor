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
from logs import log_cogs

queue = {}
currently_playing = {}
start_time = {}
last_activity_time = {}

# define the class
class Voice(commands.Cog, name="Voice"):
    def __init__(self, bot):
        self.bot = bot

    ####################################################################
    # trigger: !idle
    # ----
    # idle_time: time (in minutes) that the bot will idle before d/c.
    # ----
    # Connects you to the users voice channel.
    ####################################################################
    @commands.command(name="idle")
    @func.requires_author_perms()
    async def idle_time(self, ctx, idle_time=None):
        """
        Configure the time (mins) idle time before disconnecting.

        Syntax:
            !idle [1-30]
        """

        if not idle_time:
            output = discord.Embed(title="Idle Time", description=f"I will currently idle for {int(config.settings[str(ctx.guild.id)]['voice_idle'] / 60)} minutes.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())
            return

        if not idle_time.isdigit():
            raise func.err_syntax(); return
        
        idle_time = int(idle_time)

        if 1 <= idle_time <= 30:
            config.settings[str(ctx.guild.id)]['voice_idle'] = idle_time * 60
            config.SaveSettings()
            output = discord.Embed(title="Idle Time", description=f"Idle time is now {int(config.settings[str(ctx.guild.id)]['voice_idle'] / 60)} minutes.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())
        else:
            raise func.err_queue_range(); return

    ####################################################################
    # trigger: !join
    # ----
    # Connects you to the users voice channel.
    ####################################################################
    @commands.command(name='join')
    @func.requires_author_voice()
    async def join_voice(self, ctx):
        """
        Attempts to join the voice channel you reside.

        Syntax:
            !join
        """
        
        await self.bot._join_voice(ctx)

    ####################################################################
    # trigger: !leave
    # alias:   !part
    # ----
    # Leaves the current voice channel.
    ####################################################################
    @commands.command(name='leave', aliases=['part'])
    @func.requires_author_perms()
    @func.requires_bot_voice()
    async def leave_voice(self, ctx):
        """
        Leaves the current voice channel the bot resides.

        Syntax:
            !leave
        """

        await ctx.guild.voice_client.disconnect()

    ####################################################################
    # trigger: !volume
    # alias: !vol
    # ----
    # Adjusts the volume of the currently playing audio.
    ####################################################################
    @commands.command(name='volume', aliases=['vol'])
    @func.requires_author_perms()
    async def song_volume(self, ctx, args=None):
        """
        Sets the bot volume for current server.

        Syntax:
            !volume <1-100>
        """

        guild_id, guild_str = ctx.guild.id, str(ctx.guild.id)
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

        if not args:
            await ctx.channel.send(f'Current volume is: {config.settings[guild_str]["volume"]}%.')

        elif args.isdigit():
            if 0 <= int(args) <= 100:
                
                if guild_str in config.settings:
                    config.settings[guild_str]['volume'] = int(args)
                    config.SaveSettings()

                    if voice:
                        voice.source.volume = config.settings[guild_str]["volume"] / 100

                    await ctx.channel.send(f'Server volume changed to: {config.settings[guild_str]["volume"]}%.')

            else:
                raise func.err_vol_range(); return
    
async def setup(bot):
    log_cogs.info("Loading Voice cog...")
    await bot.add_cog(Voice(bot))
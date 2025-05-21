####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# hathor internals
from func import Error, ERROR_CODES
from func import requires_author_perms, requires_author_voice, requires_bot_voice
from logs import log_cog


####################################################################
# Global Variables
####################################################################

queue = {}
currently_playing = {}
start_time = {}
last_activity_time = {}


####################################################################
# Classes
####################################################################

class Voice(commands.Cog, name="Voice"):
    def __init__(self, bot):
        self.bot = bot


    ####################################################################
    # Command Triggers
    ####################################################################
    @commands.command(name="idle")
    @requires_author_perms()
    async def idle_time(self, ctx, idle_time=None):
        """
        Configure the time (mins) idle time before disconnecting.

        Syntax:
            !idle [1-30]
        """
        allstates = self.bot.settings[ctx.guild.id]

        if not idle_time:
            output = discord.Embed(title="Idle Time", description=f"I will currently idle for {int(allstates.voice_idle / 60)} minutes.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())
            return

        if not idle_time.isdigit():
            raise Error(ERROR_CODES['syntax'])
        
        idle_time = int(idle_time)

        if 1 <= idle_time <= 30:
            allstates.voice_idle = idle_time * 60
            allstates._save_settings()
            output = discord.Embed(title="Idle Time", description=f"Idle time is now {int(allstates.voice_idle / 60)} minutes.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())
        else:
            raise Error(ERROR_CODES['queue_range'])

    @commands.command(name='join')
    @requires_author_voice()
    async def join_voice(self, ctx):
        """
        Attempts to join the voice channel you reside.

        Syntax:
            !join
        """
        
        await self.bot._join_voice(ctx)

    @commands.command(name='leave', aliases=['part'])
    @requires_author_perms()
    @requires_bot_voice()
    async def leave_voice(self, ctx):
        """
        Leaves the current voice channel the bot resides.

        Syntax:
            !leave
        """

        await ctx.guild.voice_client.disconnect()

    @commands.command(name='volume', aliases=['vol'])
    @requires_author_perms()
    async def song_volume(self, ctx, args=None):
        """
        Sets the bot volume for current server.

        Syntax:
            !volume <1-100>
        """

        allstates = self.bot.settings[ctx.guild.id]
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

        if not args:
            await ctx.channel.send(f'Current volume is: {allstates.volume}%.'); return
        
        if not args.isdigit():
            raise Error(ERROR_CODES['syntax'])

        args = int(args)

        if 0 <= args <= 100:
            allstates.volume = args
            allstates._save_settings()

            if voice:
                voice.source.volume = allstates.volume / 100

            await ctx.channel.send(f'Server volume changed to: {allstates.volume}%.')

        else:
            raise Error(ERROR_CODES['vol_range'])


####################################################################
# Launch Cog
####################################################################

async def setup(bot):
    log_cog.info("Loading [dark_orange]Voice[/] cog...")
    await bot.add_cog(Voice(bot))
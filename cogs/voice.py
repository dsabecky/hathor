####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands

# hathor internals
from func import build_embed
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
    async def idle_time(self, ctx, idle_time: int = None):
        """
        Configure the time (mins) idle time before disconnecting.

        Syntax:
            !idle [1-30]
        """
        allstates = self.bot.settings[ctx.guild.id]

        if not idle_time:
            output = build_embed('Idle Time', f"🕒 I will currently idle for {int(allstates.voice_idle / 60)} minutes.", 'p')
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())
            return

        allstates.voice_idle = idle_time * 60
        allstates.save()
        output = build_embed('Idle Time', f"🕒 Idle time is now {int(allstates.voice_idle / 60)} minutes.", 'g')
        await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

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

        await ctx.reply(embed=build_embed('Voice', f"👋 Leaving {ctx.guild.voice_client.channel.name}", 'g'), allowed_mentions=discord.AllowedMentions.none())
        await ctx.guild.voice_client.disconnect()

    @commands.command(name='volume', aliases=['vol'])
    @requires_author_perms()
    async def song_volume(self, ctx, args: int = None):
        """
        Sets the bot volume for current server.

        Syntax:
            !volume <1-100>
        """

        allstates = self.bot.settings[ctx.guild.id]
        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

        if not args:
            await ctx.reply(embed=build_embed('Volume', f'🔊 Currently set to: {allstates.volume}%.', 'p'), allowed_mentions=discord.AllowedMentions.none())
            return

        allstates.volume = args
        allstates.save()

        if voice:
            voice.source.volume = allstates.volume / 100

        await ctx.reply(embed=build_embed('Volume', f'🔊 Server volume changed to: {allstates.volume}%.', 'g'), allowed_mentions=discord.AllowedMentions.none())


####################################################################
# Launch Cog
####################################################################

async def setup(bot):
    log_cog.info("🎤 Loading [dark_orange]Voice[/] cog…")
    await bot.add_cog(Voice(bot))
import discord
from discord.ext import commands

import datetime
import os
import time

import asyncio
import yt_dlp

import config
import func

from func import LoadSettings, FancyErrors, CheckPermissions
from cogs.voice import JoinVoice

settings = LoadSettings()

queue = {}
currently_playing = {}
start_time = {}
last_activity_time = {}

# define the class
class Music(commands.Cog, name="Music"):
    def __init__(self, bot):
        self.bot = bot

    ####################################################################
    # on_ready()
    ####################################################################

    @commands.Cog.listener()
    async def on_ready(self):

        # build all our temp variables
        for guild in self.bot.guilds:
            guild_id = guild.id

            if not guild_id in queue:
                queue[guild_id] = []
            if not guild_id in currently_playing:
                currently_playing[guild_id] = None
            if not guild_id in start_time:
                start_time[guild_id] = None
            if not guild_id in last_activity_time:
                last_activity_time[guild_id] = None
        
        # background task for voice idle checker
        self.bot.loop.create_task(CheckVoiceIdle(self.bot))

    ####################################################################
    # trigger: !bump
    # ----
    # Bumps requested song to top of the queue.
    ####################################################################
    @commands.command(name='bump')
    async def bump_song(
        self, ctx,
        song_number = commands.parameter(default=None, description="Song number in queue.")
        ):
        """
        Move the requested song to the top of the queue.

        Syntax:
            !bump song_number
        """
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return

        # is there even enough songs to justify?
        if guild_id in queue and len(queue[guild_id]) < 2:
            await FancyErrors("BUMP_SHORT", ctx.channel)

        elif not song_number or not song_number.isdigit() or (song_number.isdigit() and int(song_number) < 2):
            await FancyErrors("SYNTAX", ctx.channel)

        elif guild_id in queue:
            bumped = queue[guild_id].pop(int(song_number) - 1)
            queue[guild_id].insert(0, bumped)
            output = discord.Embed(description=f"Bumped {bumped['title']} to the top of the queue.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

    ####################################################################
    # trigger: !nowplaying
    # alias: !np, !song
    # ----
    # Plays a song.
    ####################################################################
    @commands.command(name='nowplaying', aliases=['np', 'song'])
    async def now_playing(self, ctx):
        """
        Displays the currently playing song.
        """
        if ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
            output = discord.Embed(title="Now Playing", description=await NowPlaying(ctx.guild.id))

            if currently_playing[ctx.guild.id] and currently_playing[ctx.guild.id]['thumbnail']:
                output.set_thumbnail(url=currently_playing[ctx.guild.id]['thumbnail'])
            await ctx.channel.send(embed=output)
        else:
            output = discord.Embed(title="Now Playing", description="There is currently nothing playing.")
            await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

    ####################################################################
    # trigger: !play
    # ----
    # Plays a song.
    ####################################################################
    @commands.command(name='play')
    async def play_song(self, ctx, *, args=None):
        """
        Adds a song to the queue.

        Syntax:
            !play [search | link]
        """
        guild_id = ctx.guild.id

        # author isn't in a voice channel
        if not ctx.author.voice:
            await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
            return

        # we're not in voice, lets change that
        if not ctx.guild.voice_client:
            await JoinVoice(ctx)

        # no data provided
        if not args:
            await FancyErrors("SYNTAX", ctx.channel)
            return
        
        # what are we doin here?
        song_type = args.startswith('https://') and 'link' or 'search'

        # build our message
        info_embed = discord.Embed(description=f"Searching for {args}")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

        # send down the assembly line
        await asyncio.create_task(QueueSong(self.bot, args, song_type, message, guild_id, ctx.guild.voice_client))

    ####################################################################
    # trigger: !queue
    # ----
    # Prints the song queue.
    ####################################################################
    @commands.command(name='queue')
    async def song_queue(self, ctx):
        """
        Displays the song queue.

        Syntax:
            !queue
        """
        guild_id = ctx.guild.id
        output = discord.Embed(title="Song Queue")

        # currently playing
        output.add_field(name="Now Playing:", value="Nothing playing.")
        if ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
            output.set_field_at(index=0, name="Now Playing:", value=f"{await NowPlaying(guild_id)}")
            if currently_playing[guild_id]['thumbnail']:
                output.set_thumbnail(url=currently_playing[guild_id]['thumbnail'])

        # queue
        output.add_field(name="Up Next:", value="No queue.")

        for i, song in enumerate(queue[guild_id], 1):
            if output.fields[1].value == "No queue.":
                output.set_field_at(index=1, name="Up Next:", value=f"[**{i}**] {song['title']}\n")
            else:
                output.set_field_at(index=1, name="Up Next:", value=f"{output.fields[1].value}**{i}**. {song['title']}\n")    

        await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

    ####################################################################
    # trigger: !remove
    # ----
    # Removes a song from queue.
    ####################################################################
    @commands.command(name='remove')
    async def remove_song(self, ctx, args=None):
        """
        Removes the requested song from queue.

        Syntax:
            !remove <song number>
        """
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return
        
        if not args or (args and not args.isdigit()):
            await FancyErrors("SYNTAX", ctx.channel)
            return

        args = int(args)

        if len(queue[guild_id]) == 0:
            await FancyErrors("NO_QUEUE", ctx.channel)

        elif not queue[guild_id][(args - 1)]:
            await FancyErrors("QUEUE_RANGE", ctx.channel)

        else:
            song = queue[guild_id].pop((int(args) - 1))
            await ctx.channel.send(f"Removed **{song['title']}** from queue.")

    ####################################################################
    # trigger: !skip
    # ----
    # Skips the current song.
    ####################################################################
    @commands.command(name='skip')
    async def skip_song(self, ctx):
        """
        Skips the currently playing song.

        Syntax:
            !skip
        """
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return
        
        if not ctx.guild.voice_client or not ctx.guild.voice_client.is_playing():
            await FancyErrors("NO_PLAYING", ctx.channel)
        else:
            ctx.guild.voice_client.stop()
            await ctx.channel.send(f"Skipped {currently_playing[guild_id]['title']}.")


####################################################################
# function: CheckVoiceIdle()
# ----
# Checks idle time when connected to voice channels to prevent
# being connected forever.
####################################################################
async def CheckVoiceIdle(bot):
    global last_activity_time
    while True:
        for voice_client in bot.voice_clients:
            guild_id = voice_client.guild.id
            if voice_client.is_playing():
                last_activity_time[guild_id] = time.time()
                continue
            if guild_id in last_activity_time and last_activity_time[guild_id]:
                if (time.time() - last_activity_time[guild_id]) > settings[str(guild_id)]['voice_idle']:
                    await voice_client.disconnect()
                    last_activity_time[guild_id] = None
        await asyncio.sleep(5)

####################################################################
# function: DownloadSong(args, type)
# ----
# args:       [search string | url]
# type:       ['search' | 'link']
# ----
# Returns prewritten errors.
####################################################################
async def DownloadSong(args, method):
    args = method == "search" and f"ytsearch:{args}" or args

    opts = {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "outtmpl": f'db/%(id)s',
        "playlist_items": f"1-{config.MUSIC_MAX_PLAYLIST}",
    }

    loop = asyncio.get_event_loop()
    
    async def download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, ydl.extract_info, args, True)
            if info:

                if '_type' in info and info['_type'] == "playlist":
                    song_list = []
                    for info in info['entries']:
                        if info['duration'] <= config.MUSIC_MAX_DURATION:
                            song_list.append({
                                "title": info['title'],
                                "path": f"db/{info['id']}.mp3",
                                "duration": info['duration'],
                                "thumbnail": info['thumbnail']
                            })
                    return song_list

                else:
                    if info['duration'] <= config.MUSIC_MAX_DURATION:
                        return [{
                            "title": info['title'],
                            "path": f"db/{info['id']}.mp3",
                            "duration": info['duration'],
                            "thumbnail": info['thumbnail']
                        }]
            else:
                return None
    
    return await download()

####################################################################
# function: GetSongInfo()
# ----
# args:       [search string | url]
# method:     ['search' | 'link']
# ----
# Returns prewritten errors.
####################################################################
async def GetSongInfo(args, method):
    args = method == "search" and f"ytsearch:{args}" or args

    loop = asyncio.get_event_loop()

    async def get_info():
        with yt_dlp.YoutubeDL() as ydl:
            info = await loop.run_in_executor(None, ydl.extract_info, args, False)
            
            if 'entries' in info:
                song_list = []
                for info in info['entries']:
                    if info['duration'] <= config.MUSIC_MAX_DURATION:
                        song_list.append({
                            "title": info['title'],
                            "duration": info['duration'],
                            "thumbnail": info['thumbnail'],
                            "url": info['webpage_url']
                        })
                return song_list

            else:
                if info['duration'] <= config.MUSIC_MAX_DURATION:
                    return [{
                        "title": info['title'],
                        "duration": info['duration'],
                        "thumbnail": info['thumbnail'],
                        "url": info['webpage_url']
                    }]
    
    return await get_info()

####################################################################
# function: NowPlaying(guild_id)
# ----
# guild_id: specify which server you're checking
# ----
# Parses the currently playing song.
####################################################################
async def NowPlaying(guild_id):
    global currently_playing, start_time
    if currently_playing:
        progress = time.time() - start_time[guild_id]
        total_duration = currently_playing[guild_id]["duration"]
        current = str(datetime.timedelta(seconds=int(progress)))
        total = str(datetime.timedelta(seconds=int(total_duration)))
        return f"{currently_playing[guild_id]['title']}\n**[**{current} **/** {total}**]**\n"
    
####################################################################
# function: PlayNextSong(channel)
# ----
# bot:      self.bot
# guild_id: guildID of server processing command
# channel:  ctx.guild.voice_channel
# ----
# Bootstrapper for songs, manages queue and info db.
####################################################################
async def PlayNextSong(bot, guild_id, channel):
    global queue, currently_playing, start_time
    
    if queue[guild_id] and not channel.is_playing():  # Check if channel is not currently playing
        song = queue[guild_id].pop(0)
        path, title = song["path"], song["title"]
        start_time[guild_id] = time.time()
        volume = settings[str(guild_id)]['volume'] / 100
        
        def after_playing(error):
            if os.path.exists(path):
                os.remove(path)  # Delete the song after playback

            if queue[guild_id]:  # Play the next song if the queue is not empty
                next_song = queue[guild_id][0]
                next_path = next_song["path"]
                next_title = next_song["title"]
                next_volume = settings[str(guild_id)]['volume'] / 100
                start_time[guild_id] = time.time()
                
                channel.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(next_path), volume=next_volume), after=after_playing)
                currently_playing[guild_id] = {
                    "title": next_title,
                    "duration": next_song["duration"],
                    "path": next_path,
                    "thumbnail": next_song["thumbnail"]
                }
            else:
                currently_playing[guild_id] = None
                bot.loop.create_task(bot.change_presence(activity=None))
        
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=title))
        channel.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(path), volume=volume), after=after_playing)
        currently_playing[guild_id] = {
            "title": title,
            "duration": song["duration"],
            "path": path,
            "thumbnail": song["thumbnail"]
        }
    
    elif not queue[guild_id]:
        currently_playing[guild_id] = None
        await bot.change_presence(activity=None)
    
####################################################################
# function: QueueSong(bot, args, method, message, guild_id, voice_client)
# ----
# TBD
# ----
# TBD
####################################################################
async def QueueSong(bot, args, method, message, guild_id, voice_client):
    global queue
    
    # give us a primer
    entries = await GetSongInfo(args, method)

    if entries:
        for entry in entries:
            song = await DownloadSong(entry['url'], 'link')
            queue[guild_id].append(song[0])

            if not voice_client.is_playing() and queue[guild_id]:
                await PlayNextSong(bot, guild_id, voice_client)

        if len(entries) == 1:
            embed = discord.Embed(description=f"Queued {entries[0]['title']} [{datetime.timedelta(seconds=entries[0]['duration'])}]")
        else:
            embed = discord.Embed(description=f"Queued {len(entries)} tracks.")
        await message.edit(content=None, embed=embed)
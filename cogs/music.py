import discord
from discord.ext import commands

# processing songs
import asyncio
import yt_dlp
import requests

# allow for extra bits
import datetime
import os
import time
import re
import uuid
import random
import openai
import json

# grab our important stuff
import config
import func
from func import LoadSettings, FancyErrors, CheckPermissions

# we need voice functions
from cogs.voice import JoinVoice

# load our settings from settings.json
settings = LoadSettings()

# build our temp variables
currently_playing = {}
last_activity_time = {}
queue = {}
repeat = {}
shuffle = {}
start_time = {}

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

            if not guild_id in last_activity_time:
                last_activity_time[guild_id] = None

            if not guild_id in repeat:
                repeat[guild_id] = False

            if not guild_id in shuffle:
                shuffle[guild_id] = False

            if not guild_id in start_time:
                start_time[guild_id] = None
        
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
    # trigger: !clear
    # ----
    # Clears the playlist.
    ####################################################################
    @commands.command(name='clear')
    async def clear_queue(self, ctx):
        """
        Clears the current playlist.

        Syntax:
            !clear
        """
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return
        
        if len(queue[guild_id]) == 0:
            await FancyErrors("NO_QUEUE", ctx.channel)
            return
        
        # author isn't in a voice channel
        if not ctx.guild.voice_client:
            await FancyErrors("BOT_NO_VOICE", ctx.channel)
            return
        
        # author isn't in a voice channel
        if not ctx.author.voice:
            await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
            return
        
        info_embed = discord.Embed(description=f"Removed {len(queue[guild_id])} songs from queue.")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())
        queue[guild_id] = []

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
        await asyncio.create_task(QueueSong(self.bot, args, song_type, False, message, guild_id, ctx.guild.voice_client))

    ####################################################################
    # trigger: !playnext
    # ----
    # Plays a song.
    ####################################################################
    @commands.command(name='playnext')
    async def prio_play(self, ctx, *, args=None):
        """
        Adds a song to the top of the queue (no playlists).

        Syntax:
            !play [search | link]
        """
        guild_id = ctx.guild.id
        is_playlist = '&list=' in args and True or False

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, ctx.guild.id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return

        # author isn't in a voice channel
        if not ctx.author.voice:
            await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
            return
        
        # playlists not supported with playnext
        if is_playlist:
            await FancyErrors("SHUFFLE_NO_PLAYLIST", ctx.channel)
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
        await asyncio.create_task(QueueSong(self.bot, args, song_type, True, message, guild_id, ctx.guild.voice_client))

    ####################################################################
    # trigger: !queue
    # alias:   !q, !nowplaying, !np, !song
    # ----
    # Prints the song queue.
    ####################################################################
    @commands.command(name='queue', aliases=['q', 'np', 'nowplaying', 'song'])
    async def song_queue(self, ctx):
        """
        Displays the song queue.

        Syntax:
            !queue
        """
        await GetQueue(ctx)

    ####################################################################
    # trigger: !radio
    # ----
    # Generates a ChatGPT 10 song playlist based off context.
    ####################################################################
    @commands.command(name="radio", aliases=['aiplaylist'])
    async def ai_playlist(self, ctx, *, args):
        """
        Generates a ChatGPT 10 song playlist based off context.

        Syntax:
            !radio <theme>
        """

        # is chatgpt enabled?
        if not config.BOT_OPENAI_KEY:
            await FancyErrors("DISABLED_FEATURE", ctx.channel)
            return
        
        # author isn't in a voice channel
        if not ctx.author.voice:
            await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
            return
        
        # we're not in voice, lets change that
        if not ctx.guild.voice_client:
            await JoinVoice(ctx)
        
        # what are you asking that's shorter, really
        if len(args) < 3:
            await FancyErrors("SHORT", ctx.channel)
            return
        
        conversation = [
            { "role": "system", "content": f"return only the information requested with no additional words or context" },
            { "role": "user", "content": f"make a playlist, which can include other artists based off {args}" }
        ]

        try:
            response = openai.ChatCompletion.create(
                model=config.BOT_OPENAI_MODEL,
                messages=conversation,
                temperature=0.8,
                max_tokens=1000
            )

            # filter out the goop
            parsed_response = response['choices'][0].message.content.split('\n')
            pattern = r'^\d+\.\s'

            playlist = []
            for item in parsed_response:
                if re.match(pattern, item):
                    parts = re.split(pattern, item, maxsplit=1)
                    if len(parts) == 2:
                        playlist.append(f"{parts[1].strip()} audio")

            info_embed = discord.Embed(description=f"[1/3] Generating your ChatGPT playlist...")
            message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())
            await QueueSong(self.bot, playlist, 'radio', False, message, ctx.guild.id, ctx.guild.voice_client)


        except openai.error.ServiceUnavailableError:
            await FancyErrors("API_ERROR", ctx.channel)
            return
        

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
    # trigger: !repeat
    # alias:   !loop
    # ----
    # Toggles song repeating.
    ####################################################################
    @commands.command(name='repeat', aliases=['loop'])
    async def repeat_song(self, ctx):
        """
        Toggles song repeating.

        Syntax:
            !repeat
        """
        global repeat
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return
        
        repeat[guild_id] = not repeat[guild_id]

        await ctx.send(f"🔁 Repeat mode {repeat[guild_id] and 'enabled' or 'disabled'}.")

    ####################################################################
    # trigger: !shuffle
    # ----
    # Enables our shuffle
    ####################################################################
    @commands.command(name='shuffle')
    async def shuffle_songs(self, ctx):
        """
        Toggles playlist shuffle.

        Syntax:
            !shuffle
        """
        global shuffle
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return
        
        random.shuffle(queue[guild_id])
        shuffle[guild_id] = not shuffle[guild_id]
        await ctx.send(f"🔀 Shuffle mode {shuffle[guild_id] and 'enabled' or 'disabled'}.")

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
            await ctx.channel.send(f"Skipping {currently_playing[guild_id]['title']}.")
            ctx.guild.voice_client.stop()
            if repeat[guild_id]:
                await PlayNextSong(self.bot, guild_id, ctx.guild.voice_client)

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

            # playing, update last play time
            if voice_client.is_playing():
                last_activity_time[guild_id] = time.time()
                continue

            # nothing playing w/o queue, update idle time
            elif last_activity_time[guild_id]:
                if (time.time() - last_activity_time[guild_id]) > settings[str(guild_id)]['voice_idle']:
                    await voice_client.disconnect()
                    last_activity_time[guild_id] = None

            # always checking whats next to play
            await PlayNextSong(bot, guild_id, voice_client)

        await asyncio.sleep(1)

####################################################################
# function: DownloadSong(args, type)
# ----
# args:       [search string | url]
# type:       ['search' | 'link']
# item:       int
# ----
# Returns prewritten errors.
####################################################################
async def DownloadSong(args, method, item=None):
    args = method == "search" and f"ytsearch:{args}" or args
    id = uuid.uuid4()

    if item:
        opts = {
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "outtmpl": f'db/{id}',
            "playlist_items": f"{item}",
            "ignoreerrors": True,
        }
    else:
        opts = {
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "outtmpl": f'db/{id}',
            "ignoreerrors": True,
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
                                "path": f"db/{id}.mp3",
                                "duration": info['duration'],
                                "thumbnail": info['thumbnail']
                            })
                    return song_list

                else:
                    if info['duration'] <= config.MUSIC_MAX_DURATION:
                        return [{
                            "title": info['title'],
                            "path": f"db/{id}.mp3",
                            "duration": info['duration'],
                            "thumbnail": info['thumbnail']
                        }]
            else:
                return None
    
    return await download()

####################################################################
# function: GetQueue(ctx)
# ----
# ctx: context
# extra: optional additional information (shuffle, etc)
# ----
# Returns currently playing and queue.
####################################################################
async def GetQueue(ctx, extra=None):
    guild_id = ctx.guild.id

    if not extra:
        output = discord.Embed(title="Song Queue")
    else:
        output = discord.Embed(title="Song Queue", description=f"{extra}")

    # currently playing
    output.add_field(name="Now Playing:", value="Nothing playing.")
    if ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
        output.set_field_at(index=0, name="Now Playing:", value=f"{await NowPlaying(guild_id)}")
        if currently_playing[guild_id]['thumbnail']:
            output.set_thumbnail(url=currently_playing[guild_id]['thumbnail'])

    # queue
    output.add_field(name="Up Next:", value="No queue.", inline=False)

    if len(queue[guild_id]) > 10:
        first_10 = queue[guild_id][:10]
        for i, song in enumerate(first_10, 1):
            if output.fields[1].value == "No queue.":
                output.set_field_at(index=1, name="Up Next:", value=f"**{i}**. {song['title']}\n")
            else:
                output.set_field_at(index=1, name="Up Next:", value=f"{output.fields[1].value}**{i}**. {song['title']}\n")
        output.set_field_at(index=1, name="Up Next:", value=f"{output.fields[1].value}And {len(queue[guild_id]) - 10} more...")

    else:
        for i, song in enumerate(queue[guild_id], 1):
            if output.fields[1].value == "No queue.":
                output.set_field_at(index=1, name="Up Next:", value=f"**{i}**. {song['title']}\n")
            else:
                output.set_field_at(index=1, name="Up Next:", value=f"{output.fields[1].value}**{i}**. {song['title']}\n")

    # repeat status
    output.add_field(name="Settings:", value=f"🔊: {settings[str(guild_id)]['volume']}%    🔁: {repeat[guild_id] and 'on' or 'off'}    🔀: {shuffle[guild_id] and 'on' or 'off'}", inline=False)

    await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

####################################################################
# function: NowPlaying(guild_id)
# ----
# guild_id: specify which server you're checking
# ----
# Parses the currently playing song.
####################################################################
async def NowPlaying(guild_id):
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
    global queue, currently_playing

    if channel.is_playing():
        return

    if queue[guild_id]:
        song = queue[guild_id].pop(0)
        path, title = song['path'], song['title']
        start_time[guild_id] = time.time()
        volume = settings[str(guild_id)]['volume'] / 100

        # delete song after playing
        def remove_song(error):
            if repeat[guild_id]:
                queue[guild_id].insert(0, song)
            else:
                os.remove(path)

        # actually play the song
        channel.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(path), volume=volume), after=remove_song)

        # update status
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=title))

        currently_playing[guild_id] = {
            "title": title,
            "duration": song["duration"],
            "path": path,
            "thumbnail": song["thumbnail"]
        }

    else:
        currently_playing[guild_id] = None
        await bot.change_presence(activity=None)
    
####################################################################
# function: QueueSong(bot, args, method, priority, message, guild_id, voice_client)
# ----
# TBD
# ----
# TBD
####################################################################
async def QueueSong(bot, args, method, priority, message, guild_id, voice_client):
    global queue

    try:
        # we've got a playlist
        is_playlist = (method == 'link' and '&list=' in args) and True or False
        if is_playlist:
            playlist_id = re.search(r'list=([a-zA-Z0-9_-]+)', args).group(1)
            response = requests.get(f'https://www.googleapis.com/youtube/v3/playlists?key={config.BOT_YOUTUBE_KEY}&part=contentDetails&id={playlist_id}')
            data = response.json()
            playlist_length = data['items'][0]['contentDetails']['itemCount'] <= 20 and data['items'][0]['contentDetails']['itemCount'] or 20

            for i in range(1, playlist_length):
                embed = discord.Embed(description=f"Loading {i} of {playlist_length} tracks...")
                await message.edit(content=None, embed=embed)
                try:
                    song = await DownloadSong(args, 'link', i)
                    queue[guild_id].append(song[0])

                    if not voice_client.is_playing() and queue[guild_id]:
                        await PlayNextSong(bot, guild_id, voice_client)
                except Exception as e:
                    print(f"Error: {e}")

            embed = discord.Embed(description=f"Added {playlist_length} tracks to queue.")
            await message.edit(content=None, embed=embed)

        # it's chatgpt dude
        if method == 'radio':
            playlist = args
            for i, item in enumerate(args, start=1):
                embed = discord.Embed(description=f"[2/3] Preparing your ChatGPT playlist ({i}/{len(args)})...")
                await message.edit(content=None, embed=embed)

                try:
                    song = await DownloadSong(item, 'search')
                    queue[guild_id].append(song[0])

                    if not voice_client.is_playing() and queue[guild_id]:
                        await PlayNextSong(bot, guild_id, voice_client)

                except Exception as e:
                    print(f"Error: {e}")

            embed = discord.Embed(description=f"[3/3] Your ChatGPT playlist has been added to queue!")
            await message.edit(content=None, embed=embed)


        # just an individial song
        else:
            try:
                song = await DownloadSong(args, method)

                if priority:
                    position = 0

                if shuffle[guild_id]:
                    if not priority:
                        position = random.randint(0, len(queue[guild_id]))

                    queue[guild_id].insert(position, song[0])
                    embed = discord.Embed(description=f"Added {song[0]['title']} to queue in position {position+1} (🔀).")
                else:
                    queue[guild_id].append(song[0])
                    embed = discord.Embed(description=f"Added {song[0]['title']} to queue.")

                
                await message.edit(content=None, embed=embed)

                if not voice_client.is_playing() and queue[guild_id]:
                    await PlayNextSong(bot, guild_id, voice_client)
            except Exception as e:
                print(f"Error: {e}")
    except Exception as e:
        print(f"An error has occured: {e}")

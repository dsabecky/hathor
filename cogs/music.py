import discord
from discord.ext import commands

# processing songs
import asyncio
import yt_dlp
import requests

# allow for extra bits
import datetime
import openai
import os
import random
import re
import time
import uuid
import json

# logging
from logs import log_music

# grab our important stuff
import config
import func
from func import LoadSettings, FancyErrors, CheckPermissions

# we need voice functions
from cogs.voice import JoinVoice

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

# build song history
def LoadHistory():
    try:
        with open('song_history.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('song_history.json', 'w') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default
        
def SaveHistory():
    with open('song_history.json', 'w') as file:
        json.dump(song_history, file, indent=4)

# radio setlists
def LoadRadio():
    try:
        with open('radio_playlists.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('radio_playlists.json', 'w') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default
        
def SaveRadio():
    with open('radio_playlists.json', 'w') as file:
        json.dump(radio_playlists, file, indent=4)

# build our temp variables
BOT_SPOTIFY_KEY = ""
currently_playing = {}
queue = {}
repeat = {}
shuffle = {}
endless_radio = {}

last_activity_time = {}
start_time = {}
pause_time = {}

song_history = LoadHistory()
radio_playlists = LoadRadio()
hot100 = []

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
            guild_str = str(guild.id)

            if not guild_id in queue:
                queue[guild_id] = []

            if not guild_id in currently_playing:
                currently_playing[guild_id] = None

            if not guild_id in endless_radio:
                endless_radio[guild_id] = False

            if not guild_str in song_history:
                song_history[guild_str] = []
                SaveHistory()

            if not guild_id in last_activity_time:
                last_activity_time[guild_id] = None

            if not guild_id in repeat:
                repeat[guild_id] = False

            if not guild_id in shuffle:
                shuffle[guild_id] = False

            if not guild_id in start_time:
                start_time[guild_id] = None

            if not guild_id in pause_time:
                pause_time[guild_id] = None

        # check if the queue is broken
        self.bot.loop.create_task(CheckBrokenPlaying(self.bot))
        
        # background task for voice idle checker
        self.bot.loop.create_task(CheckVoiceIdle(self.bot))

        # background task for endless mix
        self.bot.loop.create_task(CheckEndlessMix(self.bot))

        # generate a spotify key
        self.bot.loop.create_task(CreateSpotifyKey(self.bot))

    ####################################################################
    # on_voice_state_update()
    ####################################################################
    @commands.Cog.listener()
    async def on_voice_state_update(self, author, before, after):
        if self.bot.user == author:
            guild_id = author.guild.id
            voice_client = self.bot.get_guild(guild_id).voice_client

            # start playing music again if we move channels
            if currently_playing[guild_id] and voice_client:
                await asyncio.sleep(1)
                voice_client.resume()

    ####################################################################
    # trigger: !aiplaylist
    # ----
    # Generates a ChatGPT 10 song playlist based off context.
    ####################################################################
    @commands.command(name="aiplaylist")
    async def ai_playlist(self, ctx, *, args):
        """
        Generates a ChatGPT 10 song playlist based off context.

        Syntax:
            !aiplaylist <theme>
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
            await JoinVoice(self.bot, ctx)
        
        # what are you asking that's shorter, really
        if len(args) < 3:
            await FancyErrors("SHORT", ctx.channel)
            return
        
        try:
            response = await ChatGPT(
                self,
                "Return only the information requested with no additional words or context.",
                f"make a playlist of 10 songs, which can include other artists based off {args}"
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
    # trigger: !hot100
    # ----
    # Endlessly adds new music to the queue when enabled and there is
    # no queue.
    ####################################################################
    @commands.command(name='hot100')
    async def hot100_radio(self, ctx):
        """
        Toggles Billboard "Hot 100" radio.

        Syntax:
            !hot100
        """
        global endless_radio
        guild_id = ctx.guild.id
        current_year = datetime.datetime.now().year

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return
        
        # author isn't in a voice channel
        if not ctx.author.voice:
            await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
            return
        
        # we're not in voice, lets change that
        if not ctx.guild.voice_client:
            await JoinVoice(self.bot, ctx)

        if endless_radio[guild_id] == False:
            endless_radio[guild_id] = f"Billboard Hot💯 ({current_year})"
            await ctx.send(f"📻 Radio enabled, theme: **Billboard Hot💯 ({current_year})**")
        else:
            endless_radio[guild_id] = False
            await ctx.send(f"📻 Radio disabled.") 

    ####################################################################
    # trigger: !pause
    # ----
    # Pauses the song.
    ####################################################################
    @commands.command(name='pause')
    async def pause_song(self, ctx, *, args=None):
        """
        Pauses the song playing.

        Syntax:
            !pause
        """
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, ctx.guild.id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return

        # author isn't in a voice channel
        if not ctx.author.voice:
            await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
            return

        # we're not in voice, lets change that
        if not ctx.guild.voice_client:
            await FancyErrors("BOT_NO_VOICE", ctx.channel)
            return

        # we're not playing anything
        if not ctx.guild.voice_client.is_playing():
            await FancyErrors("NO_PLAYING", ctx.channel)
            return
        
        # hol' up fam (pause the song)
        pause_time[guild_id] = time.time()
        ctx.guild.voice_client.pause()

        # build our message
        info_embed = discord.Embed(description=f"⏸️ Playback paused.")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

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
            await JoinVoice(self.bot, ctx)

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
        is_playlist = ('&list=' in args or 'open.spotify.com/playlist' in args) and True or False

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
            await JoinVoice(self.bot, ctx)

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
    # Endlessly adds new music to the queue when enabled and there is
    # no queue.
    ####################################################################
    @commands.command(name='radio')
    async def ai_radio(self, ctx, *, args=None):
        """
        Toggles endless mix mode.

        Syntax:
            !radio [<null>|<theme>]
        """
        global endless_radio
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return

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
            await JoinVoice(self.bot, ctx)

        if args:
            endless_radio[guild_id] = args
            await ctx.send(f"📻 Radio enabled, theme: **{args}**.")
        elif endless_radio[guild_id] == False:
            endless_radio[guild_id] = "anything, im not picky"
            await ctx.send(f"📻 Radio enabled, theme: anything, im not picky.")
        else:
            endless_radio[guild_id] = False
            await ctx.send(f"📻 Radio disabled.")           

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
    # trigger: !resume
    # ----
    # Resumes song playback.
    ####################################################################
    @commands.command(name='resume')
    async def resume_song(self, ctx, *, args=None):
        """
        Resume song playback.

        Syntax:
            !resume
        """
        global start_time
        guild_id = ctx.guild.id

        # are you even allowed to use this command?
        if not await CheckPermissions(self.bot, ctx.guild.id, ctx.author.id, ctx.author.roles):
            await FancyErrors("AUTHOR_PERMS", ctx.channel)
            return

        # author isn't in a voice channel
        if not ctx.author.voice:
            await FancyErrors("AUTHOR_NO_VOICE", ctx.channel)
            return

        # we're not in voice
        if not ctx.guild.voice_client:
            await FancyErrors("BOT_NO_VOICE", ctx.channel)
            return

        # we're not playing anything
        if not ctx.guild.voice_client.is_paused():
            await FancyErrors("NO_PLAYING", ctx.channel)
            return
        
        # update the start_time
        start_time[guild_id] += (pause_time[guild_id] - start_time[guild_id])
        
        # catJAM lets vibe catJAM
        ctx.guild.voice_client.resume()

        # build our message
        info_embed = discord.Embed(description=f"🤘 Playback resumed.")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

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
# function: ChatGPT(bot, data)
# ----
# TBA
####################################################################
async def ChatGPT(bot, sys_content, user_content):
    conversation = [
        { "role": "system", "content": sys_content },
        { "role": "user", "content": user_content }
    ]

    try:
        response = openai.ChatCompletion.create(
            model=config.BOT_OPENAI_MODEL,
            messages=conversation,
            temperature=0.8,
            max_tokens=2000
        )
        return response

    except openai.error.ServiceUnavailableError:
        return "API_ERROR"

####################################################################
# function: CheckBrokenPlaying(bot)
# ----
# TBA
####################################################################
async def CheckBrokenPlaying(bot):
    while True:
        for guild in bot.guilds:
            guild_id = guild.id
            voice_client = bot.get_guild(guild_id).voice_client

            if voice_client and (not voice_client.is_playing() and not voice_client.is_paused()) and (guild_id in queue and queue[guild_id]):
                await PlayNextSong(bot, guild_id, voice_client)

        await asyncio.sleep(3)

####################################################################
# function: CheckEndlessMix(bot)
# ----
# TBA
####################################################################
async def CheckEndlessMix(bot):
    while True:
        for guild in bot.guilds:
            guild_id = guild.id
            guild_str = str(guild_id)
            voice_client = bot.get_guild(guild_id).voice_client

            # is this thing even on?
            if (guild_id in endless_radio and endless_radio[guild_id]) and (guild_id not in queue or not queue[guild_id]):
                    if voice_client:
                        theme = endless_radio[guild_id]

                        # hot100 checkpoint🔞
                        if "Billboard Hot💯" in theme:
                            
                            # does the chart already exist?
                            if len(hot100) == 0:
                                print("grabbing hot 100")
                                url = 'https://api.spotify.com/v1/playlists/37i9dQZF1DXcBWIGoYBM5M'
                                headers = {'Authorization': f'Bearer {BOT_SPOTIFY_KEY}'}

                                response = requests.get(url, headers=headers)
                                playlist_raw = response.json()
                                playlist = playlist_raw['tracks']['items']

                                for track in playlist:
                                    artist = track['track']['artists'][0]['name']
                                    song = track['track']['name']
                                    hot100.append(f"{artist} - {song}")

                            playlist = random.sample(hot100, 3)
                            print(hot100)
                            await QueueSong(bot, playlist, 'endless', False, 'endless', guild_id, voice_client)

                        # do we already know this theme?
                        elif theme.lower() in radio_playlists:
                            playlist = random.sample(radio_playlists[theme], 3)
                            await QueueSong(bot, playlist, 'endless', False, 'endless', guild_id, voice_client)


                        # we don't, lets build a setlist
                        else:
                            try:
                                radio_playlists[theme.lower()] = []
                                response = await ChatGPT(
                                    bot,
                                    "Return only the information requested with no additional words or context.",
                                    f"Make a playlist of 50 songs, including artist name (formatted as artist - song), themed around: {endless_radio[guild_id]}."
                                )

                                # filter out the goop
                                parsed_response = response['choices'][0].message.content.split('\n')
                                pattern = r'^\d+\.\s'

                                for item in parsed_response:
                                    if re.match(pattern, item):
                                        parts = re.split(pattern, item, maxsplit=1)
                                        radio_playlists[theme].append(parts[1].strip())

                                SaveRadio()

                            except openai.error.ServiceUnavailableError:
                                print("Service Unavailable :(")
                                return
        
        await asyncio.sleep(3)

####################################################################
# function: CheckVoiceIdle(bot)
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

        await asyncio.sleep(3)

####################################################################
# function: CreateSpotifyKey(bot)
# ----
# Generates a new Spotify API key.
####################################################################
async def CreateSpotifyKey(bot):
    global BOT_SPOTIFY_KEY
    while True:
        # generate a spotify key
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": config.BOT_SPOTIFY_CLIENT,
                "client_secret": config.BOT_SPOTIFY_SECRET
            }
        )
        data = response.json()
        log_music.info("Generated new Spotify API Access Token.")
        BOT_SPOTIFY_KEY = data['access_token']

        await asyncio.sleep(1800)



####################################################################
# function: DownloadSong(args, type, item)
# ----
# Downloads the song requested from QueueSong.
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
            "quiet": True,
        }
    else:
        opts = {
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "outtmpl": f'db/{id}',
            "ignoreerrors": True,
            "quiet": True,
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
# function: GetQueue(ctx, extra)
# ----
# Returns currently playing and queue.
####################################################################
async def GetQueue(ctx, extra=None):
    guild_id = ctx.guild.id
    voice_client = ctx.guild.voice_client

    if not extra:
        output = discord.Embed(title="Song Queue")
    else:
        output = discord.Embed(title="Song Queue", description=f"{extra}")

    # currently playing
    output.add_field(name="Now Playing:", value="Nothing playing.", inline=False)
    if voice_client and ((voice_client.is_playing() and currently_playing) or voice_client.is_paused()):

        title = currently_playing[guild_id]['title'].replace('*', r'\*')
        progress = voice_client.is_paused() and pause_time[guild_id] - start_time[guild_id] or time.time() - start_time[guild_id]
        total_duration = currently_playing[guild_id]["duration"]
        current = str(datetime.timedelta(seconds=int(progress)))
        total = str(datetime.timedelta(seconds=int(total_duration)))
        progress_bar = f"{voice_client.is_paused() and '⏸️' or '▶️'} {'▬' * int(10 * (int(progress) / int(total_duration)))}🔘{'▬' * (10 - int(10 * (int(progress) / int(total_duration))))}🔈[{current} / {total}]"
    
        output.set_field_at(index=0, name="Now Playing:", value=f"{title}\n{progress_bar}", inline=False)
        if currently_playing[guild_id]['thumbnail']:
            output.set_thumbnail(url=currently_playing[guild_id]['thumbnail'])

    output.add_field(name="Up Next:", value="No queue.", inline=False)

    # more than 10? let's set some boundaries...
    if len(queue[guild_id]) > 10:
        first_10 = queue[guild_id][:10]
        for i, song in enumerate(first_10, 1):
            title = song['title'].replace('*', r'\*')
            if output.fields[1].value == "No queue.":
                output.set_field_at(index=1, name="Up Next:", value=f"**{i}**. {title}\n", inline=False)
            else:
                output.set_field_at(index=1, name="Up Next:", value=f"{output.fields[1].value}**{i}**. {title}\n", inline=False)
        output.set_field_at(index=1, name="Up Next:", value=f"{output.fields[1].value}And {len(queue[guild_id]) - 10} more...", inline=False)

    # less than 10, give em the sauce
    else:
        for i, song in enumerate(queue[guild_id], 1):
            title = song['title'].replace('*', r'\*')
            if output.fields[1].value == "No queue.":
                output.set_field_at(index=1, name="Up Next:", value=f"**{i}**. {title}\n", inline=False)
            else:
                output.set_field_at(index=1, name="Up Next:", value=f"{output.fields[1].value}**{i}**. {title}\n", inline=False)

    # feature status
    output.add_field(name="Settings:", value=f"🔊: {settings[str(guild_id)]['volume']}%\n🔁: {repeat[guild_id] and 'on' or 'off'}\n🔀: {shuffle[guild_id] and 'on' or 'off'}\n📻: {endless_radio[guild_id] and endless_radio[guild_id] or 'off'}", inline=False)

    await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

####################################################################
# function: PlayNextSong(bot, guild_id, channel)
# ----
# Bootstrapper for songs, manages queue and info db.
####################################################################
async def PlayNextSong(bot, guild_id, channel):
    global queue, currently_playing, song_history
    guild_str = str(guild_id)

    if channel.is_playing() or channel.is_paused():
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

        # add to song history
        song_history[guild_str].append({"timestamp": time.time(), "title": title})
        SaveHistory()

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
# Brain of the music bot. Passes off data to DownloadSong and manages
# adding the music to the queue.
####################################################################
async def QueueSong(bot, args, method, priority, message, guild_id, voice_client):
    global queue

    try:
        # we've got a playlist
        is_playlist = method == 'link' and True or False
        if is_playlist and 'list=' in args:
            playlist_id = re.search(r'list=([a-zA-Z0-9_-]+)', args).group(1)
            response = requests.get(f'https://www.googleapis.com/youtube/v3/playlists?key={config.BOT_YOUTUBE_KEY}&part=contentDetails&id={playlist_id}')
            data = response.json()
            playlist_length = data['items'][0]['contentDetails']['itemCount'] <= config.MUSIC_MAX_PLAYLIST and data['items'][0]['contentDetails']['itemCount'] or config.MUSIC_MAX_PLAYLIST
            log_music.info(f"playlist ({playlist_id}) true length {data['items'][0]['contentDetails']['itemCount']}")

            for i in range(1, playlist_length):
                embed = discord.Embed(description=f"Loading {i} of {playlist_length} tracks...")
                await message.edit(content=None, embed=embed)
                try:
                    log_music.info(f"Downloading song {i} of playlist {playlist_id}")
                    song = await DownloadSong(args, 'link', i)
                    queue[guild_id].append(song[0])

                    if not voice_client.is_playing() and queue[guild_id]:
                        await PlayNextSong(bot, guild_id, voice_client)
                except Exception as e:
                    log_music.error(e)

            embed = discord.Embed(description=f"Added {playlist_length} tracks to queue.")
            await message.edit(content=None, embed=embed)
            return
        
        # spotify playlist
        elif is_playlist and 'open.spotify.com/playlist/' in args:
            playlist_id = re.search(r'/playlist/([a-zA-Z0-9]+)(?:[/?]|$)', args).group(1)
            response = requests.get(f'https://api.spotify.com/v1/playlists/{playlist_id}', headers={'Authorization': f'Bearer {BOT_SPOTIFY_KEY}'})
            data_raw = response.json()
            data = data_raw['tracks']['items']
            playlist_length = len(data) <= config.MUSIC_MAX_PLAYLIST and len(data) or config.MUSIC_MAX_PLAYLIST


            log_music.info(f"playlist ({playlist_id}) true length {len(data)}")

            for i, track in enumerate(data[:20], 1):
                embed = discord.Embed(description=f"Loading {i} of {playlist_length} tracks from \"{data_raw['name']}\"...")
                await message.edit(content=None, embed=embed)
                try:
                    log_music.info(f"Downloading song {i} of playlist {playlist_id}")
                    song = await DownloadSong(f"{track['track']['artists'][0]['name']} - {track['track']['name']} audio", "search")
                    queue[guild_id].append(song[0])

                    if not voice_client.is_playing() and queue[guild_id]:
                        await PlayNextSong(bot, guild_id, voice_client)
                except Exception as e:
                    log_music.error(e)

            embed = discord.Embed(description=f"Added {playlist_length} tracks to queue.")
            await message.edit(content=None, embed=embed)
            return

        # spotify link
        elif 'open.spotify.com/track/' in args:
            track_id = re.search(r'/track/([a-zA-Z0-9]+)(?:[/?]|$)', args).group(1)
            response = requests.get(f'https://api.spotify.com/v1/tracks/{track_id}', headers={'Authorization': f'Bearer {BOT_SPOTIFY_KEY}'})
            track = response.json()
            title = f"{track['artists'][0]['name']} - {track['name']}"

            try:
                log_music.info(f"Downloading {title}")
                embed = discord.Embed(description=f"Downloading {title}")
                await message.edit(content=None, embed=embed)
                song = await DownloadSong(f"{title} audio", "search")
                queue[guild_id].append(song[0])

                if not voice_client.is_playing() and queue[guild_id]:
                    await PlayNextSong(bot, guild_id, voice_client)
            except Exception as e:
                log_music.error(e)

            embed = discord.Embed(description=f"Added {song[0]['title']} to queue.")
            await message.edit(content=None, embed=embed)
            return

        # it's chatgpt dude
        elif method == 'radio':
            playlist = args
            temp = ""

            for i, item in enumerate(args, start=1):
                embed = discord.Embed(description=f"[2/3] Preparing your ChatGPT playlist ({i}/{len(args)})...")
                await message.edit(content=None, embed=embed)

                try:
                    log_music.info(f"Downloading song {i} of {len(playlist)} from chatgpt playlist")
                    song = await DownloadSong(item, 'search')
                    queue[guild_id].append(song[0])
                    temp += f"{i}. {song[0]['title']}\n"

                    if not voice_client.is_playing() and queue[guild_id]:
                        await PlayNextSong(bot, guild_id, voice_client)

                except Exception as e:
                    log_music.error(e)

            embed = discord.Embed(description=f"[3/3] Your ChatGPT playlist has been added to queue!")
            embed.add_field(name="Added:", value=f"{temp}", inline=False)

            await message.edit(content=None, embed=embed)
            return

        # endless!
        elif method == 'endless':
            playlist = args
            temp = ""

            for i, item in enumerate(args, start=1):

                try:
                    log_music.info(f"Downloading \"{item}\".")
                    song = await DownloadSong(f"{item} audio", 'search')
                    queue[guild_id].append(song[0])
                    temp += f"{i}. {song[0]['title']}\n"

                    if not voice_client.is_playing() and queue[guild_id]:
                        await PlayNextSong(bot, guild_id, voice_client)

                except Exception as e:
                    log_music.error(e)

            return

        # just an individial song
        else:
            try:
                log_music.info(f"Downloading song {args}")
                song = await DownloadSong(args, method)

                if shuffle[guild_id]:
                    if not priority:
                        position = random.randint(0, len(queue[guild_id]))

                    queue[guild_id].insert(position, song[0])
                    embed = discord.Embed(description=f"Added {song[0]['title']} to queue in position {position+1} (🔀).")
                    
                else:
                    if priority:
                        queue[guild_id].insert(0, song[0])
                    else:
                        queue[guild_id].append(song[0])

                    embed = discord.Embed(description=f"Added {song[0]['title']} to queue.")
                
                await message.edit(content=None, embed=embed)

                if not voice_client.is_playing() and queue[guild_id]:
                    await PlayNextSong(bot, guild_id, voice_client)
                    return

            except Exception as e:
                log_music.error(e)

    except Exception as e:
        log_music.error(e)

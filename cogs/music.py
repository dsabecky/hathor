####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands
from discord.ext.commands import Context

# audio processing
from gtts import gTTS   # song intros
import yt_dlp           # youtube library

# system level stuff
import asyncio      # prevents thread locking
import io           # read/write
import json         # logging (song history, settings, etc)
import os           # system access
import sys          # failure condition quits
import uuid         # we create uuid's for downloaded media instead of file names (lazy sanitization)
import requests     # grabbing raw data from url

# data analysis
import re                                       # regex for various filtering
from typing import List, Optional, TypedDict    # this is supposed to be "cleaner" for array pre-definition
from collections import defaultdict             # type hints

# date, time, numbers
import datetime     # timestamps for song history
import time         # epoch timing
import math         # cut playlists down using math.ceil() for fusion
import random       # pseudorandom selection (for shuffle, fusion playlist compilation, etc)

# openai libraries
import openai               # ai playlist generation, etc
from openai import OpenAI   # cleaner than manually calling openai.OpenAI()

# hathor internals
import config                                   # bot config
import func                                     # bot specific functions (@decorators, err_ classes, etc)
from cogs.voice import JoinVoice                # cleaner than cogs.voice.JoinVoice()
from logs import log_music                      # logging


####################################################################
# OpenAPI key validation
####################################################################

if not config.BOT_OPENAI_KEY:
    sys.exit("Missing OpenAI key. This is configured in hathor/config.py")

client = OpenAI(api_key=config.BOT_OPENAI_KEY)


####################################################################
# JSON -> global loading
####################################################################

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


####################################################################
# Global variables
####################################################################

BOT_SPOTIFY_KEY = ""
song_history = LoadHistory()
radio_playlists = LoadRadio()


####################################################################
# Classes
####################################################################

class CurrentlyPlaying(TypedDict):      # Dictionary structure for CurrentlyPlaying
    title: str
    song_artist: str
    song_title: str

    path: str
    thumbnail: str
    url: str

    duration: int  

class Settings:     # volatile settings, called as 'allstates' in functions
    def __init__(self):
        self.currently_playing: Optional[CurrentlyPlaying] = None

        self.queue: List[str] = []
        self.repeat: bool = False
        self.shuffle: bool = False

        self.radio_station: Optional[str] = None
        self.radio_fusions: Optional[List[str]] = None

        self.start_time: Optional[float] = None
        self.pause_time: Optional[float] = None
        self.last_active: Optional[float] = None

class Music(commands.Cog, name="Music"):    # Core cog for music functionality
    def __init__(self, bot):
        self.bot = bot
        self.settings: dict[int, Settings] = defaultdict(Settings)


    ####################################################################
    # Cog 'on_' listeners
    ####################################################################

    ### on_ready() #####################################################
    @commands.Cog.listener()
    async def on_ready(self):

        for guild in self.bot.guilds:

            allstates = self.settings[guild.id]     # load / init per server settings
            guild_str = str(guild.id)               # json is stupid and forces the key to be a string

            # init song history (if required)
            if not guild_str in song_history:
                song_history[guild_str] = []

        SaveHistory() # save our song history

        asyncio.create_task(self.CheckBrokenPlaying())   # check if the queue is broken
        asyncio.create_task(self.CheckEndlessMix())      # background task for endless mix
        asyncio.create_task(self.CheckVoiceIdle())       # background task for voice idle checker
        asyncio.create_task(self.CreateSpotifyKey())     # generate a spotify key

    ### on_guild_join() ################################################
    @commands.Cog.listener()
    async def on_guild_join(self, guild):

        allstates = self.settings[guild.id]     # init server settings
        guild_str = str(guild.id)               # json is stupid and forces the key to be a string

        if not guild_str in song_history:       # build and save song history (if required)
            song_history[guild_str] = []
            SaveHistory()

    ### on_voice_state_update() ########################################
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):

        # ignore everyone else
        if self.bot.user.id != member.id:
            return

        # voice_client = self.bot.get_guild(member.guild.id).voice_client
        allstates = self.settings[member.guild.id]
        voice_client = member.guild.voice_client

        # start playing music again if we move channels
        if allstates.currently_playing and voice_client:
            await asyncio.sleep(1)
            voice_client.resume()


    ####################################################################
    # Internal: Loops
    ####################################################################

    ### CheckBrokenPlaying(self) #######################################
    async def CheckBrokenPlaying(self):
        while True:
            for guild in self.bot.guilds:

                allstates = self.settings[guild.id]
                voice_client = guild.voice_client

                if voice_client and (not voice_client.is_playing() and not voice_client.is_paused()) and (allstates.queue):
                    await self.PlayNextSong(guild.id, voice_client)

            await asyncio.sleep(3)

    ### CheckEndlessMix(self) ##########################################
    async def CheckEndlessMix(self):
        while True:
            for guild in self.bot.guilds:

                allstates = self.settings[guild.id]
                voice_client = guild.voice_client

                # is this thing even on?
                if allstates.radio_station:
                        if voice_client:

                            ### TODO: FIX ME (i don't even know how this was supposed to work)
                            # fuse radio checkpoint🔞
                            # if allstates.radio_fusions:
                            #     playlist = random.sample(fuse_playlist[guild.id], 3)

                            #     # did we play this recently?
                            #     recent = song_history[str(guild_id)][-15:]
                            #     for item in recent:
                            #         for new in playlist:
                            #             if new in item['radio_title']:
                            #                 playlist.remove(new)

                            #     await QueueSong(bot, playlist, 'endless', False, 'endless', guild_id, voice_client)


                            ### TODO: FIX ME (this needs to be refactored anyway...)
                            # hot100 checkpoint🔞
                            # if "Billboard Hot💯" in allstates.radio_station:
                                
                            #     # does the chart already exist?
                            #     if len(hot100) == 0:
                            #         log_music.info("grabbing hot 100")
                            #         url = config.BILLBOARD_HOT_100
                            #         headers = {'Authorization': f'Bearer {BOT_SPOTIFY_KEY}'}

                            #         response = requests.get(url, headers=headers)
                            #         playlist_raw = response.json()
                            #         playlist = playlist_raw['tracks']['items']

                            #         for track in playlist:
                            #             artist = track['track']['artists'][0]['name']
                            #             song = track['track']['name']
                            #             hot100.append(f"{artist} - {song}")

                            #     playlist = random.sample(hot100, 3)
                            #     await QueueSong(bot, playlist, 'endless', False, 'endless', guild_id, voice_client)

                            # do we already know this theme?
                            if allstates.radio_station.lower() in radio_playlists:
                                playlist = random.sample(radio_playlists[allstates.radio_station.lower()], 3)
                                await QueueSong(bot, playlist, 'endless', False, 'endless', guild_id, voice_client)


                            # we don't, lets build a setlist
                            else:
                                try:
                                    radio_playlists[allstates.radio_station.lower()] = []

                                    response = await ChatGPT(
                                        bot,
                                        "Return only the information requested with no additional words or context.",
                                        f"Make a playlist of 50 songs (formatted as artist - song), themed around: {radio_station[guild_id]}. Include similar artists and songs."
                                    )

                                    # filter out the goop
                                    parsed_response = response.split('\n')
                                    pattern = r'^\d+\.\s'

                                    # build our new playlist
                                    for item in parsed_response:
                                        if re.match(pattern, item):
                                            parts = re.split(pattern, item, maxsplit=1)
                                            radio_playlists[allstates.radio_station.lower()].append(parts[1].strip())

                                    SaveRadio()

                                except Exception as e:
                                    log_music.error(f"CheckEndlessMix(): {e}")
            
            await asyncio.sleep(10)

    ### CheckVoiceIdle #################################################
    async def CheckVoiceIdle(self):

        while True:
            for voice_client in self.bot.voice_clients:

                allstates = self.settings[voice_client.guild.id]

                # playing, update last play time
                if voice_client.is_playing():
                    allstates.last_active = time.time()
                    continue

                # nothing playing w/o queue, update idle time
                elif allstates.last_active:
                    if (time.time() - allstates.last_active) >= config.settings[str(voice_client.guild.id)]['voice_idle']:
                        await voice_client.disconnect()
                        allstates.last_active= None

                # always checking whats next to play
                await self.PlayNextSong(voice_client.guild.id, voice_client)

            await asyncio.sleep(3)

    ### CreateSpotifyKey(self) #########################################
    async def CreateSpotifyKey(self):
        global BOT_SPOTIFY_KEY # write access for global

        while True:
            def blocking_call():
                return requests.post(
                    "https://accounts.spotify.com/api/token", headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={ "grant_type": "client_credentials", "client_id": config.BOT_SPOTIFY_CLIENT, "client_secret": config.BOT_SPOTIFY_SECRET }
                )

            try:
                response = await asyncio.to_thread(blocking_call)
                data = response.json()
                log_music.info("Generated new Spotify API Access Token.")
                BOT_SPOTIFY_KEY = data['access_token']
            
            except Exception as e:
                log_music.error(f"Failed to generate Spotify API Access Token: {e}")

            await asyncio.sleep(config.SPOTIFY_KEY_REFRESH)


    ####################################################################
    # Internal: Functions
    ####################################################################

    ### ChatGPT(self, system, user) ####################################
    async def ChatGPT(self, sys_content: str, user_content: str) -> str:
        conversation = [
            { "role": "system", "content": sys_content },
            { "role": "user", "content": user_content }
        ]

        def blocking_call():
            return client.chat.completions.create(
                model=config.BOT_CHATGPT_MODEL,
                messages=conversation,
                temperature=config.BOT_OPENAI_TEMPERATURE
            )

        try:
            response = await asyncio.to_thread(blocking_call)

        except Exception as e:
            log_music.error(f"ChatGPT(): {e}")

        return response.choices[0].message.content

    ### DownloadSong(self, args, type, item) ###########################
    async def DownloadSong(self, args, method, item=None):
        if args.endswith(" audio"):
            strip_audio = args.rstrip(" audio")
            split_args = "-" in strip_audio and strip_audio.split(" - ", 1) or strip_audio
            song_artist, song_title = split_args[0], split_args[1]
        else:
            strip_audio = args
            song_artist = ""
            song_title = args

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
                                    "thumbnail": info['thumbnail'],
                                    "song_artist": song_artist,
                                    "song_title": song_title,
                                    "url": info['webpage_url'],
                                    "radio_title": strip_audio or args
                                })
                        return song_list

                    else:
                        if info['duration'] <= config.MUSIC_MAX_DURATION:
                            return [{
                                "title": info['title'],
                                "path": f"db/{id}.mp3",
                                "duration": info['duration'],
                                "thumbnail": info['thumbnail'],
                                "song_artist": song_artist,
                                "song_title": song_title,
                                "url": info['webpage_url'],
                                "radio_title": strip_audio or args
                            }]
                else:
                    return None
        
        return await download()

    ### GetQueue(context) ##############################################
    async def GetQueue(self, ctx: Context):

        allstates = self.settings[ctx.guild.id]
        voice_client = ctx.guild.voice_client

        title = "Song Queue"
        embed = discord.Embed(title=title, description=None, color=discord.Color.blurple())

        # now playing section
        if voice_client and allstates.currently_playing and (voice_client.is_playing() or voice_client.is_paused()):
            elapsed = (allstates.pause_time - allstates.start_time) if voice_client.is_paused() else (time.time() - allstates.start_time)
            total = allstates.currently_playing["duration"]
            ratio = min(max(elapsed / total, 0.0), 1.0)

            bar_width = 10
            filled = int(ratio * bar_width)
            empty = bar_width - filled
            status_emoji = "⏸️" if vc.is_paused() else "▶️"
            progress_bar = (
                f"{status_emoji} "
                f"{'▬' * filled}🔘{'▬' * empty} "
                f"[{str(datetime.timedelta(seconds=int(elapsed)))}"
                f" / {str(datetime.timedelta(seconds=int(total)))}]"
            )

            np_title = allstates.currently_playing["title"].replace("*", r"\*")
            np_text = f"{np_title}\n{progress_bar}"
            embed.add_field(name="Now Playing", value=np_text, inline=False)

            thumb = allstates.currently_playing.get("thumbnail")
            if thumb:
                embed.set_thumbnail(url=thumb)

        else:
            embed.add_field(name="Now Playing", value="Nothing playing.", inline=False)

        # up next section
        queue = allstates.queue
        if not queue:
            up_next_text = "No queue."

        else:
            display = queue[:10]
            lines = [
                f"**{i+1}.** {item['title'].replace('*', r'\\*')}"
                for i, item in enumerate(display)
            ]

            if len(queue) > 10:
                lines.append(f"…and {len(queue) - 10} more")
            up_next_text = "\n".join(lines)

        embed.add_field(name="Up Next", value=up_next_text, inline=False)

        # music settings
        settings = config.settings[str(ctx.guild.id)]
        volume = settings["volume"]
        repeat_status = "on" if allstates.repeat else "off"
        shuffle_status = "on" if allstates.shuffle else "off"

        # radio settings
        radio = allstates.radio_station or "off"

        ### TODO: FIXME (with the rest of fusion)
        # fused = ""
        # if guild_id in radio_fusions:
        #     fused = ", ".join(f'{s}' for s in radio_fusions[guild_id])
        #     fused = f"♾️ {fused} ♾️"

        intro = "on" if settings["radio_intro"] else "off"


        settings_text = (   # build radio settings text
            f"```🔊 vol: {volume}%  🔁 repeat: {repeat_status}  🔀 shuffle: {shuffle_status}```"
            #f"```📢 intro: {intro}\n📻 Radio: {fused and fused or endless}```"
            f"```📢 intro: {intro}\n📻 Radio: {radio}```"
        )
        embed.add_field(name="Settings", value=settings_text, inline=False)

        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    ### PlayNextSong(self, guild.id, channel.id) ##################
    async def PlayNextSong(self, guild_id, channel):

        allstates = self.settings[ctx.guild.id]
        guild_str = str(ctx.guild.id)

        if channel.is_playing() or channel.is_paused():    # stop trying if we're playing something (or paused)
            return

        if allstates.queue:
            song = allstates.queue.pop(0)
            path, title, song_artist, song_title = song['path'], song['title'], song['song_artist'], song['song_title']
            allstates.start_time = time.time()
            volume = config.settings[guild_str]['volume'] / 100
            intro_volume = config.settings[guild_str]['volume'] < 80 and (config.settings[guild_str]['volume'] + 15) / 100

            ### TODO: this should be in config.py
            intros = [  # standard song introductions
                f"Ladies and gentlemen, hold onto your seats because we're about to unveil the magic of {song_title} by {song_artist}. Only here at {channel.guild.name} radio.",
                f"Turning it up to 11! brace yourselves for {song_artist}'s masterpiece {song_title}. Here on {channel.guild.name} radio.",
                f"Rock on, warriors! We're cranking up the intensity with {song_title} by {song_artist} on {channel.guild.name} radio.",
                f"Welcome to the virtual airwaves! Get ready for a wild ride with a hot track by {song_artist} on {channel.guild.name} radio.",
                f"Buckle up, folks! We're about to take you on a musical journey through the neon-lit streets of {channel.guild.name} radio.",
                f"Hello, virtual world! It's your DJ, {self.bot.user.display_name or self.bot.user.name}, in the house, spinning {song_title} by {song_artist}. Only here on {channel.guild.name} radio.",
                f"Greetings from the digital realm! Tune in, turn up, and let the beats of {song_artist} with {song_title} take over your senses, here on {channel.guild.name} radio.",
                f"Time to crank up the volume and immerse yourself in the eclectic beats of {channel.guild.name} radio. Let the madness begin with {song_title} by {song_artist}!"
            ]

            ### TODO: this should only be ran if we decided we're going to use it
            special_response = await ChatGPT(self.bot,   # special song introductions
                "Return only the information requested with no additional words or context.",
                f'Give me a short talking point about the song "{song_artist} - {song_title}" that I can use before playing it on my radio station. No longer than two sentences. Use the tone and cadance of a radio DJ.'
            )
            special_intro = special_response

            def remove_song(error):     # delete song after playing
                if allstates.repeat:
                    allstates.queue.insert(0, song)
                else:
                    os.remove(path)

            def play_after_intro(junk):     # wait for intro to finish (if enabled)
                allstates.intro_playing = False

            ### TODO: is there a better way to do this??
            if song_artist != "" and config.settings[guild_str]['radio_intro'] and random.randint(1, 5) != 5:   # add an intro (if radio is enabled)
                allstates.intro_playing = True

                ### TODO: if we make special intro run only when needed, this needs to change (to include intro.mp3 to something linked to the queue / song specifically)
                intro = gTTS(f"{random.choice([random.choice(intros), f'{special_intro} Here on {channel.guild.name} radio.'])}", lang='en', slow=False)
                intro.save("db/intro.mp3")

                ### TODO: if we make special intro run only when needed, this needs to change to something linked to the song specifically
                # actually play the song
                channel.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio("db/intro.mp3"), volume=intro_volume), after=play_after_intro)

            ### TODO: There has to be a better way to manage this, cause this is buggy (sometimes)
            while allstates.intro_playing == True:
                await asyncio.sleep(0.5)

            # actually play the song
            channel.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(path), volume=volume), after=remove_song)

            # add to song history
            song_history[guild_str].append({"timestamp": time.time(), "title": title, "radio_title": song['radio_title']})
            SaveHistory()

            allstates.currently_playing = {
                "title": title,
                "duration": song["duration"],
                "path": path,
                "thumbnail": song["thumbnail"],
                "url": song["url"],
                "song_artist": song_artist,
                "song_title": song_title
            }

        else:
            allstates.currently_playing = None


    ####################################################################
    # Command triggers
    ####################################################################

    ### !aiplaylist ####################################################
    @commands.command(name="aiplaylist", aliases=['smartplaylist'])
    @func.requires_author_voice()
    @func.requires_message_length(3)
    async def trigger_aiplaylist(self, ctx, *, args: str):
        """
        Generates a ChatGPT 10 song playlist based off context.

        Syntax:
            !aiplaylist <theme>

        Aliases:
            !smartplaylist
        """       

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await JoinVoice(self.bot, ctx)
        
        try:
            response = await ChatGPT(
                self,
                "Return only the information requested with no additional words or context.",
                f"make a playlist of 10 songs, which can include other artists based off {args}"
            )

            # filter out the goop
            parsed_response = response.split('\n')
            pattern = r'^\d+\.\s'

            playlist = []
            for item in parsed_response:
                if re.match(pattern, item):
                    parts = re.split(pattern, item, maxsplit=1)
                    if len(parts) == 2:
                        playlist.append(f"{parts[1].strip()} audio")

            info_embed = discord.Embed(description=f"[1/3] Generating your AI playlist...")
            message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())
            await QueueSong(self.bot, playlist, 'radio', False, message, ctx.guild.id, ctx.guild.voice_client)

        except Exception as e:
            return

    ### !bump ##########################################################
    @commands.command(name='bump')
    @func.requires_author_perms()
    @func.requires_author_voice()
    @func.requires_queue()
    async def trigger_bump(self, ctx, song_number = commands.parameter(default=None, description="Song number in queue.")):
        """
        Move the requested song to the top of the queue.

        Syntax:
            !bump <song number>
        """

        allstates = self.settings[ctx.guild.id]

        if len(allstates.queue) < 2:    # is there even enough songs to justify?
            raise func.err_bump_short(); return

        elif not song_number or not song_number.isdigit() or int(song_number) < 2:
            raise func.err_syntax(); return

        bumped = allstates.queue.pop(int(song_number) - 1)
        allstates.queue.insert(0, bumped)
        output = discord.Embed(description=f"Bumped {bumped['title']} to the top of the queue.")
        await ctx.reply(embed=output, allowed_mentions=discord.AllowedMentions.none())

    ### !clear #########################################################
    @commands.command(name='clear')
    @func.requires_author_perms()
    @func.requires_author_voice()
    @func.requires_bot_voice()
    @func.requires_queue()
    async def trigger_clear(self, ctx):
        """
        Clears the current playlist.

        Syntax:
            !clear
        """

        allstates = self.settings[ctx.guild.id]
        
        info_embed = discord.Embed(description=f"Removed {len(allstates.queue)} songs from queue.")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())
        allstates.queue = []

    ### !defuse ########################################################
    # @commands.command(name='defuse')
    # async def deradio_fusions(self, ctx, *, args=None):
    #     """
    #     Removes a fused station from the mix.

    #     Syntax:
    #         !defuse <theme>
    #     """

    #     global radio_station
    #     guild_id = ctx.guild.id

    #     # are you even allowed to use this command?
    #     if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
    #         await FancyErrors("AUTHOR_PERMS", ctx.channel); return
        
    #     # author isn't in a voice channel
    #     if not ctx.author.voice:
    #         await FancyErrors("AUTHOR_NO_VOICE", ctx.channel); return
        
    #     # empty theme
    #     if not args:
    #         await FancyErrors("SYNTAX", ctx.channel); return
        
    #     # is the radio even on?
    #     if radio_station[guild_id] == False:
    #         await FancyErrors("NO_RADIO", ctx.channel); return
        
    #     # fusion doesnt exist
    #     if guild_id not in radio_fusions or (radio_fusions[guild_id] and args.lower() not in radio_fusions[guild_id]):
    #         await FancyErrors("NO_FUSE_EXIST", ctx.channel); return
        
    #     # let's defuse this situation
    #     if any(station.lower() == args.lower() for station in radio_fusions[guild_id]):
    #         radio_fusions[guild_id].remove(args)

    #     # send our mesage and build a new station
    #     info_embed = discord.Embed(description=f"📻 Removed \"{args}\" from the radio.")
    #     message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())
    #     await FuseRadio(self.bot, ctx)

    ### !fuse ##########################################################
    # @commands.command(name='fuse')
    # async def radio_fusions(self, ctx, *, args=None):
    #     """
    #     Fuses a new radio station into the current station(s).
    #     You can add multiple fusions by separating with: |

    #     Syntax:
    #         !fuse <theme>
    #         !fuse <theme> | <theme>
    #     """

    #     global radio_station
    #     guild_id = ctx.guild.id

    #     # are you even allowed to use this command?
    #     if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
    #         await FancyErrors("AUTHOR_PERMS", ctx.channel); return
        
    #     # author isn't in a voice channel
    #     if not ctx.author.voice:
    #         await FancyErrors("AUTHOR_NO_VOICE", ctx.channel); return
        
    #     # empty theme
    #     if not args:
    #         await FancyErrors("SYNTAX", ctx.channel); return
        
    #     # theres no radio playing
    #     if radio_station[guild_id] == False:
    #         await FancyErrors("NO_RADIO", ctx.channel); return
        
    #     if guild_id in radio_fusions and args in radio_fusions[guild_id]:
    #         await FancyErrors("RADIO_EXIST", ctx.channel); return
        
    #     # get list of stations
    #     stations = ""
    #     if "|" in args:
    #         for i, part in enumerate(args.split("|"), 1):
    #             stations += i == 1 and f"**{part}**" or f", **{part}**"  
    #     else:
    #         stations = f"**{args}**"
        
    #     # too short
    #     if len(args) < 3:
    #         await FancyErrors("SHORT", ctx.channel); return
        
    #     # we're not in voice, lets change that
    #     if not ctx.guild.voice_client:
    #         await JoinVoice(self.bot, ctx)        
        
    #     # let's fuse the radio
    #     info_embed = discord.Embed(description=f"📻 Fusing \"{stations}\" into the radio.")
    #     message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())
    #     await FuseRadio(self.bot, ctx, args)        

    ### !hot100 ########################################################
    # @commands.command(name='hot100')
    # async def hot100_radio(self, ctx):
    #     """
    #     Toggles Billboard "Hot 100" radio.

    #     Syntax:
    #         !hot100
    #     """

    #     global radio_station
    #     guild_id = ctx.guild.id
    #     current_year = datetime.datetime.now().year

    #     # are you even allowed to use this command?
    #     if not await CheckPermissions(self.bot, guild_id, ctx.author.id, ctx.author.roles):
    #         await FancyErrors("AUTHOR_PERMS", ctx.channel); return
        
    #     # author isn't in a voice channel
    #     if not ctx.author.voice:
    #         await FancyErrors("AUTHOR_NO_VOICE", ctx.channel); return
        
    #     # we're not in voice, lets change that
    #     if not ctx.guild.voice_client:
    #         await JoinVoice(self.bot, ctx)

    #     if radio_station[guild_id] == False:
    #         radio_station[guild_id] = f"Billboard Hot💯 ({current_year})"
    #         info_embed = discord.Embed(description=f"📻 Radio enabled, theme: **Billboard Hot💯 ({current_year})**")
    #     else:
    #         radio_station[guild_id] = False
    #         info_embed = discord.Embed(description=f"📻 Radio disabled.")

    #     message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    ### !intro #########################################################
    @commands.command(name='intro')
    @func.requires_author_perms()
    async def trigger_intro(self, ctx):
        """
        Toggles song intros for the radio station.

        Syntax:
            !intro
        """

        guild_str = str(guild.id)   # str() the guild id for json purposes
        
        config.settings[guild_str]['radio_intro'] = not config.settings[guild_str]['radio_intro']
        config.SaveSettings()

        info_embed = discord.Embed(description=f"📢 Radio intros {config.settings[guild_str]['radio_intro'] and 'enabled' or 'disabled'}.")
        await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    ### !pause #########################################################
    @commands.command(name='pause')
    @func.requires_author_perms()
    @func.requires_author_voice()
    @func.requires_bot_playing()
    @func.requires_bot_voice()
    async def trigger_pause(self, ctx, *, args=None):
        """
        Pauses the song playing.

        Syntax:
            !pause
        """

        allstates = self.settings[ctx.guild.id]
        
        allstates.pause_time = time.time()  # record when we paused
        ctx.guild.voice_client.pause()      # actually pause

        info_embed = discord.Embed(description=f"⏸️ Playback paused.")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    ### !play ##########################################################
    @commands.command(name='play')
    @func.requires_author_voice()
    async def trigger_play(self, ctx, *, args=None):
        """
        Adds a song to the queue.

        Syntax:
            !play [ <search query> | <link> ]
        """

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await JoinVoice(self.bot, ctx)

        if not args:    # no data provided
            raise func.err_syntax(); return
        
        song_type = args.startswith('https://') and 'link' or 'search'  # lazy filter to determine if it's a direct link or if we're searching

        info_embed = discord.Embed(description=f"Searching for {args}")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

        await asyncio.create_task(QueueSong(self.bot, args, song_type, False, message, guild.id, ctx.guild.voice_client))

    ### !playnext ######################################################
    @commands.command(name='playnext', aliases=['playbump'])
    @func.requires_author_perms()
    @func.requires_author_voice()
    async def trigger_playnext(self, ctx, *, args=None):
        """
        Adds a song to the top of the queue (no playlists).

        Syntax:
            !play [ <search query> | <link> ]

        Aliases:
            !playbump
        """

        is_playlist = ('&list=' in args or 'open.spotify.com/playlist' in args) and True or False
        
        if is_playlist:     # playlists not supported with playnext
            raise func.err_shuffle_no_playlist(); return
        
        if not args:    # no data provided
            raise func.err_syntax(); return

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await JoinVoice(self.bot, ctx)
        
        song_type = args.startswith('https://') and 'link' or 'search' # lazy filter to determine if it's a direct link or if we're searching

        info_embed = discord.Embed(description=f"Searching for {args}")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

        await asyncio.create_task(QueueSong(self.bot, args, song_type, True, message, ctx.guild.id, ctx.guild.voice_client))

    ### !queue #########################################################
    @commands.command(name='queue', aliases=['q', 'np', 'nowplaying', 'song'])
    async def trigger_queue(self, ctx):
        """
        Displays the song queue.

        Syntax:
            !queue

        Aliases:
            [ !q | !np | !nowplaying | !song ]
        """

        await self.GetQueue(ctx)

    ### !radio #########################################################
    @commands.command(name='radio', aliases=['dj'])
    @func.requires_author_perms()
    @func.requires_author_voice()
    async def trigger_radio(self, ctx, *, args=None):
        """
        Toggles endless mix mode.

        Syntax:
            !radio
            !radio <theme>

        Aliases:
            !dj
        """

        allstates = self.settings[ctx.guild.id]
        
        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await JoinVoice(self.bot, ctx)

        ### TODO: FIXME (with the rest of fusion)
        # # cancel out fusion
        # if guild_id in radio_fusions:
        #     radio_fusions.pop(guild_id)
        #     fuse_playlist.pop(guild_id)

        if args:
            allstates.radio_station = args
            info_embed = discord.Embed(description=f"📻 Radio enabled, theme: **{args}**.")
            
        elif allstates.radio_station == False:
            allstates.radio_station = "anything, im not picky" ### TODO: make this customizable per server
            info_embed = discord.Embed(description=f"📻 Radio enabled, theme: anything, im not picky.") ### TODO: variable to match above todo
        else:
            allstates.radio_station = False
            info_embed = discord.Embed(description=f"📻 Radio disabled.")
        
        await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())    

    ### !remove ########################################################
    @commands.command(name='remove')
    @func.requires_author_perms()
    @func.requires_queue()
    async def trigger_remove(self, ctx, args=None):
        """
        Removes the requested song from queue.

        Syntax:
            !remove <song number>
        """

        allstates = self.settings[ctx.guild.id]
        
        if not args or (args and not args.isdigit()):
            raise func.err_syntax(); return

        args = int(args)

        if not allstates.queue[(args - 1)]:
            raise func.err_queue_range(); return

        else:
            song = allstates.queue.pop((int(args) - 1))
            info_embed = discord.Embed(description=f"Removed **{song['title']}** from queue.")
            await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    ### !repeat ########################################################
    @commands.command(name='repeat', aliases=['loop'])
    @func.requires_author_perms()
    async def trigger_repeat(self, ctx):
        """
        Toggles song repeating.

        Syntax:
            !repeat

        Aliases:
            !loop
        """

        allstates = self.settings[ctx.guild.id]
        allstates.repeat = not allstates.repeat # change value to current opposite (True -> False)

        info_embed = discord.Embed(description=f"🔁 Repeat mode {allstates.repeat and 'enabled' or 'disabled'}.")
        await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    ### !resume ########################################################
    @commands.command(name='resume')
    @func.requires_author_perms()
    @func.requires_author_voice()
    @func.requires_bot_playing()
    @func.requires_bot_voice()
    async def trigger_resume(self, ctx, *, args=None):
        """
        Resume song playback.

        Syntax:
            !resume
        """

        allstates = self.settings[ctx.guild.id]
        
        allstates.start_time += (allstates.pause_time - allstates.start_time)   # update the start_time
        ctx.guild.voice_client.resume()     # actually resume playing

        info_embed = discord.Embed(description=f"🤘 Playback resumed.")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    ### !shuffle #######################################################
    @commands.command(name='shuffle')
    @func.requires_author_perms()
    async def trigger_shuffle(self, ctx):
        """
        Toggles playlist shuffle.

        Syntax:
            !shuffle
        """

        allstates.self.settings[ctx.guild.id]
        
        random.shuffle(allstates.queue)     # actually shuffles the queue
        allstates.shuffle = not allstates.shuffle   # update the shuffle variable

        info_embed = discord.Embed(description=f"🔀 Shuffle mode {allstates.shuffle and 'enabled' or 'disabled'}.")
        message = await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    ### !skip ##########################################################
    @commands.command(name='skip')
    @func.requires_author_perms()
    @func.requires_bot_playing()
    @func.requires_bot_voice()
    async def trigger_skip(self, ctx):
        """
        Skips the currently playing song.

        Syntax:
            !skip
        """

        allstates = self.settings[ctx.guild.id]
        
        await ctx.channel.send(f"Skipping {allstates.currently_playing['title']}.")

        ctx.guild.voice_client.stop()   # actually skip the song
        if allstates.repeat:
            await self.PlayNextSong(ctx.guild.id, ctx.guild.voice_client)


####################################################################
# function: FuseRadio(bot, ctx, new_theme)
# ----
# Fuse function to merge radio stations.
####################################################################
# async def FuseRadio(bot, ctx, new_theme=None):
#     guild_id = ctx.guild.id
#     fuse_playlist[guild_id] = []

#     # initial build
#     if guild_id not in radio_fusions:
#         radio_fusions[guild_id] = []
#         radio_fusions[guild_id].append(radio_station[guild_id])

#     # add the themes to the fuse, and clear out the old fuse station
#     if new_theme:
#         # add multiple fusions
#         if "|" in new_theme:
#             parts = new_theme.split("|")
#             for part in parts:
#                 if part.strip() not in radio_station[guild_id]:
#                     radio_fusions[guild_id].append(part.strip())
#         # add single fusion
#         else:
#             if new_theme not in radio_station[guild_id]:
#                 radio_fusions[guild_id].append(new_theme)

#     if radio_fusions[guild_id] == []:
#         return

#     # how many songs are we grabbing from each station
#     song_limit = math.ceil(50 / len(radio_fusions[guild_id]))

#     # build our new combined station
#     for station in radio_fusions[guild_id]:

#         # we don't know this station, build it
#         if station.lower() not in radio_playlists:
#             try:
#                 radio_playlists[station.lower()] = []
#                 response = await ChatGPT(
#                     bot,
#                     "Return only the information requested with no additional words or context.",
#                     f"Make a playlist of 50 songs (formatted as artist - song), themed around: {station}. Include similar artists and songs."
#                 )

#                 # filter out the goop
#                 parsed_response = response.split('\n')
#                 pattern = r'^\d+\.\s'

#                 for item in parsed_response:
#                     if re.match(pattern, item):
#                         parts = re.split(pattern, item, maxsplit=1)
#                         radio_playlists[station].append(parts[1].strip())
#                 SaveRadio()

#             except openai.ServiceUnavailableError:
#                 print("Service Unavailable :(")
#                 return
            
#         # add the station songs to the fuse station, and mix up the list
#         temp_pl = random.sample(radio_playlists[station.lower()], song_limit)
#         for song in temp_pl:
#             fuse_playlist[guild_id].append(song)
#         random.shuffle(fuse_playlist[guild_id])

#     return
    
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
                        await self.PlayNextSong(guild_id, voice_client)
                except Exception as e:
                    log_music.error(e)

            embed = discord.Embed(description=f"Added {playlist_length} tracks to queue.")
            await message.edit(content=None, embed=embed); return
        
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
                        await self.PlayNextSong(guild_id, voice_client)
                except Exception as e:
                    log_music.error(e)

            embed = discord.Embed(description=f"Added {playlist_length} tracks to queue.")
            await message.edit(content=None, embed=embed); return

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
                    await self.PlayNextSong(guild_id, voice_client)
            except Exception as e:
                log_music.error(e)

            embed = discord.Embed(description=f"Added {song[0]['title']} to queue.")
            await message.edit(content=None, embed=embed); return

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
                        await self.PlayNextSong(guild_id, voice_client)

                except Exception as e:
                    log_music.error(e)

            embed = discord.Embed(description=f"[3/3] Your ChatGPT playlist has been added to queue!")
            embed.add_field(name="Added:", value=f"{temp}", inline=False)

            await message.edit(content=None, embed=embed); return

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
                        await self.PlayNextSong(guild_id, voice_client)

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
                    await self.PlayNextSong(guild_id, voice_client); return

            except Exception as e:
                log_music.error(e)

    except Exception as e:
        log_music.error(e)

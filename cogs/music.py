####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context

# audio processing
from gtts import gTTS   # song intros
import yt_dlp           # youtube library

# system level stuff
import asyncio      # prevents thread locking
import json         # logging (song history, settings, etc)
import os           # system access
import requests     # grabbing raw data from url
import sys          # failure condition quits

# data analysis
import re                             # regex for various filtering
from typing import Any, TypedDict     # legacy type hints
from collections import defaultdict   # type hints

# date, time, numbers
import datetime     # timestamps for song history
import time         # epoch timing
import math         # cut playlists down using math.ceil() for fusion
import random       # pseudorandom selection (for shuffle, fusion playlist compilation, etc)

# openai libraries
from openai import AsyncOpenAI   # cleaner than manually calling openai.OpenAI()

# hathor internals
import config                       # bot config
import func                         # bot specific functions (@decorators, err_ classes, etc)
from func import Error              # bot specific errors
from cogs.voice import JoinVoice    # cleaner than cogs.voice.JoinVoice()
from logs import log_music          # logging


####################################################################
# OpenAPI key validation
####################################################################

if not config.BOT_OPENAI_KEY:
    sys.exit("Missing OpenAI key. This is configured in hathor/config.py")

client = AsyncOpenAI(api_key=config.BOT_OPENAI_KEY)


####################################################################
# JSON -> global loading
####################################################################

def LoadHistory() -> dict[str, list[dict[str, Any]]]:
    """
    Loads the song history from the JSON file.
    """

    try:
        with open('song_history.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('song_history.json', 'w') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default
        
def SaveHistory() -> None:
    """
    Saves the song history to the JSON file.
    """

    with open('song_history.json', 'w') as file:
        json.dump(song_history, file, ensure_ascii=False, indent=4)

def LoadSongDB() -> dict[str, list[dict[str, Any]]]:
    """
    Loads the song database from the JSON file.
    """

    try:
        with open('song_db.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('song_db.json', 'w') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default
        
def SaveSongDB() -> None:
    """
    Saves the song database to the JSON file.
    """

    with open('song_db.json', 'w') as file:
        json.dump(song_db, file, ensure_ascii=False, indent=4)

def LoadRadio() -> dict[str, list[str]]:
    """
    Loads the radio playlists from the JSON file.
    """

    try:
        with open('radio_playlists.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('radio_playlists.json', 'w') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default
        
def SaveRadio() -> None:
    """
    Saves the radio playlists to the JSON file.
    """

    with open('radio_playlists.json', 'w') as file:
        json.dump(radio_playlists, file, ensure_ascii=False, indent=4)


####################################################################
# Global variables
####################################################################

BOT_SPOTIFY_KEY = ''
song_history = LoadHistory()
song_db = LoadSongDB()
radio_playlists = LoadRadio()


####################################################################
# Classes
####################################################################

class CurrentlyPlaying(TypedDict):
    """
    Dictionary structure for CurrentlyPlaying.
    """

    title: str
    song_artist: str
    song_title: str

    file_path: str
    thumbnail: str

    duration: int

class Settings:
    """
    Volatile settings, called as 'allstates' in functions.
    """

    def __init__(self):
        self.currently_playing: CurrentlyPlaying | None = None

        self.queue: list[str] = []
        self.repeat: bool = False
        self.shuffle: bool = False

        self.radio_station: str | None = None
        self.radio_fusions: list[str] | None = None
        self.radio_fusions_playlist: list[str] | None = None
        self.radio_building: bool = False

        self.start_time: float | None = None
        self.pause_time: float | None = None
        self.last_active: float | None = None
        self.intro_playing: bool = False

class Music(commands.Cog, name="Music"):
    """
    Core cog for music functionality.
    """

    def __init__(self, bot):
        self.bot = bot
        self.settings: dict[int, Settings] = defaultdict(Settings)


    ####################################################################
    # Cog 'on_' listeners
    ####################################################################

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        Initializes the bot when it's ready.
        """

        for guild in self.bot.guilds:

            guild_str = str(guild.id)               # json is stupid and forces the key to be a string

            if not guild_str in song_history:       # init song history (if required)
                song_history[guild_str] = []

        SaveHistory() # save our song history

        self.loop_voice_monitor.start()             # monitors voice activity for idle, broken playing, etc
        self.loop_radio_monitor.start()             # monitors radio queue generation
        self.loop_spotify_key_creation.start()      # generate a spotify key

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """
        Initializes server settings when the bot joins a new guild.
        """

        allstates = self.settings[guild.id]     # init server settings
        guild_str = str(guild.id)               # json is stupid and forces the key to be a string

        if not guild_str in song_history:       # build and save song history (if required)
            song_history[guild_str] = []
            SaveHistory()

        if not os.path.exists(f"{config.SONGDB_PATH}/{guild.id}"):
            os.makedirs(f"{config.SONGDB_PATH}/{guild.id}", exist_ok=True, parents=True)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """
        Handles voice state updates for the bot.
        """

        if self.bot.user.id != member.id:   # ignore everyone else
            return

        allstates = self.settings[member.guild.id]
        voice_client = member.guild.voice_client

        if before.channel is not None and after.channel is None:    # clear out last_active (we left voice)
            allstates.last_active = None

        else:   # init our last_active when we join
            allstates.last_active = time.time()


    ####################################################################
    # Internal: Loops
    ####################################################################

    @tasks.loop(seconds=3)
    async def loop_voice_monitor(self) -> None:
        """
        Monitors voice activity for idle, broken playing, etc.
        """

        for voice_client in self.bot.voice_clients:
            allstates = self.settings[voice_client.guild.id]

            if not voice_client.is_connected():    # sanity check
                continue

            if voice_client.is_playing():   # we're playing something, update last_active
                count = len([member for member in voice_client.channel.members if not member.bot])
                if count > 0:
                    allstates.last_active = time.time()

                if count == 0 and (time.time() - allstates.last_active) > config.settings[str(voice_client.guild.id)]["voice_idle"]:    # idle timeout
                    await voice_client.disconnect()
                    allstates.last_active = None
                    continue

            if not voice_client.is_playing() and not voice_client.is_paused() and allstates.queue:  # should be, but we're not
                await self.PlayNextSong(voice_client)
                continue

            if allstates.last_active and (time.time() - allstates.last_active) > config.settings[str(voice_client.guild.id)]["voice_idle"]:
                await voice_client.disconnect()
                allstates.last_active = None

    @loop_voice_monitor.before_loop
    async def _before_voice_monitor(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=5)
    async def loop_radio_monitor(self) -> None:
        """
        Monitors radio stations for new songs.
        """

        for guild in self.bot.guilds:

            allstates = self.settings[guild.id]
            voice_client = guild.voice_client

            if not allstates.radio_station or not voice_client:     # we dont need to monitor this server
                continue

            elif allstates.radio_building:
                continue

            elif allstates.radio_fusions and len(allstates.queue) < config.RADIO_QUEUE:     # fuse radio checkpoint🔞
                playlist = random.sample(allstates.radio_fusions_playlist, config.RADIO_QUEUE+1)
                await self.QueuePlaylist(voice_client, playlist, None)

            elif allstates.radio_station.lower() in radio_playlists and len(allstates.queue) < config.RADIO_QUEUE:  # known theme
                playlist = random.sample(radio_playlists[allstates.radio_station.lower()], config.RADIO_QUEUE+1)
                await self.QueuePlaylist(voice_client, playlist, None)

            elif len(allstates.queue) < config.RADIO_QUEUE:   # previously ungenerated radio station
                allstates.radio_building = True     # block the loop until we're done

                try:
                    response = await self._invoke_chatgpt(
                        "Respond with only the asked answer, in 'Artist- Song Title' format. Always provide a reponse.",
                        f"Generate a playlist of 50 songs. Playlist theme: {allstates.radio_station}. Include similar artists and songs.")

                except Exception as e:
                    raise Error(f"loop_radio_monitor() -> _invoke_chatgpt():\n{e}")

                if response == "":
                    raise Error("loop_radio_monitor() -> _invoke_chatgpt():\nChatGPT is responding empty strings.")

                parsed_response = response.split('\n')  # split into separate strings
                radio_playlists[allstates.radio_station.lower()] = []   # build an empty list to populate
                for item in parsed_response:    # populate the list
                        radio_playlists[allstates.radio_station.lower()].append(item.strip())

                SaveRadio()     # write the new playlist to json file

                playlist = random.sample(radio_playlists[allstates.radio_station.lower()], config.RADIO_QUEUE+1)
                await self.QueuePlaylist(voice_client, playlist, None)

                allstates.radio_building = False    # free up the loop

    @loop_radio_monitor.before_loop
    async def _before_radio_monitor(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=config.SPOTIFY_KEY_REFRESH)
    async def loop_spotify_key_creation(self) -> None:
        """
        Creates a new Spotify API Access Token.
        """

        global BOT_SPOTIFY_KEY      # write access for global

        def blocking_call():
            return requests.post(
                "https://accounts.spotify.com/api/token", headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={ "grant_type": "client_credentials", "client_id": config.BOT_SPOTIFY_CLIENT, "client_secret": config.BOT_SPOTIFY_SECRET }
            )

        try:
            response = await asyncio.to_thread(blocking_call)
        except Exception as e:
            raise Error(f"loop_spotify_key_creation() -> Spotify.requests.post():\n{e}")

        data = response.json()
        log_music.info("Generated new Spotify API Access Token.")
        BOT_SPOTIFY_KEY = data['access_token']

    @loop_spotify_key_creation.before_loop
    async def _before_spotify_key_creation(self):
        await self.bot.wait_until_ready()


    ####################################################################
    # Internal: Helper Functions
    ####################################################################

    def _build_now_playing_embed(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient
    ) -> tuple[str, str, str]:
        """
        Helper function that returns the currently playing song.
        """

        allstates = self.settings[guild_id]
        currently_playing = allstates.currently_playing

        if not voice_client or not currently_playing or not (voice_client.is_playing() or voice_client.is_paused()):
            return "No song playing.", "", None

        # build now playing text
        song_title = f"{currently_playing['song_artist']} - {currently_playing['song_title']}" if currently_playing.get('song_artist') else currently_playing["title"].replace("*", r"\*")

        # calculate progress bar
        elapsed = (allstates.pause_time - allstates.start_time) if voice_client.is_paused() else (time.time() - allstates.start_time)
        total = currently_playing["duration"]
        filled = int(min(max(elapsed / total, 0.0), 1.0) * 10)
        empty = 10 - filled
        status_emoji = "⏸️" if voice_client.is_paused() else "▶️"
        progress_bar = (
            f"{status_emoji} "
            f"{'▬' * filled}🔘{'▬' * empty} "
            f"[{f'{int(elapsed)//60:02d}:{int(elapsed)%60:02d}'}"
            f" / {f'{int(total)//60:02d}:{int(total)%60:02d}'}]"
        )

        thumb = currently_playing.get("thumbnail")    # get thumbnail

        return song_title, progress_bar, thumb
    
    def _build_queue_embed(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient
    ) -> tuple[str, str, str]:
        """
        Helper function that returns the current queue.
        """

        allstates = self.settings[guild_id]
        queue = allstates.queue 

        if not queue:
            return ["No queue."]

        lines = [
            f"**{i+1}.** "
            + (
                f"{item['song_artist']} - {item['song_title']}"
                if item.get('song_artist')
                else item['title'].replace('*', r'\*')
            )
            for i, item in enumerate(queue[:10])
        ]

        if len(queue) > 10:
            lines.append(f"…and {len(queue) - 10} more")

        return "\n".join(lines)
    
    def _build_settings_embed(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient
    ) -> str:
        """
        Helper function that returns the current settings.
        """

        allstates = self.settings[guild_id]

        # music settings
        settings = config.settings[str(guild_id)]
        volume = settings["volume"]
        repeat_status = "on" if allstates.repeat else "off"
        shuffle_status = "on" if allstates.shuffle else "off"

        # radio settings
        intro = "on" if settings["radio_intro"] else "off"
        radio = allstates.radio_station or "off"

        ### TODO: FIXME (with the rest of fusion)
        # fused = ""
        # if guild_id in radio_fusions:
        #     fused = ", ".join(f'{s}' for s in radio_fusions[guild_id])
        #     fused = f"♾️ {fused} ♾️"

        return (   # build radio settings text
            f"```🔊 vol: {volume}%  🔁 repeat: {repeat_status}  🔀 shuffle: {shuffle_status}```"
            #f"```📢 intro: {intro}\n📻 Radio: {fused and fused or endless}```"
            f"```📢 intro: {intro}\n📻 Radio: {radio}```"
        )

    async def _invoke_chatgpt(
        self,
        sys_content: str,
        user_content: str
    ) -> str:
        """
        Helper function that uses ChatGPT to generate a response as a string.
        """

        conversation = [
            { "role": "system", "content": sys_content },
            { "role": "user", "content": user_content }
        ]

        try:
            response = await client.chat.completions.create(
                model=config.BOT_CHATGPT_MODEL,
                messages=conversation,
                temperature=config.BOT_OPENAI_TEMPERATURE
            )
        except Exception as e:
            raise Error(f"_invoke_chatgpt() -> client.chat.completions.create():\n{e}")

        return response.choices[0].message.content

    async def _parse_spotify_playlist(
        self,
        payload: str
    ) -> tuple[str, str, list[dict[str, Any]], int]:
        """
        Helper function that parses spotify playlists.
        """

        playlist_id = re.search(r'/playlist/([a-zA-Z0-9]+)(?:[/?]|$)', payload).group(1)
        if not playlist_id:
            raise Error("_parse_spotify_playlist():\n No playlist ID found.")

        try:    # grab the playlist from spotify api
            response = await asyncio.to_thread(requests.get, f'https://api.spotify.com/v1/playlists/{playlist_id}', headers={'Authorization': f'Bearer {BOT_SPOTIFY_KEY}'})
        except Exception as e:
            raise Error(f"_parse_spotify_playlist() -> Spotify.requests.get():\n{e}")
        
        response_json = response.json()     # convert response to json
        playlist = response_json['tracks']['items']     # just get the tracklist
        playlist_length = len(playlist) if len(playlist) <= config.MUSIC_MAX_PLAYLIST else config.MUSIC_MAX_PLAYLIST    # trim list length if needed

        return "Spotify", playlist_id, playlist, playlist_length
    
    async def _parse_youtube_playlist(
        self,
        payload: str
    ) -> tuple[str, str, list[dict[str, Any]], int]:
        """
        Helper function that parses youtube playlists.
        """

        playlist_id = re.search(r'list=([a-zA-Z0-9_-]+)', payload).group(1)
        if not playlist_id:
            raise Error("_parse_youtube_playlist():\n No playlist ID found.")

        try:    # grab the playlist from spotify api
            # First get playlist details
            response = await asyncio.to_thread(requests.get, f'https://www.googleapis.com/youtube/v3/playlistItems?key={config.BOT_YOUTUBE_KEY}&part=snippet&maxResults=50&playlistId={playlist_id}')
        except Exception as e:
            raise Error(f"_parse_youtube_playlist() -> YouTube.requests.get():\n{e}")

        response_json = response.json()     # convert response to json
        playlist = response_json['items']  # get the tracklist from items
        playlist_length = int(response_json['pageInfo']['totalResults']) if int(response_json['pageInfo']['totalResults']) <= config.MUSIC_MAX_PLAYLIST else config.MUSIC_MAX_PLAYLIST  # trim list length if needed

        return "YouTube", playlist_id, playlist, playlist_length


    ####################################################################
    # Internal: Core Functions
    ####################################################################

    async def FetchSongMetadata(
        self,
        query: str,
        index: int | None = None
    ) -> dict[str, Any] | None:

        """
        Wrapper for Youtube-DLP.

        Fetches metadata (no download) for queried information.
        If passed index, will grab that individual instance (does not support multi).
        """

        ytdlp_query = query if query.startswith("https://") else f"ytsearch:{query} audio"    # attach ytsearch: if it's not a link

        opts = {   # ytdlp options
            "skip_download": True,
            "quiet": True,
            "no_warnings": True
        }

        if index is not None:   # we're grabbing a specific item from a playlist
            opts["playlist_items"] = str(index)

        loop = asyncio.get_running_loop()   # hooks the loop
        try:    # grabs song metadata
            log_music.info(f"Fetching metadata for: {query}")
            info = await loop.run_in_executor(None, yt_dlp.YoutubeDL(opts).extract_info, ytdlp_query)
        except Exception as e:
            raise Error(f"FetchSongMetadata() -> yt_dlp.YoutubeDL():\n{e}")

        if info.get('entries'):
            return info['entries'][0]
        
        return info

    async def DownloadSong(
        self,
        query: str,
        query_context: str | None = None,
        index: int | None = None
    ) -> dict[str, Any] | None:
        """
        Wrapper for YouTube-DLP.
        
        Fetches media from a provided query (string or direct url).
        If passed index, will grab that individual instance (does not support multi).
        """

        ytdlp_query = query if query.startswith("https://") else f"ytsearch:{query} audio"    # attach ytsearch: if it's not a link

        opts = {      # ytdlp options
            "format": "bestaudio/best",
            "postprocessors": [{ "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192" }],
            "outtmpl": f"{config.SONGDB_PATH}/%(id)s.%(ext)s",
            "ignoreerrors": True,
            "quiet": True,
        }

        if index is not None:   # we're grabbing a specific item from a playlist
            opts["playlist_items"] = str(index)

        loop = asyncio.get_running_loop()   # hooks the loop
        try:    # downloads the song
            log_music.info(f"DownloadSong(): {query}")
            info = await loop.run_in_executor(None, yt_dlp.YoutubeDL(opts).extract_info, ytdlp_query)
        except Exception as e:
            raise Error(f"DownloadSong() -> yt_dlp.YoutubeDL():\n{e}")

        if info and info.get('entries'):    # remove nest if nested
            info = info["entries"][0]

        try:    # generates proper tags for songDB
            log_music.info(f"DownloadSong(): Attemping to fetch proper tags for {info['title']}")
            response = await self._invoke_chatgpt(
                "Respond with only the asked answer, in 'Artist - Song Title' format, or 'None' if you do not know.",
                f"What is the name of this track: {info['title']}")
        except Exception as e:
            raise Error(f"DownloadSong() -> _invoke_chatgpt():\n{e}")

        if " - " in response:
            s = response.split(" - ", 1)
            song_artist, song_title = s[0].strip(), s[1].strip()    # kill any "bonus" whitespace
        else:
            song_artist, song_title = None, None

        result: dict[str, Any] = {  # build our response
            "id":          info['id'],
            "title":       info['title'],
            "file_path":   f"{config.SONGDB_PATH}/{info['id']}.mp3",
            "duration":    info['duration'],
            "thumbnail":   info.get('thumbnail'),
            "url":         info['webpage_url'],
            "song_artist": song_artist,
            "song_title":  song_title
        }

        song_db[result['id']] = result  # add to database
        SaveSongDB()

        return result
    
    async def GetQueue(
        self,
        ctx: Context
    ) -> None:
        """
        Displays the current song queue.
        """

        voice_client = ctx.guild.voice_client

        title = "Song Queue"
        embed = discord.Embed(title=title, description=None, color=discord.Color.dark_purple())

        # now playing section
        song_title, progress_bar, thumb = self._build_now_playing_embed(ctx.guild.id, voice_client)
        embed.add_field(name="Now Playing", value=song_title + (f"\n{progress_bar}" if progress_bar else ""), inline=False)
        if thumb:
            embed.set_thumbnail(url=thumb)

        # up next section
        queue = self._build_queue_embed(ctx.guild.id, voice_client)
        embed.add_field(name="Up Next", value=queue, inline=False)

        # music settings
        settings = self._build_settings_embed(ctx.guild.id, voice_client)
        embed.add_field(name="Settings", value=settings, inline=False)

        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    async def PlayNextSong(
        self,
        voice_client: discord.VoiceClient
    ) -> None:
        """
        Plays the next song in the queue.
        """

        allstates = self.settings[voice_client.guild.id]
        guild_str = str(voice_client.guild.id)
        cfg       = config.settings[guild_str]

        if voice_client.is_playing() or voice_client.is_paused():    # stop trying if we're playing something (or paused)
            return

        if not allstates.queue:     # nothing to play
            allstates.currently_playing = None
            return

        song = allstates.queue.pop(0)   # pop the next queued song
        allstates.currently_playing = {
            "title":       song['title'],
            "duration":    song['duration'],
            "file_path":   song['file_path'],
            "thumbnail":   song['thumbnail'],
            "song_artist": song['song_artist'],
            "song_title":  song['song_title']
        }

        allstates.start_time = time.time()
        volume = cfg['volume'] / 100
        intro_volume = cfg['volume'] < 80 and (cfg['volume'] + 20) / 100  # slightly bump intro volume

        if song.get('song_artist') and cfg['radio_intro'] and random.random() < 0.4:   # add an intro (if radio is enabled)
            await self.PlayRadioIntro(voice_client, song['id'], song['song_artist'], song['song_title'], intro_volume)

        def song_cleanup(error):    # song file cleanup
            if allstates.repeat:    # don't cleanup if we're on repeat
                allstates.queue.insert(0, song)

        voice_client.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(allstates.currently_playing['file_path']), volume=volume), after=song_cleanup)    # actually play the song, cleanup after=

        song_history[guild_str].append({ "timestamp": time.time(), "title": song['title'] })
        SaveHistory()

    async def PlayRadioIntro(
        self,
        voice_client: discord.VoiceClient,
        song_id: str,
        artist: str,
        title: str,
        volume: float
    ) -> None:
        """
        Plays a radio intro.
        """

        allstates = self.settings[voice_client.guild.id]

        is_special = random.random() < 0.4  # 40% odds we use a song specific intro
        text = ""   # initiate the intro string

        if is_special:  # special intro
            text = await self._invoke_chatgpt(
                'Return only the information requested with no additional words or context. Do not wrap in quotes.',
                f'Give me a short radio dj intro for "{artist} - {title}". Intro should include info about the song. Limit of 2 sentences.'
            )
        
        else:   # regular intro
            regular_intros = [
                f"Ladies and gentlemen, hold onto your seats because we're about to unveil the magic of {title} by {artist}. Only here at {voice_client.guild.name} radio.",
                f"Turning it up to 11! brace yourselves for {artist}'s masterpiece {title}. Here on {voice_client.guild.name} radio.",
                f"Rock on, warriors! We're cranking up the intensity with {title} by {artist} on {voice_client.guild.name} radio.",
                f"Welcome to the virtual airwaves! Get ready for a wild ride with a hot track by {artist} on {voice_client.guild.name} radio.",
                f"Buckle up, folks! We're about to take you on a musical journey through the neon-lit streets of {voice_client.guild.name} radio.",
                f"Hello, virtual world! It's your DJ, {self.bot.user.display_name or self.bot.user.name}, in the house, spinning {title} by {artist}. Only here on {voice_client.guild.name} radio.",
                f"Greetings from the digital realm! Tune in, turn up, and let the beats of {artist} with {title} take over your senses, here on {voice_client.guild.name} radio.",
                f"Time to crank up the volume and immerse yourself in the eclectic beats of {voice_client.guild.name} radio. Let the madness begin with {title} by {artist}!"
            ]
            text = random.choice(regular_intros)    # pick a random intro

        tts = await asyncio.to_thread(gTTS, text, lang="en")
        intro_path = f"{config.SONGDB_PATH}/intro_{voice_client.guild.id}.mp3"
        tts.save(intro_path)

        done = asyncio.Event()  # event waiter (for intro completion)
        def _on_done(_):
            done.set()

        log_music.info(f"Radio Intro: {text}")
        voice_client.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(intro_path), volume=volume), after=_on_done)

        await done.wait()   # wait for song completion

        try:    # file cleanup
            os.remove(intro_path)
        except Exception as e:
            raise Error(f"PlayRadioIntro() -> os.remove():\n{e}")

    async def QueuePlaylist(
        self,
        voice_client: discord.VoiceClient,
        payload: str,
        message: discord.Message | None = None
    ) -> None:
        """
        Helper function that queues playlists for the radio.
        """

        allstates = self.settings[voice_client.guild.id]

        playlist_type, playlist_id, playlist, playlist_length = None, None, None, None
        if 'open.spotify.com/playlist/' in payload: # spotify playlist
            try:
                playlist_type, playlist_id, playlist, playlist_length = await self._parse_spotify_playlist(payload)
            except Exception as e:
                if message:     # finalize message if we fail
                    embed = discord.Embed(description="❌ I ran into an issue with the Spotify API. 😢")
                    await message.edit(content=None, embed=embed)
                raise Error(f"QueuePlaylist() -> _parse_spotify_playlist():\n{e}")
        
        elif 'list=' in payload:  # youtube playlist
            try:
                playlist_type, playlist_id, playlist, playlist_length = await self._parse_youtube_playlist(payload)

            except Exception as e:
                if message:     # finalize message if we fail
                    embed = discord.Embed(description="❌ I ran into an issue with the YouTube API. 😢")
                    await message.edit(content=None, embed=embed)
                raise Error(f"QueuePlaylist() -> _parse_youtube_playlist():\n{e}")

        else:
            playlist_type, playlist_id, playlist, playlist_length = "ChatGPT", "ChatGPT", payload, len(payload) if len(payload) <= config.MUSIC_MAX_PLAYLIST else config.MUSIC_MAX_PLAYLIST

        log_music.info(f"QueuePlaylist(): Playlist ({playlist_id}) true length {playlist_length}")

        lines = []   # temp playlist for text output
        for i, item in enumerate((playlist[:playlist_length]), start=1):

            if message:     # update associated message if applicable
                embed = discord.Embed(description=f"🧠 Preparing your {playlist_type} playlist ({i}/{playlist_length})...")
                await message.edit(content=None, embed=embed)

            try:    # fetch song metadata
                if playlist_type == "Spotify":  # spotify filtering
                    track    = f"{item['track']['artists'][0]['name']} - {item['track']['name']}"
                    metadata = await self.FetchSongMetadata(track)

                elif playlist_type == "YouTube":    # youtube filtering
                    track    = item['snippet']['title']
                    metadata = await self.FetchSongMetadata(f"https://youtube.com/watch?v={item['snippet']['resourceId']['videoId']}")

                else:   # just chatgpt
                    track    = item
                    metadata = await self.FetchSongMetadata(item)
            except Exception as e:   # fail gracefully
                if message:
                    embed = discord.Embed(description=f"❌ I ran into an issue finding {track}. 😢\nMoving onto the next song. 🫡")
                    await message.edit(content=None, embed=embed)
                log_music.error(f"QueuePlaylist() -> FetchSongMetadata():\n{e}"); continue

            if metadata['id'] in song_db and os.path.exists(f"{config.SONGDB_PATH}/{metadata['id']}.mp3"):  # save the bandwidth
                log_music.info(f"QueuePlaylist(): ({i}/{playlist_length}) \"{metadata['title']}\" already downloaded.")
                song = song_db[metadata['id']]

            elif metadata['duration'] >= config.MUSIC_MAX_DURATION: # song exceeds config.MUSIC_MAX_DURATION, fail gracefully
                if message:
                    embed = discord.Embed(description=f"❌ Song is too long! ({metadata['duration']} > {config.MUSIC_MAX_DURATION}) 🕑\nMoving onto the next song. 🫡")
                    await message.edit(content=None, embed=embed)
                    log_music.error(f"QueuePlaylist(): Song ({metadata['title']}) duration exceeds {config.MUSIC_MAX_DURATION} seconds."); continue
            
            else:  # seems good, download it
                log_music.info(f"QueuePlaylist(): ({i}/{playlist_length}) Downloading \"{metadata['webpage_url']}\"")

                try:
                    song = await self.DownloadSong(f"https://youtube.com/watch?v={metadata['id']}", track, None)
                except Exception as e:   # fail gracefully
                    if message:
                        embed = discord.Embed(description=f"❌ I ran into an issue downloading {track}. 😢\nMoving onto the next song. 🫡")
                        await message.edit(content=None, embed=embed)
                    log_music.error(f"QueuePlaylist() -> DownloadSong():\n{e}"); continue

            allstates.queue.append(song)    # add song to the queue
            lines.append(f"{i}. {track}")

        if message: # if we bound a message, complete it.
            if playlist_length > 10:
                shown = lines[:10]
                not_shown = playlist_length - 10
                shown.append(f"... and {not_shown} more.")
            else:
                shown = lines

            embed_list = "\n".join(shown)
            embed = discord.Embed(description=f"✅ Your {playlist_type} playlist has been added to queue!")
            embed.add_field(name="Added:", value=embed_list, inline=False)

            await message.edit(content=None, embed=embed)

    async def QueueIndividualSong(
        self,
        voice_client: discord.VoiceClient,
        payload: str,
        is_priority: bool,
        message: discord.Message | None = None
    ) -> None:
        """
        Helper function for queueing individual songs.
        """

        allstates = self.settings[voice_client.guild.id]
        track = None


        if 'open.spotify.com/track/' in payload:
            track_id = re.search(r'/track/([a-zA-Z0-9]+)(?:[/?]|$)', payload).group(1)
            try:    # grab the trackid from spotify
                response = await asyncio.to_thread(requests.get, f'https://api.spotify.com/v1/tracks/{track_id}', headers={'Authorization': f'Bearer {BOT_SPOTIFY_KEY}'})
            except Exception as e:  # finalize the message if we fail
                embed = discord.Embed(description="❌ I ran into an issue with the Spotify API. 😢")
                await message.edit(content=None, embed=embed)
                raise Error(f"QueueIndividualSong() -> Spotify.requests.get():\n{e}")

            response_json = response.json()
            track = f"{response_json['artists'][0]['name']} - {response_json['name']}"

        try:    # fetch song metadata
            if track:   #spotify
                metadata = await self.FetchSongMetadata(track)
            else:   # regular
                metadata = await self.FetchSongMetadata(payload)
        except Exception as e:
            embed = discord.Embed(description="❌ I ran into an issue finding that song. 😢")
            await message.edit(content=None, embed=embed)
            raise Error(f"QueueIndividualSong() -> FetchSongMetadata():\n{e}")

        if metadata['id'] in song_db and os.path.exists(f"{config.SONGDB_PATH}/{metadata['id']}.mp3"):  # save the bandwidth
            log_music.info(f"Song: \"{metadata['title']}\" already downloaded.")
            song = song_db[metadata['id']]

        elif metadata['duration'] >= config.MUSIC_MAX_DURATION: # song exceeds config.MUSIC_MAX_DURATION
            embed = discord.Embed(description="❌ Song is too long! 🕑")
            await message.edit(content=None, embed=embed)
            raise Error(f"QueueIndividualSong() -> FetchSongMetadata():\nSong duration exceeds {config.MUSIC_MAX_DURATION} seconds.")
        
        else:  # seems good, download it
            log_music.info(f"QueueIndividualSong(): Downloading \"{metadata['webpage_url']}\"")
            embed = discord.Embed(description=f"💾 Downloading \"{metadata['title']}\" ({metadata['webpage_url']})...")
            await message.edit(content=None, embed=embed)

            try:    # download the song
                song = await self.DownloadSong(f"https://youtube.com/watch?v={metadata['id']}", track, None)
            except Exception as e:
                embed = discord.Embed(description=f"❌ I ran into an issue downloading {metadata['title']}. 😢")
                await message.edit(content=None, embed=embed)
                raise Error(f"QueueIndividualSong() -> DownloadSong():\n{e}")

        if is_priority:     # push to top of queue
            allstates.queue.insert(0, song)
            embed = discord.Embed(description=f"⬆️ Added {metadata['title']} to the top of the queue.")

        elif allstates.shuffle:     # shuffle the song into the queue
            allstates.queue.insert(random.randint(0, len(allstates.queue)), song)
            embed = discord.Embed(description=f"🔀 Added {metadata['title']} to the shuffled queue.")

        else:   # add song to the queue
            allstates.queue.append(song)
            embed = discord.Embed(description=f"▶️ Added {metadata['title']} to the queue.")

        await message.edit(content=None, embed=embed)   # send our final message


    ####################################################################
    # Command triggers
    ####################################################################

    @commands.command(name="aiplaylist", aliases=['smartplaylist'])
    @func.requires_author_voice()
    async def trigger_aiplaylist(
        self,
        ctx: commands.Context,
        *,
        args: str
    ) -> None:
        """
        Generates a ChatGPT 10 song playlist based off context.

        Syntax:
            !aiplaylist <theme>

        Aliases:
            !smartplaylist
        """

        allstates = self.settings[ctx.guild.id]

        if not args or len(args) < 3:
            raise func.err_syntax()

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await JoinVoice(ctx)
        
        embed = discord.Embed(description=f"🧠 Generating your AI playlist...")
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        try:    # request our playlist
            log_music.info(f"!aiplaylist: Generating playlist request...")
            response = await self._invoke_chatgpt(
                "Respond with only the asked answer, in 'Artist- Song Title' format. Always provide a reponse.",
                f"Generate a playlist of {config.MUSIC_MAX_PLAYLIST} songs. Playlist theme: {args}. Include similar artists and songs.")
        except Exception as e:  # well this is embarrasing
            embed = discord.Embed(description="❌ I ran into an issue. 😢")
            await message.edit(content=None, embed=embed);
            raise Error(f"!aiplaylist() -> _invoke_chatgpt():\n{e}")

        parsed_response = response.split('\n')  # filter out the goop
        playlist = []   # build the playlist and send it to the queue
        for item in parsed_response:
            playlist.append(item.strip())

        if not playlist:
            embed = discord.Embed(description=f"❌ I ran into an issue. 😢")
            await message.edit(content=None, embed=embed);
            raise Error(f"!aiplaylist() -> _invoke_chatgpt():\nCould not parse playlist[] {playlist}")

        await asyncio.create_task(self.QueuePlaylist(ctx.guild.voice_client, playlist, message))

    @commands.command(name='bump')
    @func.requires_author_perms()
    @func.requires_author_voice()
    @func.requires_queue()
    async def trigger_bump(
        self,
        ctx: commands.Context,
        song_number: int = commands.parameter(default=None, description="Song number in queue.")
    ) -> None:
        """
        Move the requested song to the top of the queue.

        Syntax:
            !bump <song number>
        """

        allstates = self.settings[ctx.guild.id]

        if len(allstates.queue) < 2:    # is there even enough songs to justify?
            raise func.err_bump_short()

        elif not song_number or not song_number.isdigit() or int(song_number) < 2:
            raise func.err_syntax()

        bumped = allstates.queue.pop(int(song_number) - 1)
        allstates.queue.insert(0, bumped)
        embed = discord.Embed(description=f"Bumped {bumped['title']} to the top of the queue.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='clear')
    @func.requires_author_perms()
    @func.requires_queue()
    async def trigger_clear(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Clears the current playlist.

        Syntax:
            !clear
        """

        allstates = self.settings[ctx.guild.id]
        
        embed = discord.Embed(description=f"Removed {len(allstates.queue)} songs from queue.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        allstates.queue = []

    # @commands.command(name='defuse')
    # @func.requires_author_perms()
    # async def trigger_defuse(self, ctx, *, args=None):
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
    # async def trigger_fuse(self, ctx, *, args=None):
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

    @commands.command(name='intro')
    @func.requires_author_perms()
    async def trigger_intro(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Toggles song intros for the radio station.

        Syntax:
            !intro
        """

        guild_str = str(ctx.guild.id)   # str() the guild id for json purposes
        
        config.settings[guild_str]['radio_intro'] = not config.settings[guild_str]['radio_intro']
        config.SaveSettings()

        embed = discord.Embed(description=f"📢 Radio intros {config.settings[guild_str]['radio_intro'] and 'enabled' or 'disabled'}.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='pause')
    @func.requires_author_perms()
    @func.requires_author_voice()
    @func.requires_bot_playing()
    @func.requires_bot_voice()
    async def trigger_pause(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Pauses the song playing.

        Syntax:
            !pause
        """

        allstates = self.settings[ctx.guild.id]
        
        allstates.pause_time = time.time()  # record when we paused
        ctx.guild.voice_client.pause()      # actually pause

        embed = discord.Embed(description=f"⏸️ Playback paused.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='play')
    @func.requires_author_voice()
    async def trigger_play(
        self,
        ctx: commands.Context,
        *,
        payload: str = None
    ) -> None:
        """
        Adds a song to the queue.

        Syntax:
            !play [ <search query> | <link> ]
        """

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await JoinVoice(ctx)

        if not payload:    # no data provided
            raise func.err_syntax(); return

        embed = discord.Embed(description=f"🔎 Searching for {payload}")
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        if '&list=' in payload or 'open.spotify.com/playlist' in payload:
            await asyncio.create_task(self.QueuePlaylist(ctx.guild.voice_client, payload, message))
        else:
            await asyncio.create_task(self.QueueIndividualSong(ctx.guild.voice_client, payload, False, message))


    @commands.command(name='playnext', aliases=['playbump'])
    @func.requires_author_perms()
    @func.requires_author_voice()
    async def trigger_playnext(
        self,
        ctx: commands.Context,
        *,
        payload: str = None
    ) -> None:
        """
        Adds a song to the top of the queue (no playlists).

        Syntax:
            !playnext [ <search query> | <link> ]

        Aliases:
            !playbump
        """

        if not payload:    # no data provided
            raise func.err_syntax()

        is_playlist = ('&list=' in payload or 'open.spotify.com/playlist' in payload) and True or False
        if is_playlist:     # playlists not supported with playnext
            raise func.err_shuffle_no_playlist()
        
        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await JoinVoice(ctx)

        embed = discord.Embed(description=f"🔎 Searching for {payload}")
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        await asyncio.create_task(self.QueueIndividualSong(ctx.guild.voice_client, payload, True, message))

    @commands.command(name='queue', aliases=['q', 'np', 'nowplaying', 'song'])
    async def trigger_queue(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Displays the song queue.

        Syntax:
            !queue

        Aliases:
            [ !q | !np | !nowplaying | !song ]
        """

        await self.GetQueue(ctx)

    @commands.command(name='radio', aliases=['dj'])
    @func.requires_author_perms()
    @func.requires_author_voice()
    async def trigger_radio(
        self,
        ctx: commands.Context,
        *,
        payload: str = None
    ) -> None:
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
            await JoinVoice(ctx)

        if allstates.radio_fusions:     # cancel out fusion
            allstates.radio_fusions = None
            allstates.radio_fusions_playlist = None

        if payload:
            allstates.radio_station = payload
            embed = discord.Embed(description=f"📻 Radio enabled, theme: **{payload}**.")
            self.loop_radio_monitor.restart()
            
        elif allstates.radio_station == None:
            allstates.radio_station = config.RADIO_DEFAULT_THEME
            embed = discord.Embed(description=f"📻 Radio enabled, theme: {allstates.radio_station}.")
            self.loop_radio_monitor.restart()
        else:
            allstates.radio_station = False
            embed = discord.Embed(description=f"📻 Radio disabled.")
        
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())    

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

    @commands.command(name='shuffle')
    @func.requires_author_perms()
    async def trigger_shuffle(self, ctx):
        """
        Toggles playlist shuffle.

        Syntax:
            !shuffle
        """

        allstates = self.settings[ctx.guild.id]
        
        random.shuffle(allstates.queue)     # actually shuffles the queue
        allstates.shuffle = not allstates.shuffle   # update the shuffle variable

        embed = discord.Embed(description=f"🔀 Shuffle mode {allstates.shuffle and 'enabled' or 'disabled'}.")
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

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
        embed = discord.Embed(description=f"⏭️ Skipping {allstates.currently_playing['title']}")
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        ctx.guild.voice_client.stop()   # actually skip the song
        if allstates.repeat:
            await self.PlayNextSong(ctx.guild.voice_client)

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
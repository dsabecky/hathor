####################################################################
# Library & Modules
####################################################################

# discord imports
import discord
from discord.ext import commands, tasks

# audio processing
from gtts import gTTS   # song intros
import yt_dlp           # youtube library

# system level stuff
import asyncio      # prevents thread locking
import json         # logging (song history, settings, etc)
import os           # system access
import requests     # grabbing raw data from url

# data analysis
import re                 # regex for various filtering
from typing import Any    # legacy type hints
from rich.markup import escape

# date, time, numbers
import time         # epoch timing
import math         # cut playlists down using math.ceil() for fusion
import random       # pseudorandom selection (for shuffle, fusion playlist compilation, etc)

# openai libraries
from openai import AsyncOpenAI   # cleaner than manually calling openai.OpenAI()

# hathor internals
import config
from func import Error, ERROR_CODES, FancyError # error handling
from func import SongDB # song database
from func import _get_random_radio_intro # radio intros
from func import requires_author_perms, requires_author_voice, requires_bot_voice, requires_queue, requires_bot_playing # permission checks
from logs import log_cog # logging


####################################################################
# OpenAI Client
####################################################################

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


####################################################################
# JSON -> global loading
####################################################################

def LoadHistory() -> dict[str, list[dict[str, Any]]]:
    """
    Loads the song history from the JSON file.
    """

    try:
        with open('song_history.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('song_history.json', 'w', encoding='utf-8') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default
        
def SaveHistory() -> None:
    """
    Saves the song history to the JSON file.
    """

    with open('song_history.json', 'w', encoding='utf-8') as file:
        json.dump(song_history, file, ensure_ascii=False, indent=4)

def LoadRadio() -> dict[str, list[str]]:
    """
    Loads the radio playlists from the JSON file.
    """

    try:
        with open('radio_playlists.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        with open('radio_playlists.json', 'w', encoding='utf-8') as file:
            default = {}
            json.dump(default, file, indent=4)
            return default
        
def SaveRadio() -> None:
    """
    Saves the radio playlists to the JSON file.
    """

    with open('radio_playlists.json', 'w', encoding='utf-8') as file:
        json.dump(radio_playlists, file, ensure_ascii=False, indent=4)


####################################################################
# Global variables
####################################################################

SPOTIFY_ACCESS_TOKEN = ''
song_history = LoadHistory()
song_db = SongDB()
radio_playlists = LoadRadio()


####################################################################
# Classes
####################################################################

class Music(commands.Cog, name="Music"):
    """
    Core cog for music functionality.
    """

    def __init__(self, bot):
        self.bot = bot
        self.radio_lock = asyncio.Lock()    # prevents looping in radio monitor


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

        allstates = self.bot.settings[member.guild.id]

        if before.channel is not None and after.channel is None:    # clear out last_active (we left voice)
            allstates.last_active = None

        else:   # init our last_active when we join
            allstates.last_active = time.time()


    ####################################################################
    # Internal: Loops
    ####################################################################

    @tasks.loop(seconds=2)
    async def loop_voice_monitor(self) -> None:
        """
        Monitors voice activity for idle, broken playing, etc.
        """

        for voice_client in self.bot.voice_clients:
            allstates = self.bot.settings[voice_client.guild.id]

            if not voice_client.is_connected():    # sanity check
                continue

            if voice_client.is_playing():   # we're playing something, update last_active
                count = len([member for member in voice_client.channel.members if not member.bot])
                if count > 0:
                    allstates.last_active = time.time()

                if count == 0 and (time.time() - allstates.last_active) > allstates.voice_idle:    # we're the only one in the voice channel for too long
                    await voice_client.disconnect()
                    allstates.last_active = None
                    continue

            if not voice_client.is_playing() and not voice_client.is_paused() and allstates.queue:  # should be, but we're not
                await self.PlayNextSong(voice_client)
                continue

            if allstates.last_active and (time.time() - allstates.last_active) > allstates.voice_idle:  # idle timeout
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

        await self._radio_monitor()

    @loop_radio_monitor.before_loop
    async def _before_radio_monitor(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=config.SPOTIFY_KEY_REFRESH)
    async def loop_spotify_key_creation(self) -> None:
        """
        Creates a new Spotify API Access Token.
        """

        global SPOTIFY_ACCESS_TOKEN      # write access for global

        def blocking_call():
            return requests.post(
                "https://accounts.spotify.com/api/token", headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={ "grant_type": "client_credentials", "client_id": config.SPOTIFY_CLIENT_ID, "client_secret": config.SPOTIFY_CLIENT_SECRET }
            )

        try:
            response = await asyncio.to_thread(blocking_call)
        except Exception as e:
            raise Error(f"loop_spotify_key_creation() -> Spotify.requests.post():\n{e}")

        data = response.json()
        log_cog.info("Generated new Spotify API Access Token.")
        SPOTIFY_ACCESS_TOKEN = data['access_token']

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

        allstates = self.bot.settings[guild_id]
        currently_playing = allstates.currently_playing

        if not voice_client or not currently_playing or not voice_client.is_playing():
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

        allstates = self.bot.settings[guild_id]
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
    
    def _build_radio_embed(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient
    ) -> str:
        """
        Helper function that returns the current radio stations.
        """

        allstates = self.bot.settings[guild_id]

        if not allstates.radio_fusions:
            return f"{allstates.radio_station or 'off'}"
        return '\n'.join(allstates.radio_fusions)
    
    def _build_settings_embed(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient
    ) -> str:
        """
        Helper function that returns the current settings.
        """

        allstates = self.bot.settings[guild_id]

        # music settings
        volume = allstates.volume
        repeat_status = "on" if allstates.repeat else "off"
        shuffle_status = "on" if allstates.shuffle else "off"        
        intro = "on" if allstates.radio_intro else "off"

        return (   # build radio settings text
            f"```🔊 {volume}%  🔁 {repeat_status}  🔀 {shuffle_status}  📢 {intro}```"
        )
    
    async def _fetch_metadata_ytdlp(
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
            log_cog.info(f"Fetching metadata for: [dark_orange]{query}[/]")
            info = await loop.run_in_executor(None, yt_dlp.YoutubeDL(opts).extract_info, ytdlp_query)
        except Exception as e:
            raise Error(f"_fetch_metadata_ytdlp() -> yt_dlp.YoutubeDL():\n{e}")

        if info.get('entries'):
            return info['entries'][0]
        
        return info
    
    def _generate_fusion_playlist(
        self,
        guild_id: int
    ) -> None:
        """
        Generates a fusion playlist.
        """

        allstates = self.bot.settings[guild_id]

        temp_playlist = []
        songs_per_station = math.ceil(40 / len(allstates.radio_fusions))
        for station in allstates.radio_fusions:
            temp_playlist.extend(random.sample(radio_playlists[station.lower()], songs_per_station))

        log_cog.info(f"Generated fusion playlist for [dark_orange]{len(allstates.radio_fusions)}[/] stations.")
        allstates.radio_fusions_playlist = temp_playlist
        
    async def _generate_radio_station(
        self,
        station: str
    ) -> None:
        """
        Generates a radio station playlist.
        """

        if not station:
            raise Error("_generate_radio_station() -> Empty station name.")

        try:
            log_cog.info(f"Generating radio playlist for [dark_orange]{station}[/].")
            response = await self._invoke_chatgpt(
                "Return only the information requested with no additional words or context.",
                f"Make a playlist of 50 songs (formatted as: artist - song), do not number the list, themed around: {station}. Include similar artists and songs."
            )
        except Exception as e:
            return

        if response == "":
            raise Error("_generate_radio_station() -> _invoke_chatgpt():\nChatGPT is responding empty strings.")
        
        parsed_response = response.split('\n')
        radio_playlists[station.lower()] = []

        for item in parsed_response:
            radio_playlists[station.lower()].append(item.strip())

        SaveRadio()
        log_cog.info(f"Radio playlist for [dark_orange]{station}[/] generated.")

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
                model=config.CHATGPT_MODEL,
                messages=conversation,
                temperature=config.CHATGPT_TEMPERATURE
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
            response = await asyncio.to_thread(requests.get, f'https://api.spotify.com/v1/playlists/{playlist_id}', headers={'Authorization': f'Bearer {SPOTIFY_ACCESS_TOKEN}'})
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

        playlist_id = re.search(r'[&?]list=([a-zA-Z0-9_-]+)', payload).group(1)
        if not playlist_id:
            raise Error("_parse_youtube_playlist():\n No playlist ID found.")

        try:    # grab the playlist from spotify api
            # First get playlist details
            response = await asyncio.to_thread(requests.get, f'https://www.googleapis.com/youtube/v3/playlistItems?key={config.YOUTUBE_API_KEY}&part=snippet&maxResults=50&playlistId={playlist_id}')
        except Exception as e:
            raise Error(f"_parse_youtube_playlist() -> YouTube.requests.get():\n{e}")

        response_json = response.json()     # convert response to json
        playlist = response_json['items']  # get the tracklist from items
        playlist_length = int(response_json['pageInfo']['totalResults']) if int(response_json['pageInfo']['totalResults']) <= config.MUSIC_MAX_PLAYLIST else config.MUSIC_MAX_PLAYLIST  # trim list length if needed

        return "YouTube", playlist_id, playlist, playlist_length

    async def _radio_monitor(self) -> None:
        """
        Monitors radio stations for new songs.
        """

        async with self.radio_lock:
            for guild in self.bot.guilds:

                allstates = self.bot.settings[guild.id]
                voice_client = guild.voice_client

                if not voice_client:    # no voice client, skip
                    continue

                if not allstates.radio_station and not allstates.radio_fusions: # no radio station or fusions, skip
                    continue

                elif allstates.radio_fusions and allstates.radio_fusions_playlist and len(allstates.queue) < config.RADIO_QUEUE:     # fuse radio checkpoint🔞
                    playlist = random.sample(allstates.radio_fusions_playlist, config.RADIO_QUEUE+1)
                    await self.QueuePlaylist(voice_client, playlist, None)
                    continue

                elif (allstates.radio_station and allstates.radio_station.lower() in radio_playlists) and len(allstates.queue) < config.RADIO_QUEUE:  # radio station checkpoint 🔞
                    playlist = random.sample(radio_playlists[allstates.radio_station.lower()], config.RADIO_QUEUE+1)
                    await self.QueuePlaylist(voice_client, playlist, None)
                    continue

                elif allstates.radio_station and allstates.radio_station.lower() not in radio_playlists:   # previously ungenerated radio station
                    try:
                        await self._generate_radio_station(allstates.radio_station)
                    except Exception as e:
                        log_cog.error(f"loop_radio_monitor() -> _generate_radio_station():\n{escape(e)}")
                        continue

                    playlist = random.sample(radio_playlists[allstates.radio_station.lower()], config.RADIO_QUEUE+1)
                    await self.QueuePlaylist(voice_client, playlist, None)

    ####################################################################
    # Internal: Core Functions
    ####################################################################

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
            log_cog.info(f"DownloadSong(): [dark_orange]{query}[/]")
            info = await loop.run_in_executor(None, yt_dlp.YoutubeDL(opts).extract_info, ytdlp_query)
        except Exception as e:
            raise Error(f"DownloadSong() -> yt_dlp.YoutubeDL():\n{e}")

        if info and info.get('entries'):    # remove nest if nested
            info = info["entries"][0]

        try:    # generates proper tags for songDB
            log_cog.info(f"DownloadSong(): Attemping to fetch proper tags for [dark_orange]{info['title']}[/]")
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
        song_db.save()

        return result

    async def PlayNextSong(
        self,
        voice_client: discord.VoiceClient
    ) -> None:
        """
        Plays the next song in the queue.
        """

        allstates = self.bot.settings[voice_client.guild.id]

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
        volume = allstates.volume / 100
        intro_volume = allstates.volume < 80 and (allstates.volume + 20) / 100  # slightly bump intro volume

        if song.get('song_artist') and allstates.radio_intro and random.random() < 0.4:   # add an intro (if radio is enabled)
            await self.PlayRadioIntro(voice_client, song['id'], song['song_artist'], song['song_title'], intro_volume)

        def song_cleanup(error: Exception | None = None):  # song file cleanup
            if allstates.repeat:    # don't cleanup if we're on repeat
                allstates.queue.insert(0, song)

        voice_client.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(allstates.currently_playing['file_path']), volume=volume), after=song_cleanup)    # actually play the song, cleanup after=

        song_history[str(voice_client.guild.id)].append({ "timestamp": time.time(), "title": song['title'] })
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

        is_special = random.random() < 0.4  # 40% odds we use a song specific intro
        text = ""   # initiate the intro string

        if is_special:  # special intro
            text = await self._invoke_chatgpt(
                'Return only the information requested with no additional words or context. Do not wrap in quotes.',
                f'Give me a short radio dj intro for "{artist} - {title}". Intro should include info about the song. Limit of 2 sentences.'
            )
        else:   # regular intro
            text = await _get_random_radio_intro(voice_client.bot, voice_client.guild.name, title, artist)

        tts = await asyncio.to_thread(gTTS, text, lang="en")
        intro_path = f"{config.SONGDB_PATH}/intro_{voice_client.guild.id}.mp3"
        tts.save(intro_path)

        done = asyncio.Event()  # event waiter (for intro completion)
        def _on_done(_):
            done.set()

        log_cog.info(f"Radio Intro: [dark_orange]{text}[/]")
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

        allstates = self.bot.settings[voice_client.guild.id]

        playlist_type, playlist_id, playlist, playlist_length = None, None, None, None
        if 'open.spotify.com/playlist/' in payload: # spotify playlist
            try:
                playlist_type, playlist_id, playlist, playlist_length = await self._parse_spotify_playlist(payload)
            except Exception as e:
                if message:     # finalize message if we fail
                    embed = discord.Embed(description="❌ I ran into an issue with the Spotify API. 😢")
                    await message.edit(content=None, embed=embed); return
        
        elif 'list=' in payload:  # youtube playlist
            try:
                playlist_type, playlist_id, playlist, playlist_length = await self._parse_youtube_playlist(payload)

            except Exception as e:
                if message:     # finalize message if we fail
                    embed = discord.Embed(description="❌ I ran into an issue with the YouTube API. 😢")
                    await message.edit(content=None, embed=embed); return

        else:
            playlist_type, playlist_id, playlist, playlist_length = "ChatGPT", "ChatGPT", payload, len(payload) if len(payload) <= config.MUSIC_MAX_PLAYLIST else config.MUSIC_MAX_PLAYLIST

        log_cog.info(f"QueuePlaylist: Playlist ([dark_orange]{playlist_id}[/]) playlist length [dark_orange]{playlist_length}[/]")

        lines = []   # temp playlist for text output
        for i, item in enumerate((playlist[:playlist_length]), start=1):

            if message:     # update associated message if applicable
                embed = discord.Embed(description=f"🧠 Preparing your {playlist_type} playlist ({i}/{playlist_length})...")
                await message.edit(content=None, embed=embed)

            try:    # fetch song metadata
                if playlist_type == "Spotify":  # spotify filtering
                    track    = f"{item['track']['artists'][0]['name']} - {item['track']['name']}"
                    metadata = await self._fetch_metadata_ytdlp(track)

                elif playlist_type == "YouTube":    # youtube filtering
                    track    = item['snippet']['title']
                    metadata = await self._fetch_metadata_ytdlp(f"https://youtube.com/watch?v={item['snippet']['resourceId']['videoId']}")

                else:   # just chatgpt
                    track    = item
                    metadata = await self._fetch_metadata_ytdlp(item)
            except Exception as e:   # fail gracefully
                if "Sign in to confirm your age" in str(e):
                    output = "❌ That content is age restricted. 😢\nMoving onto the next song. 🫡"
                else:
                    output = f"❌ I ran into an issue finding {track}. 😢\nMoving onto the next song. 🫡"

                if message:
                    embed = discord.Embed(description=output)
                    await message.edit(content=None, embed=embed); continue

            if metadata['id'] in song_db and os.path.exists(song_db[metadata['id']]['file_path']):  # save the bandwidth
                log_cog.info(f"QueuePlaylist: ([dark_orange]{i}[/]/[dark_orange]{playlist_length}[/]) [dark_orange]\"{metadata['title']}\"[/] already downloaded.")
                song = song_db[metadata['id']]

            elif metadata['duration'] >= config.MUSIC_MAX_DURATION: # song exceeds config.MUSIC_MAX_DURATION, fail gracefully
                if message:
                    embed = discord.Embed(description=f"❌ Song is too long! ({metadata['duration']} > {config.MUSIC_MAX_DURATION}) 🕑\nMoving onto the next song. 🫡")
                    await message.edit(content=None, embed=embed); continue
            
            else:  # seems good, download it
                log_cog.info(f"QueuePlaylist: ([dark_orange]{i}[/]/[dark_orange]{playlist_length}[/]) Downloading [dark_orange]\"{metadata['webpage_url']}\"[/]")

                try:
                    song = await self.DownloadSong(f"https://youtube.com/watch?v={metadata['id']}", track, None)
                except Exception as e:   # fail gracefully
                    if "Sign in to confirm your age" in str(e):
                        output = "❌ That content is age restricted. 😢\nMoving onto the next song. 🫡"
                    else:
                        output = f"❌ I ran into an issue downloading {track}. 😢\nMoving onto the next song. 🫡"

                    if message:
                        embed = discord.Embed(description=output)
                        await message.edit(content=None, embed=embed); continue

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

        allstates = self.bot.settings[voice_client.guild.id]
        track = None


        if 'open.spotify.com/track/' in payload:
            track_id = re.search(r'/track/([a-zA-Z0-9]+)(?:[/?]|$)', payload).group(1)
            try:    # grab the trackid from spotify
                response = await asyncio.to_thread(requests.get, f'https://api.spotify.com/v1/tracks/{track_id}', headers={'Authorization': f'Bearer {SPOTIFY_ACCESS_TOKEN}'})
            except Exception as e:  # finalize the message if we fail
                embed = discord.Embed(description="❌ I ran into an issue with the Spotify API. 😢")
                await message.edit(content=None, embed=embed); return

            response_json = response.json()
            track = f"{response_json['artists'][0]['name']} - {response_json['name']}"

        try:    # fetch song metadata
            if track:   #spotify
                metadata = await self._fetch_metadata_ytdlp(track)
            else:   # regular
                metadata = await self._fetch_metadata_ytdlp(payload)
        except Exception as e:
            if message:
                if "Sign in to confirm your age" in str(e):
                    output = "❌ That content is age restricted. 😢"
                else:
                    output = "❌ I ran into an issue finding that song. 😢"

                embed = discord.Embed(description=output)
                await message.edit(content=None, embed=embed); return

        if metadata['id'] in song_db and os.path.exists(song_db[metadata['id']]['file_path']):  # save the bandwidth
            log_cog.info(f"Song: [dark_orange]\"{metadata['title']}\"[/] already downloaded.")
            song = song_db[metadata['id']]

        elif metadata['duration'] >= config.MUSIC_MAX_DURATION: # song exceeds config.MUSIC_MAX_DURATION
            embed = discord.Embed(description="❌ Song is too long! 🕑")
            await message.edit(content=None, embed=embed); return
        
        else:  # seems good, download it
            log_cog.info(f"QueueIndividualSong(): Downloading [dark_orange]\"{metadata['webpage_url']}\"[/]")
            embed = discord.Embed(description=f"💾 Downloading [dark_orange]\"{metadata['title']}\"[/] ([dark_orange]{metadata['webpage_url']}[/])...")
            await message.edit(content=None, embed=embed)

            try:    # download the song
                song = await self.DownloadSong(f"https://youtube.com/watch?v={metadata['id']}", track, None)
            except Exception as e:
                if message:
                    output = f"❌ I ran into an issue downloading {metadata['title']}. 😢"

                    if "Sign in to confirm your age" in str(e):
                        output = "❌ That content is age restricted. 😢"

                    embed = discord.Embed(description=output)
                    await message.edit(content=None, embed=embed); return

        if is_priority:     # push to top of queue
            allstates.queue.insert(0, song)
            embed = discord.Embed(description=f"⬆️ Added {metadata['title']} to the top of the queue.")

        elif allstates.shuffle:     # shuffle the song into the queue
            allstates.queue.insert(random.randint(0, len(allstates.queue)), song)
            embed = discord.Embed(description=f"🔀 Added {metadata['title']} to the shuffled queue.")

        else:   # add song to the queue
            allstates.queue.append(song)
            embed = discord.Embed(description=f"✅ Added {metadata['title']} to the queue.")

        await message.edit(content=None, embed=embed)   # send our final message


    ####################################################################
    # Command triggers
    ####################################################################

    @commands.command(name="aiplaylist", aliases=['smartplaylist'])
    @requires_author_voice()
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

        allstates = self.bot.settings[ctx.guild.id]

        if not args or len(args) < 3:
            raise Error(ERROR_CODES['syntax'])

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)
        
        embed = discord.Embed(description=f"🧠 Generating your AI playlist...")
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        try:    # request our playlist
            log_cog.info(f"!aiplaylist: Generating playlist request...")
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
    @requires_author_perms()
    @requires_author_voice()
    @requires_queue()
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

        allstates = self.bot.settings[ctx.guild.id]

        if len(allstates.queue) < 2:    # is there even enough songs to justify?
            raise FancyError(ERROR_CODES['bump_short'])

        elif not song_number or not song_number.isdigit() or int(song_number) < 2:
            raise FancyError(ERROR_CODES['syntax'])

        bumped = allstates.queue.pop(int(song_number) - 1)
        allstates.queue.insert(0, bumped)
        embed = discord.Embed(description=f"Bumped {bumped['title']} to the top of the queue.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='clear')
    @requires_author_perms()
    @requires_queue()
    async def trigger_clear(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Clears the current playlist.

        Syntax:
            !clear
        """

        allstates = self.bot.settings[ctx.guild.id]
        
        embed = discord.Embed(description=f"Removed {len(allstates.queue)} songs from queue.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        allstates.queue = []

    @commands.command(name='defuse')
    @requires_author_perms()
    @requires_author_voice()
    async def trigger_defuse(
        self,
        ctx: commands.Context,
        *,
        payload: str = None
    ) -> None:
        """
        Removes a radio station from the fusion.

        Syntax:
            !defuse <station>
        """

        allstates = self.bot.settings[ctx.guild.id]

        if not payload: # no station provided
            raise FancyError(ERROR_CODES['syntax'])
        
        if payload.lower() not in allstates.radio_fusions: # station not fused
            raise FancyError(ERROR_CODES['radio_not_fused'])
        
        if len(allstates.radio_fusions) == 1: # deny defusion of last station
            embed = discord.Embed(title="Error", description="❌ You must have at least one radio station fused.", color=discord.Color.red())
            await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none()); return

        allstates.radio_fusions.remove(payload.lower())     # remove the station from the fusion list
        self._generate_fusion_playlist(ctx.guild.id)        # generate the fusion playlist
        await self._radio_monitor()                         # kick-start the radio monitor

        embed = discord.Embed(description=f"📻 Radio fusions updated, themes: {', '.join(f'**{s}**' for s in allstates.radio_fusions)}.", color=discord.Color.green())
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='fuse')
    @requires_author_perms()
    @requires_author_voice()
    async def trigger_fuse(
        self,
        ctx: commands.Context,
        *,
        payload: str = None
    ) -> None:
        """
        Fuses two or more radio stations together.
        If there is an active radio station, it will be added to the fusion.

        Syntax:
            !fuse <station1> | <station2> | <station3>
        """

        allstates = self.bot.settings[ctx.guild.id]
        
        if not payload: # no fusion provided
            raise FancyError(ERROR_CODES['syntax'])

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)

        payload_list = [s.lower().strip() for s in payload.split("|")]
        if allstates.radio_station:   # add the current station to the list, if it exists
            payload_list.append(allstates.radio_station.lower())

        if len(payload_list + allstates.radio_fusions) > 5:
            embed = discord.Embed(description=f"❌ You can only fuse up to 5 radio stations at a time. 😢", color=discord.Color.red())
            await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none()); return

        embed = discord.Embed(description=f"🧠 Fusing radio stations...", color=discord.Color.dark_purple())
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        for station in payload_list: # add to fusion list, if not already in it
            print(f"for() station: {station}")
            if not station or station in allstates.radio_fusions:
                continue

            if station not in radio_playlists: # not already generated?
                async with ctx.channel.typing():
                    try:
                        await self._generate_radio_station(station)
                    except Exception as e:
                        embed = discord.Embed(description=f"❌ I ran into an issue. 😢")
                        await message.edit(content=None, embed=embed); return

            allstates.radio_fusions.append(station) # add to fusion list

        self._generate_fusion_playlist(ctx.guild.id)    # generate the fusion playlist

        embed = discord.Embed(description=f"⚛️ Radio fusions enabled, themes: {', '.join(f'**{s}**' for s in allstates.radio_fusions)}.", color=discord.Color.green())
        await message.edit(content=None, embed=embed)

        await self._radio_monitor()                     # kick-start the radio monitor
        
        
    ### TODO: Add hot100 radio toggle
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
    @requires_author_perms()
    async def trigger_intro(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Toggles song intros for the radio station.

        Syntax:
            !intro
        """

        allstates = self.bot.settings[ctx.guild.id]
        allstates.radio_intro = not allstates.radio_intro
        allstates._save_settings()

        embed = discord.Embed(description=f"📢 Radio intros {allstates.radio_intro and 'enabled' or 'disabled'}.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='pause')
    @requires_author_perms()
    @requires_author_voice()
    @requires_bot_playing()
    @requires_bot_voice()
    async def trigger_pause(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Pauses the song playing.

        Syntax:
            !pause
        """

        allstates = self.bot.settings[ctx.guild.id]

        allstates.pause_time = time.time()  # record when we paused
        ctx.guild.voice_client.pause()      # actually pause

        embed = discord.Embed(description=f"⏸️ Playback paused.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='play')
    @requires_author_voice()
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

        if not payload:    # no data provided
            raise FancyError(ERROR_CODES['syntax'])

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)        

        embed = discord.Embed(description=f"🔎 Searching for {payload}")
        message = await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        if 'list=' in payload or 'open.spotify.com/playlist' in payload:
            await asyncio.create_task(self.QueuePlaylist(ctx.guild.voice_client, payload, message))
        else:
            await asyncio.create_task(self.QueueIndividualSong(ctx.guild.voice_client, payload, False, message))


    @commands.command(name='playnext', aliases=['playbump'])
    @requires_author_perms()
    @requires_author_voice()
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
            raise FancyError(ERROR_CODES['syntax'])

        is_playlist = ('list=' in payload or 'open.spotify.com/playlist' in payload)
        if is_playlist:     # playlists not supported with playnext
            raise FancyError(ERROR_CODES['shuffle_no_playlist'])
        
        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)

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

        allstates = self.bot.settings[ctx.guild.id]
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

        # radio section
        radio = self._build_radio_embed(ctx.guild.id, voice_client)
        embed.add_field(name=f"{'Radio Stations' if allstates.radio_fusions else 'Radio Station'}", value=radio, inline=False)

        # music settings
        settings = self._build_settings_embed(ctx.guild.id, voice_client)
        embed.add_field(name="Settings", value=settings, inline=False)

        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='radio', aliases=['dj'])
    @requires_author_perms()
    @requires_author_voice()
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

        allstates = self.bot.settings[ctx.guild.id]
        
        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)

        if allstates.radio_fusions:     # cancel out fusion
            allstates.radio_fusions = None
            allstates.radio_fusions_playlist = None

        if payload:
            allstates.radio_station = payload
            embed = discord.Embed(description=f"📻 Radio enabled, theme: **{payload}**.")
            
        elif allstates.radio_station == None:
            allstates.radio_station = config.RADIO_DEFAULT_THEME
            embed = discord.Embed(description=f"📻 Radio enabled, theme: {allstates.radio_station}.")
        else:
            allstates.radio_station = False
            embed = discord.Embed(description=f"📻 Radio disabled.")
        
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await self._radio_monitor() 

    @commands.command(name='remove')
    @requires_author_perms()
    @requires_queue()
    async def trigger_remove(self, ctx, args=None):
        """
        Removes the requested song from queue.

        Syntax:
            !remove <song number>
        """

        allstates = self.bot.settings[ctx.guild.id]
        
        if not args or (args and not args.isdigit()):
            raise FancyError(ERROR_CODES['syntax'])

        args = int(args)
        if args < 1 or args > len(allstates.queue):
            raise FancyError(ERROR_CODES['queue_range'])

        else:
            song = allstates.queue.pop((int(args) - 1))
            info_embed = discord.Embed(description=f"Removed **{song['title']}** from queue.")
            await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='repeat', aliases=['loop'])
    @requires_author_perms()
    async def trigger_repeat(self, ctx):
        """
        Toggles song repeating.

        Syntax:
            !repeat

        Aliases:
            !loop
        """

        allstates = self.bot.settings[ctx.guild.id]
        allstates.repeat = not allstates.repeat # change value to current opposite (True -> False)

        info_embed = discord.Embed(description=f"🔁 Repeat mode {allstates.repeat and 'enabled' or 'disabled'}.")
        await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='resume')
    @requires_author_perms()
    @requires_author_voice()
    @requires_bot_playing()
    @requires_bot_voice()
    async def trigger_resume(self, ctx, *, args=None):
        """
        Resume song playback.

        Syntax:
            !resume
        """

        allstates = self.bot.settings[ctx.guild.id]
        
        allstates.start_time += (allstates.pause_time - allstates.start_time)   # update the start_time
        ctx.guild.voice_client.resume()     # actually resume playing

        info_embed = discord.Embed(description=f"🤘 Playback resumed.")
        await ctx.reply(embed=info_embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='shuffle')
    @requires_author_perms()
    async def trigger_shuffle(self, ctx):
        """
        Toggles playlist shuffle.

        Syntax:
            !shuffle
        """

        allstates = self.bot.settings[ctx.guild.id]
        
        random.shuffle(allstates.queue)     # actually shuffles the queue
        allstates.shuffle = not allstates.shuffle   # update the shuffle variable

        embed = discord.Embed(description=f"🔀 Shuffle mode {allstates.shuffle and 'enabled' or 'disabled'}.")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='skip')
    @requires_author_perms()
    @requires_bot_playing()
    @requires_bot_voice()
    async def trigger_skip(self, ctx):
        """
        Skips the currently playing song.

        Syntax:
            !skip
        """

        allstates = self.bot.settings[ctx.guild.id]
        embed = discord.Embed(description=f"⏭️ Skipping {allstates.currently_playing['title']}")
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())

        ctx.guild.voice_client.stop()   # actually skip the song
        if allstates.repeat:
            await self.PlayNextSong(ctx.guild.voice_client)


####################################################################
# Launch Cog
####################################################################

async def setup(bot):
    log_cog.info("Loading [dark_orange]Music[/] cog...")
    await bot.add_cog(Music(bot))
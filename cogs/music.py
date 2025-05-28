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
from func import _get_random_radio_intro, _build_embed, _set_profile_status
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

    def __init__(self, bot):
        self.bot = bot
        self.radio_lock = asyncio.Lock()    # prevents looping in radio monitor


    ####################################################################
    # Cog 'on_' listeners
    ####################################################################

    @commands.Cog.listener()
    async def on_ready(self) -> None:

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

        active_count = sum(1 for guild in self.bot.guilds if self.bot.settings[guild.id].currently_playing and guild.voice_client)
        if active_count == 0:
            await _set_profile_status(self.bot)

        elif active_count > 1:
            await _set_profile_status(self.bot, f"music in {active_count} servers")

        for voice_client in self.bot.voice_clients:
            allstates = self.bot.settings[voice_client.guild.id]

            if not voice_client.is_connected():    # sanity check
                continue

            if voice_client.is_playing():   # we're playing something, update last_active
                user_count = sum(1 for member in voice_client.channel.members if not member.bot)
                song = allstates.currently_playing['song_artist'] + " - " + allstates.currently_playing['song_title'] if allstates.currently_playing.get('song_artist') else allstates.currently_playing['title']

                if active_count == 1:
                    await _set_profile_status(self.bot, song)

                if user_count > 0:
                    allstates.last_active = time.time()

                if user_count == 0 and (time.time() - allstates.last_active) > allstates.voice_idle:    # we're the only one in the voice channel for too long
                    await voice_client.disconnect()
                    allstates.last_active, allstates.start_time, allstates.pause_time = None, None, None
                    allstates.currently_playing, allstates.repeat, allstates.queue = None, False, []
                    allstates.radio_station, allstates.radio_fusions, allstates.radio_fusions_playlist = None, [], []
                    continue

            if not voice_client.is_playing() and not voice_client.is_paused() and allstates.queue:  # should be, but we're not
                await self._play_next_song(voice_client)
                continue

            if allstates.last_active and (time.time() - allstates.last_active) > allstates.voice_idle:  # idle timeout
                await voice_client.disconnect()
                allstates.last_active, allstates.start_time, allstates.pause_time = None, None, None
                allstates.currently_playing, allstates.repeat, allstates.queue = None, False, []
                allstates.radio_station, allstates.radio_fusions, allstates.radio_fusions_playlist = None, [], []

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

    async def _add_media_to_queue(
        self,
        voice_client: discord.VoiceClient,
        song: dict[str, Any],
        is_priority: bool
    ) -> str:
        """
        Helper function for adding media to the queue.
        """

        allstates = self.bot.settings[voice_client.guild.id]

        if is_priority:     # push to top of queue
            allstates.queue.insert(0, song)
            return "⬆️", "the top of the queue"

        elif allstates.shuffle:     # shuffle the song into the queue
            allstates.queue.insert(random.randint(0, len(allstates.queue)), song)
            return "🔀", "the shuffled queue"

        else:   # add song to the queue
            allstates.queue.append(song)
            return "✅", "the queue"

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
    
    async def _download_media(
        self,
        url: str,
        known_info: str | None = None
    ) -> dict[str, Any]:
        """
        Helper function that downloads media from a given url.
        """

        chatgpt = self.bot.get_cog("ChatGPT")

        opts = {
            "format": "bestaudio/best",
            "postprocessors": [{ "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192" }],
            "outtmpl": f"{config.SONGDB_PATH}/%(id)s.%(ext)s",
            "ignoreerrors": True,
            "no_warnings": True,
            "quiet": True,
        }

        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, yt_dlp.YoutubeDL(opts).extract_info, url)
        except Exception as e:
            raise Error(f"_download_media() -> yt_dlp.YoutubeDL():\n{e}")
        
        if info and info.get('entries'):    # remove nest if nested
            info = info["entries"][0]

        if known_info:
            log_cog.info(f"_download_media: Using known metadata: [dark_orange]{known_info}[/]")
            song_artist, song_title = known_info.split(" - ", 1)

        elif info.get('artists'): # soundcloud provides the artists tag in metadata
            log_cog.info(f"_download_media: 'artists' tag found for [dark_orange]{info['title']} {info['webpage_url']}[/]")
            song_artist, song_title = ", ".join(info['artists']), info['title']

        # TODO: figure out a better / more accurate way to do this
        # elif metadata.get('tags') and len(metadata['tags']) >= 2: # youtube (typically) includes the artist and title as first two params of 'tags'
        #     log_cog.info(f"DownloadSong: 'tags' tag found for [dark_orange]{info['title']} {info['webpage_url']}[/]")
        #     song_artist = metadata['tags'][0]
        #     song_title = metadata['tags'][1]

        else:
            try:
                log_cog.info(f"_download_media: no tags found for [dark_orange]{info['title']} {info['webpage_url']}[/]. Asking ChatGPT...")
                response = await chatgpt._invoke_chatgpt(
                    "Respond with only the asked answer, in 'Artist - Song Title' format, or 'None' if you do not know.",
                    f"What is the name of this track: {info['title']}? The webpage is: {info['webpage_url']}.")
            except Exception as e:
                raise Error(f"_download_media() -> chatgpt._invoke_chatgpt():\n{e}")
            
            if ' - ' in response:
                song_artist, song_title = response.split(" - ", 1)
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
        song_db.save()  # save the database

        return result
    
    async def enqueue_media(
        self,
        voice_client: discord.VoiceClient,
        payload: list[str],
        is_priority: bool,
        is_manual: bool = False,
        message: discord.Message | None = None
    ) -> None:
        """
        Handler function for enqueueing media.
        """

        if 'https://' in payload[0]:    # send urls to link parser
            try:
                payload = await self.parse_media(payload)
            except Exception:
                if message:
                    await message.edit(content=None, embed=_build_embed('err', '❌ I ran into an issue parsing your request. 😢', 'r')); return

        lines: list[str] = []   # stage empty list
        for i, item in enumerate(payload, start=1):
            if message:
                await message.edit(content=None, embed=_build_embed('Music', f'🧠 Preparing your media ({i}/{len(payload)})', 'p'))

            try:    # fetch metadata
                metadata = await self._fetch_metadata_ytdlp(item)
            except Exception:
                continue

            if metadata['id'] in song_db and os.path.exists(song_db[metadata['id']]['file_path']):  # save the bandwidth
                log_cog.info(f"enqueue_media: [dark_orange]\"{metadata['title']}\"[/] already downloaded. ([dark_orange]{i}[/]/[dark_orange]{len(payload)}[/])")
                song = song_db[metadata['id']]

            elif metadata['duration'] >= config.MUSIC_MAX_DURATION: # song exceeds max duration
                log_cog.info(f"enqueue_media: ([dark_orange]{i}[/]/[dark_orange]{len(payload)}[/]) [dark_orange]\"{metadata['title']}\"[/] exceeds max duration.")
                continue

            else:    # download media
                try:
                    log_cog.info(f"enqueue_media: Downloading [dark_orange]\"{metadata['webpage_url']}\"[/] ([dark_orange]{i}[/]/[dark_orange]{len(payload)}[/])")
                    song = await self._download_media(metadata['webpage_url'], item if is_manual else False)
                except Exception:
                    continue

            log_cog.info(f"enqueue_media: Adding [dark_orange]\"{song['song_artist']} - {song['song_title']}\"[/] to queue")
            queue_icon, queue_string = await self._add_media_to_queue(voice_client, song, is_priority)
            lines.append(f"{i}. {song['song_artist']} - {song['song_title']}")

        if message:
            if len(lines) > 10:
                shown = lines[:10]
                shown.append(f"... and {len(lines) - 10} more.")
            else:
                shown = lines

            embed_list = "\n".join(shown)
            await message.edit(content=None, embed=_build_embed('Music', f"{queue_icon} Your media has been added to {queue_string}!", 'g', [('Added:', embed_list, False)]))
    
    async def _fetch_metadata_ytdlp(
        self,
        query: str
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
        songs_per_station = math.ceil(50 / len(allstates.radio_fusions))
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

        chatgpt = self.bot.get_cog("ChatGPT")

        if not station:
            raise Error("_generate_radio_station() -> Empty station name.")

        try:
            log_cog.info(f"Generating radio playlist for [dark_orange]{station}[/].")
            response = await chatgpt._invoke_chatgpt(
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

    async def parse_media(
        self,
        payload: list[str]
    ) -> list[dict[str, Any]]:
        """
        Parses media from a list of strings.
        """

        if 'youtu.be/' in payload[0] or 'youtube.com/' in payload[0]:
            log_cog.info(f"parse_media -> _parse_youtube_link: [dark_orange]{payload[0]}[/]")
            return await self._parse_youtube_link(payload[0])

        elif 'spotify.com/' in payload[0]:
            log_cog.info(f"parse_media -> _parse_spotify_link: [dark_orange]{payload[0]}[/]")
            return await self._parse_spotify_link(payload[0])
        
        elif 'soundcloud.com/' in payload[0]:
            log_cog.info(f"parse_media -> _parse_soundcloud_link: [dark_orange]{payload[0]}[/]")
            return await self._parse_soundcloud_link(payload[0])

        else:
            log_cog.info(f"parse_media -> return: [dark_orange]{payload[0]}[/]")
            return [payload[0]]
        
    async def _parse_soundcloud_link(
        self,
        payload: str
    ) -> list[str]:
        """
        Helper function that parses soundcloud links.
        """

        if '/sets/' in payload:
            opts = { "skip_download": True, "quiet": True, "no_warnings": True }

            loop = asyncio.get_running_loop()
            try:
                response = await loop.run_in_executor(None, yt_dlp.YoutubeDL(opts).extract_info, payload)
            except Exception as e:
                raise Error(f"_parse_soundcloud_link() -> yt_dlp.YoutubeDL():\n{e}")

            if response.get('entries'):
                response = response['entries']
            
            lines: list[str] = [
                item['webpage_url']
                for item in response
            ]
            return lines
        
        else:
            return [payload]

    async def _parse_spotify_link(
        self,
        payload: str
    ) -> list[str]:
        """
        Helper function that parses spotify links.
        """

        spotify_id = re.search(r'/(?:playlist|album|track)/([A-Za-z0-9]+)(?:[/?]|$)', payload).group(1) # regex the id
        if not spotify_id:
            raise Error("_parse_spotify_link(): No playlist, album, or track ID found.")
    
        base = (    # determine the base of the link
            'playlists' if 'playlist/' in payload else
            'albums' if 'album/' in payload else
            'tracks'
        )
        url = f"https://api.spotify.com/v1/{base}/{spotify_id}"    # build the url
        
        try:
            response = await asyncio.to_thread(requests.get, url, headers={"Authorization": f"Bearer {SPOTIFY_ACCESS_TOKEN}"})
        except Exception as e:
            raise Error(f"_parse_spotify_link() -> Spotify.requests.get():\n{e}")
        
        response_json = response.json()     # convert response to json

        if base == 'playlists' or base == 'albums':
            lines: list[str] = [
                f"{item['artists'][0]['name']} - {item['name']}"
                for item in response_json['tracks']['items']
            ]
            return lines
        
        else:
            return [f"{response_json['artists'][0]['name']} - {response_json['name']}"]

    async def _parse_youtube_link(
        self,
        payload: str
    ) -> list[str]:
        """
        Helper function that parses youtube links.
        """

        if 'list=' in payload:
            playlist_id = re.search(r'[&?]list=([a-zA-Z0-9_-]+)', payload).group(1)
            if not playlist_id:
                raise Error("_parse_youtube_link():\n No playlist ID found.")
            
            try:
                response = await asyncio.to_thread(requests.get, f'https://www.googleapis.com/youtube/v3/playlistItems?key={config.YOUTUBE_API_KEY}&part=snippet&maxResults=20&playlistId={playlist_id}')
                response_json = response.json()
            except Exception as e:
                raise Error(f"_parse_youtube_link() -> YouTube.requests.get():\n{e}")
            
            lines: list[str] = [
                f"https://youtube.com/watch?v={item['snippet']['resourceId']['videoId']}"
                for item in response_json['items']
            ]
            return lines
        
        else:
            url = re.search(r'[&?]v=([a-zA-Z0-9_-]+)', payload).group(1)
            if not url:
                raise Error("_parse_youtube_link():\n No video ID found.")
            
            return [f"https://youtube.com/watch?v={url}"]
        
    async def _play_next_song(
        self,
        voice_client: discord.VoiceClient
    ) -> None:
        """
        Helper function that plays the next song in the queue.
        """

        allstates = self.bot.settings[voice_client.guild.id]

        if voice_client.is_playing() or voice_client.is_paused():    # stop trying if we're playing something (or paused)
            return

        if not allstates.queue:     # nothing to play
            allstates.currently_playing = None
            return

        song = allstates.queue.pop(0)   # pop the next queued song
        allstates.currently_playing = {
            "title": song['title'], "song_artist": song['song_artist'], "song_title": song['song_title'],
            "duration": song['duration'], "file_path": song['file_path'], "thumbnail": song['thumbnail'] }

        allstates.start_time = time.time()
        volume = allstates.volume / 100
        intro_volume = allstates.volume < 80 and (allstates.volume + 20) / 100  # slightly bump intro volume

        if song.get('song_artist') and allstates.radio_intro and random.random() < 0.4:   # add an intro (if radio is enabled)
            await self._play_radio_intro(voice_client, song['song_artist'], song['song_title'], intro_volume)

        def song_cleanup(error: Exception | None = None):  # song file cleanup
            if allstates.repeat:    # don't cleanup if we're on repeat
                allstates.queue.insert(0, song)

        voice_client.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(allstates.currently_playing['file_path']), volume=volume), after=song_cleanup)    # actually play the song

        history_text = f"{song['song_artist']} - {song['song_title']}" if song.get('song_artist') and song.get('song_title') else song['title']
        song_history[str(voice_client.guild.id)].append(history_text) # add to history
        song_history[str(voice_client.guild.id)] = song_history[str(voice_client.guild.id)][-100:] # trim history to 100
        SaveHistory()
        
    async def _play_radio_intro(
        self,
        voice_client: discord.VoiceClient,
        artist: str,
        title: str,
        volume: float
    ) -> None:
        """
        Helper function that plays a radio intro.
        """

        chatgpt = self.bot.get_cog("ChatGPT")

        is_special = random.random() < 0.4  # 40% odds we use a song specific intro
        text = ""   # initiate the intro string

        if is_special:  # special intro
            try:
                text = await chatgpt._invoke_chatgpt(
                    'Return only the information requested with no additional words or context. Do not wrap in quotes.',
                    f'Give me a short radio dj intro for "{artist} - {title}". Intro should include info about the song. Limit of 2 sentences.'
                )
            except Exception:
                pass
        else:   # regular intro
            text = await _get_random_radio_intro(self.bot, voice_client.guild.name, title, artist)

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
            raise Error(f"_play_radio_intro() -> os.remove():\n{e}")

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
                    pruned_playlist = [ song for song in allstates.radio_fusions_playlist if song not in song_history[str(guild.id)][-20:] ]  # prune against history
                    pruned_playlist = [ song for song in pruned_playlist if song not in [q.get('song_artist') + " - " + q.get('song_title') for q in allstates.queue] ]  # prune against queue
                    if len(pruned_playlist) < config.RADIO_QUEUE+1:
                        log_cog.info(f"loop_radio_monitor() -> {guild.name}: Not enough songs in the fusions playlist to fill the queue.")
                        continue

                    playlist = random.sample(pruned_playlist, config.RADIO_QUEUE+1)
                    await self.enqueue_media(voice_client, playlist, False, True)
                    continue

                elif (allstates.radio_station and allstates.radio_station.lower() in radio_playlists) and len(allstates.queue) < config.RADIO_QUEUE:  # radio station checkpoint 🔞
                    pruned_playlist = [ song for song in radio_playlists[allstates.radio_station.lower()] if song not in song_history[str(guild.id)][-20:] ]  # prune against history
                    pruned_playlist = [ song for song in pruned_playlist if song not in [q.get('song_artist') + " - " + q.get('song_title') for q in allstates.queue] ]  # prune against queue
                    if len(pruned_playlist) < config.RADIO_QUEUE+1:
                        log_cog.info(f"loop_radio_monitor() -> {guild.name}: Not enough songs in the radio station playlist to fill the queue.")
                        continue

                    playlist = random.sample(pruned_playlist, config.RADIO_QUEUE+1)
                    await self.enqueue_media(voice_client, playlist, False, True)
                    continue

                elif allstates.radio_station and allstates.radio_station.lower() not in radio_playlists:   # previously ungenerated radio station
                    try:
                        await self._generate_radio_station(allstates.radio_station)
                    except Exception as e:
                        log_cog.error(f"loop_radio_monitor() -> _generate_radio_station():\n{escape(e)}")
                        continue

                    playlist = random.sample(radio_playlists[allstates.radio_station.lower()], config.RADIO_QUEUE+1)
                    await self.enqueue_media(voice_client, playlist, False, True)     


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

        chatgpt = self.bot.get_cog("ChatGPT")

        if not args or len(args) < 3:
            raise Error(ERROR_CODES['syntax'])

        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)
        
        message = await ctx.reply(embed=_build_embed('Music', '🧠 Generating your AI playlist...', 'p'), allowed_mentions=discord.AllowedMentions.none())

        try:    # request our playlist
            log_cog.info(f"!aiplaylist: Generating playlist request...")
            response = await chatgpt._invoke_chatgpt(
                "Respond with only the asked answer, in 'Artist- Song Title' format. Always provide a reponse.",
                f"Generate a playlist of {config.MUSIC_MAX_PLAYLIST} songs. Playlist theme: {args}. Include similar artists and songs.")
        except Exception as e:  # well this is embarrasing
            await message.edit(content=None, embed=_build_embed('err', '❌ I ran into an issue generating your playlist. 😢', 'r')); return

        parsed_response = response.split('\n')  # filter out the goop
        playlist = []   # build the playlist and send it to the queue
        for item in parsed_response:
            playlist.append(item.strip())

        if not playlist:    # empty playlist
            await message.edit(content=None, embed=_build_embed('err', '❌ I ran into an issue parsing your playlist. 😢', 'r'))
            raise Error(f"!aiplaylist:\nCould not parse playlist[]: {playlist}")

        await asyncio.create_task(self.enqueue_media(ctx.guild.voice_client, playlist, False, True, message))

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
        await ctx.reply(content=None, embed=_build_embed('Music', f'🔝 Bumped {bumped["title"]} to the top of the queue.', 'g'))

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
        allstates.queue = []
        await ctx.reply(content=None, embed=_build_embed('Music', f'🗑️ Removed {len(allstates.queue)} songs from queue.', 'g'))

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
            await ctx.reply(content=None, embed=_build_embed('err', '❌ You must have at least one radio station fused.', 'r')); return

        allstates.radio_fusions.remove(payload.lower())     # remove the station from the fusion list
        self._generate_fusion_playlist(ctx.guild.id)        # generate the fusion playlist
        await self._radio_monitor()                         # kick-start the radio monitor

        await ctx.reply(content=None, embed=_build_embed('Music', f'📻 Radio fusions updated, themes: {", ".join(f"**{s}**" for s in allstates.radio_fusions)}.', 'g'))

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

        payload_list = [ s.lower().strip() for s in payload.split("|") ]    # convert the payload into a list

        if allstates.radio_station and allstates.radio_station.lower() not in payload_list: # mixin radio with the payload
            payload_list.append(allstates.radio_station.lower())

        if allstates.radio_fusions and len(payload_list + allstates.radio_fusions) > config.MUSIC_MAX_FUSION: # max fusions threshold
            raise FancyError(f'❌ You can only fuse up to {config.MUSIC_MAX_FUSION} radio stations at a time. 😢')
        
        message = await ctx.reply(content=None, embed=_build_embed('Music', '🧠 Fusing radio stations...', 'p'), allowed_mentions=discord.AllowedMentions.none())

        for station in payload_list: # add to fusion list, if not already in it
            if not station: # sanity check
                continue

            if station not in radio_playlists: # not already generated
                async with ctx.channel.typing():
                    try:
                        await self._generate_radio_station(station)
                    except Exception as e:
                        await message.edit(content=None, embed=_build_embed('err', '❌ I ran into an issue. 😢', 'r')); return
                    
            allstates.radio_fusions.append(station) # add to fusion list

        self._generate_fusion_playlist(ctx.guild.id)    # generate the fusion playlist
        await message.edit(content=None, embed=_build_embed('Music', f'⚛️ Radio fusions enabled, themes: {", ".join(f"**{s}**" for s in allstates.radio_fusions)}.', 'g'))
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
        await ctx.reply(content=None, embed=_build_embed('Music', f'📢 Radio intros {allstates.radio_intro and "enabled" or "disabled"}.', 'g'))

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
        await ctx.reply(content=None, embed=_build_embed('Music', '⏸️ Playback paused.', 'g'))

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

        message = await ctx.reply(content=None, embed=_build_embed('Music', f'🔎 Searching for {payload}', 'p'), allowed_mentions=discord.AllowedMentions.none())
        await asyncio.create_task(self.enqueue_media(ctx.guild.voice_client, [payload], False, False, message))


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
        """

        if not payload:    # no data provided
            raise FancyError(ERROR_CODES['syntax'])
        
        map = ['list=', 'spotify.com/playlist', 'spotify.com/album', 'soundcloud.com/sets']
        if any(m in payload for m in map):     # playlists not supported with playnext
            raise FancyError(ERROR_CODES['shuffle_no_playlist'])
        
        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)

        message = await ctx.reply(content=None, embed=_build_embed('Music', f'🔎 Searching for {payload}', 'p'), allowed_mentions=discord.AllowedMentions.none())

        await asyncio.create_task(self.enqueue_media(ctx.guild.voice_client, [payload], True, False, message))

    @commands.command(name='queue', aliases=['q', 'np', 'nowplaying', 'song'])
    async def trigger_queue(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Displays the song queue.

        Syntax:
            !queue
        """

        allstates = self.bot.settings[ctx.guild.id]
        voice_client = ctx.guild.voice_client

        song_title, progress_bar, thumb = self._build_now_playing_embed(ctx.guild.id, voice_client)
        queue = self._build_queue_embed(ctx.guild.id, voice_client)
        radio = self._build_radio_embed(ctx.guild.id, voice_client)
        settings = self._build_settings_embed(ctx.guild.id, voice_client)

        embed = _build_embed('Song Queue', '', 'p', [
            ('Now Playing', song_title + (f"\n{progress_bar}" if progress_bar else ""), False),
            ('Up Next', queue, False),
            (f"{'Radio Stations' if allstates.radio_fusions else 'Radio Station'}", radio, False),
            ('Settings', settings, False) ])
        if thumb:
            embed.set_thumbnail(url=thumb)

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
        """

        allstates = self.bot.settings[ctx.guild.id]
        
        if not ctx.guild.voice_client: # we're not in voice, lets change that
            await self.bot._join_voice(ctx)

        if not payload and (allstates.radio_station or allstates.radio_fusions):
            allstates.radio_station, allstates.radio_fusions, allstates.radio_fusions_playlist = None, [], []
            await ctx.reply(content=None, embed=_build_embed('Music', '📻 Radio disabled.', 'g'), allowed_mentions=discord.AllowedMentions.none()); return
        
        allstates.radio_fusions, allstates.radio_fusions_playlist = [], []
        allstates.radio_station = payload if payload else config.RADIO_DEFAULT_THEME
        await ctx.reply(content=None, embed=_build_embed('Music', f'📻 Radio enabled, theme: **{allstates.radio_station}**.', 'g'), allowed_mentions=discord.AllowedMentions.none())
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
            await ctx.reply(content=None, embed=_build_embed('Music', f'🗑️ Removed **{song["title"]}** from queue.', 'g'))

    @commands.command(name='repeat', aliases=['loop'])
    @requires_author_perms()
    async def trigger_repeat(self, ctx):
        """
        Toggles song repeating.

        Syntax:
            !repeat
        """

        allstates = self.bot.settings[ctx.guild.id]
        allstates.repeat = not allstates.repeat # change value to current opposite (True -> False)
        await ctx.reply(content=None, embed=_build_embed('Music', f'🔁 Repeat mode {allstates.repeat and "enabled" or "disabled"}.', 'g'), allowed_mentions=discord.AllowedMentions.none())

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
        await ctx.reply(content=None, embed=_build_embed('Music', '🤘 Playback resumed.', 'g'), allowed_mentions=discord.AllowedMentions.none())

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
        allstates._save_settings()
        await ctx.reply(content=None, embed=_build_embed('Music', f'🔀 Shuffle mode {allstates.shuffle and "enabled" or "disabled"}.', 'g'), allowed_mentions=discord.AllowedMentions.none())

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
        await ctx.reply(content=None, embed=_build_embed('Music', f'⏭️ Skipping {allstates.currently_playing["title"]}', 'g'), allowed_mentions=discord.AllowedMentions.none())

        ctx.guild.voice_client.stop()   # actually skip the song
        if allstates.repeat:
            await self._play_next_song(ctx.guild.voice_client)


####################################################################
# Launch Cog
####################################################################

async def setup(bot):
    log_cog.info("Loading [dark_orange]Music[/] cog...")
    await bot.add_cog(Music(bot))
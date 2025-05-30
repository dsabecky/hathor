# Hathor

[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](#) [![Discord](https://img.shields.io/badge/Discord-Bot-blue.svg)](#) [![ChatGPT](https://img.shields.io/badge/ChatGPT-74aa9c?logo=openai&logoColor=white)](#)   [![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](#LICENSE)

**Hathor** is a free, fully-featured Discord music+AI bot built on `discord.py`, `gTTS`, `OpenAI`, and `yt-dlp`. It offers:

- Music playback from Soundcloud, Spotify, and YouTube
- Smart playlists via ChatGPT  
- Endless “radio” with fusion of multiple themes  
- In-voice DJ intros powered by gTTS or ChatGPT  
- Full queue management (shuffle, repeat, bump, remove)  
- ChatGPT chat & image generation/editing
- Optional Last.FM scrobbling

## Installation

### Environment Setup
```bash
git clone https://github.com/dsabecky/hathor.git
```
```bash
pip install discord.py gtts openai pylast pynacl rich yt_dlp
```

### Package Updates
Be sure to update the modules periodically (YoutubeDL patches frequently)
   ```bash
   pip install -U discord.py gtts openai pylast pynacl rich yt_dlp
   ```

### Configuration

Copy ```config.py.example``` to ```config.py```
   ```bash
   cp config.py.example config.py
   ```

Fill out your essential settings (links to aquire api keys included in config)
   ```python
   DISCORD_BOT_TOKEN      # your discord bot token
   OPENAI_API_KEY         # your openai api key
   SPOTIFY_CLIENT_ID      # your spotify api client key
   SPOTIFY_CLIENT_SECRET  # your spotify client secret key
   YOUTUBE_API_KEY        # your google api key

   BOT_ADMIN              # your userID for your personal discord account (don't use quotes)
   ```

### (Optional) Last.FM Scrobbling

Set the following in ```config.py```
   ```python
   LASTFM_API_KEY    # your lastfm api key
   LASTFM_API_SECRET # your lastfm api secret
   LASTFM_SERVER     # serverID you want to send scrobbles for
   ```

Run ```lastfm_session_gen.py``` with no arguments, and follow the directions
   ```bash
   python3 lastfm_session_gen.py
   ```

Run ```lastfm_session_gen.py``` with your temporary TOKEN
   ```bash
   python3 lastfm_session_gen.py TOKEN_GOES_HERE
   ```

Set your SESSION KEY in ```config.py```
   ```python
   LASTFM_SESSION_KEY
   ```

## Running

```bash
python3 hathor.py
```
## Commands
**Music**  
```
- !play <query|url>  
- !playnext <query|url>
- !aiplaylist <theme>
- !pause / !resume / !skip  
- !queue / !clear / !remove <#> / !bump <#>  
- !shuffle / !repeat
```

**Radio**
```
- !radio <theme> / !radio to toggle  
- !fuse <theme1> | <theme2> | …  
- !defuse <theme>  
- !intro
``` 

**AI**
```
- !chatgpt <prompt>
- !imagine <prompt>
- !gptimagine <prompt>  
- !gptedit <prompt> + image attachments
```

**Server Admin**
```
- !join / !leave
- !permissions [add | remove] [channel | role | user ] <ID>
- !volume <1-100>
```

**Bot Owner**
```
- !botservers
- !botleave
- !botsync
```

## Acknowledgements
- discord.py (https://github.com/Rapptz/discord.py)  
- OpenAI Python (https://github.com/openai/openai-python)  
- yt-dlp (https://github.com/yt-dlp/yt-dlp)  
- gTTS (https://github.com/pndurette/gTTS)
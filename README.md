# 🎵 Hathor

[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)](#)
[![Discord](https://img.shields.io/badge/Discord-Bot-blue.svg)](#)
[![ChatGPT](https://img.shields.io/badge/ChatGPT-74aa9c?logo=openai&logoColor=white)](#)
[![Docker](https://img.shields.io/badge/Docker-Hathor--Bot-blue?logo=docker&logoColor=white)](https://hub.docker.com/r/nothaldu/hathor)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](#LICENSE)

> A free, fully-featured Discord music+AI bot built on `discord.py`, `gTTS`, `OpenAI`, and `yt-dlp`.

**Hathor** offers:
- 🎶 Music playback from SoundCloud, Spotify & YouTube  
- 🤖 Smart playlists powered by ChatGPT  
- 🔀 Endless “fusion radio” blending multiple themes  
- 🎤 In-voice DJ intros via gTTS or ChatGPT  
- 📑 Full queue management (shuffle, repeat, bump, remove)  
- 💬 ChatGPT chat, image generation & editing  
- 🔗 Optional Last.FM scrobbling  

---

## 🚀 Installation

### 1. From Source

```bash
git clone https://github.com/dsabecky/hathor.git
cd hathor
pip install -r requirements.txt
```

### 2. From DockerHub

```bash
docker pull nothaldu/hathor:latest
docker run -d \
  --name hathor \
  --restart unless-stopped \
  -v /full/path/to/data:/app/data \
  -v /full/path/to/db:/app/db \
  -v /full/path/to/plugins:/app/plugins \
  nothaldu/hathor:latest
```

- `/app/data`    → your folder with `config.py` and JSON
- `/app/db`      → your folder for cached music or other persistent files
- `/app/plugins` → (optional) your folder with custom plugins

---

## ⚙️ Configuration

1. (**From Source only**) Copy the example config into your data folder:

   ```bash
   mkdir data
   cp config.py.example data/config.py
   ```

2. Edit **data/config.py**:

   ```python
   DISCORD_BOT_TOKEN      # Your Discord bot token
   OPENAI_API_KEY         # Your OpenAI API key
   SPOTIFY_CLIENT_ID      # Your Spotify client ID
   SPOTIFY_CLIENT_SECRET  # Your Spotify client secret
   YOUTUBE_API_KEY        # Your Google API key

   BOT_ADMIN              # Your Discord user ID (no quotes)
   ```

### 🔗 (Optional) Last.FM Scrobbling

In **data/config.py** add:

```python
LASTFM_API_KEY    # Your Last.FM API key
LASTFM_API_SECRET # Your Last.FM API secret
LASTFM_SERVER     # The server ID to scrobble for
```

Then generate your session key:

```bash
python3 lastfm_session_gen.py
# Follow prompts, then:
python3 lastfm_session_gen.py TOKEN_FROM_PREVIOUS_STEP
# Copy SESSION_KEY back into data/config.py
```

---

## ▶️ Running

### From Source

```bash
python3 hathor.py
```

### Via Docker (already shown above)

---

## 💬 Commands

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

---

## 🙏 Acknowledgements

- [discord.py](https://github.com/Rapptz/discord.py)  
- [OpenAI Python](https://github.com/openai/openai-python)  
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)  
- [gTTS](https://github.com/pndurette/gTTS)  

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more details.
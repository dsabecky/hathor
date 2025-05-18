# Hathor

[![Discord](https://img.shields.io/badge/Discord-Bot-blue.svg)](#)  [![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](#LICENSE)

**Hathor** is a free, fully-featured Discord music+AI bot built on `discord.py`, `gTTS`, `OpenAI`, `PyNaCl`, and `yt-dlp`. It offers:

- Music playback from YouTube & Spotify  
- Smart playlists via ChatGPT  
- Endless “radio” with fusion of multiple themes  
- In-voice DJ intros powered by gTTS or ChatGPT  
- Full queue management (shuffle, repeat, bump, remove)  
- ChatGPT chat & image generation/editing  

## Features
- `!play`, `!pause`, `!skip`, `!resume`, `!queue`, `!clear`, `!remove`, `!shuffle`, `!repeat`  
- `!radio <theme>` endless radio with AI-generated playlists  
- `!fuse <theme1> | <theme2> …` mix multiple radio themes  
- `!aiplaylist <theme>` create 10–50 song smart playlists  
- DJ voice intros (customizable “radio intro”)  
- ChatGPT text chat (`!chatgpt`)
- GPT-Image generation (`!imagine`), ChatGPT prompted GPT-Image generation (`!gptimagine`), image edits (`!gptedit`)  
- Per-guild settings with persistence (JSON backing)

## Installation
```bash
git clone https://github.com/you/hathor.git
cd hathor
pip install discord.py gtts openai pynacl yt_dlp
```

## Configuration

1. Copy the example config:  
   ```bash
   cp config.example.py config.py
   ```  
2. Fill in your keys & settings in `config.py`:
(links to aquire api keys included in config)
   ```python
   BOT_TOKEN           = "your discord bot token"
   BOT_OPENAI_KEY      = "your openai api key"
   BOT_SPOTIFY_CLIENT  = "your spotify api client key"
   BOT_SPOTIFY_SECRET  = "your spotify client secret key"
   BOT_YOUTUBE_KEY     = "your google api key"

   BOT_ADMIN           = "your user accounts discord id"
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
- !aiplaylist <theme>  
- !gptimagine <prompt>  
- !gptedit <prompt> + image attachments
```

## Acknowledgements
- discord.py (https://github.com/Rapptz/discord.py)  
- OpenAI Python (https://github.com/openai/openai-python)  
- yt-dlp (https://github.com/yt-dlp/yt-dlp)  
- gTTS (https://github.com/pndurette/gTTS)
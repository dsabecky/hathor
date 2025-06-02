import sys
import hashlib
import requests
from data.config import LASTFM_API_KEY, LASTFM_API_SECRET

if not LASTFM_API_KEY or not LASTFM_API_SECRET:
    print("Error: LASTFM_API_KEY and LASTFM_API_SECRET must be set in config.py")
    sys.exit(1)

if len(sys.argv) != 2:
    print(
        "Usage: python3 lastfm_session_gen.py LASTFM_TOKEN\n\n"

        f"You can get a token from https://www.last.fm/api/auth/?api_key={LASTFM_API_KEY}\n"
        "Then copy the token from the URL bar (it will look like '?token=mTGYsbs2356GBbbsz_z')"
    )
    sys.exit(1)

TOKEN = sys.argv[1]

# Build the API signature
string_to_sign = (
    f"api_key{LASTFM_API_KEY}"
    f"methodauth.getSession"
    f"token{TOKEN}"
    f"{LASTFM_API_SECRET}"
)
api_sig = hashlib.md5(string_to_sign.encode("utf-8")).hexdigest()

params = {
    "method": "auth.getSession",
    "api_key": LASTFM_API_KEY,
    "token": TOKEN,
    "api_sig": api_sig,
    "format": "json"
}

response = requests.get("https://ws.audioscrobbler.com/2.0/", params=params)
data = response.json()

if "session" in data and "key" in data["session"]:
    print("Session key:", data["session"]["key"])
else:
    print("Error getting session key:", data)

#!/usr/bin/env bash
set -e

# check for config/save folder
if [ ! -d "/app/data" ]; then
  printf "cannot find /app/data! Please mount a volume to /app/data"
  exit 1

# check for our music cache folder
elif [ ! -d "/app/db" ]; then
  printf "cannot find /app/db! Please mount a volume to /app/db"
  exit 1

# check for config file
elif [ ! -f "/app/data/config.py" ]; then
  printf "Generating missing config.py file...\n"
  cp /app/config.py.example /app/data/config.py
  exit 1
fi

# check for optional plugins folder
if [ -d "/app/plugins" ]; then
  touch /app/plugins/__init__.py
fi

# check for updates
touch /app/data/__init__.py
pip install --no-cache-dir -U  -r requirements.txt

exec "$@"
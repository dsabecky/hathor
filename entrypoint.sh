#!/usr/bin/env bash
set -e

if [ ! -d "/app/data" ]; then # check for config/save folder
  printf "cannot find /app/data! Please mount a volume to /app/data"
  exit 1

elif [ ! -d "/app/db" ]; then # check for our music cache folder
  printf "cannot find /app/db! Please mount a volume to /app/db"
  exit 1

elif [ ! -f "/app/data/config.py" ]; then # check for config file
  printf "Generating missing config.py file...\n"
  cp /app/config.py.example /app/data/config.py
  exit 1
fi

if [ -d "/app/plugins" ]; then # check for optional plugins folder
  touch /app/plugins/__init__.py
fi

touch /app/data/__init__.py
pip install --no-cache-dir -U  -r requirements.txt # check for updates

exec "$@"
#!/usr/bin/env bash
set -e

# check for config/save folder
if [ ! -d "/app/data" ]; then
  printf "⚠️ cannot find /app/data! Please mount a volume to /app/data"
  exit 1

# check for our music cache folder
elif [ ! -d "/app/db" ]; then
  printf "⚠️ cannot find /app/db! Please mount a volume to /app/db"
  exit 1

# check for config file
elif [ ! -f "/app/data/config.py" ]; then
  printf "🔄 Generating default config.py file…\n"
  cp /app/config.py.example /app/data/config.py
  exit 1
fi

# check for optional plugins folder
if [ -d "/app/plugins" ]; then
  touch /app/plugins/__init__.py

  # install plugin dependencies
  if [ -f "/app/plugins/requirements.txt" ]; then
    printf "🔄 Checking for plugin dependency updates…\n"
    pip install -U -r /app/plugins/requirements.txt --no-cache-dir  --quiet --root-user-action ignore
  fi
fi

# check for updates
touch /app/data/__init__.py
printf "🔄 Checking for core dependency updates…\n"
pip install --no-cache-dir -U  -r requirements.txt --quiet --root-user-action ignore

exec "$@"
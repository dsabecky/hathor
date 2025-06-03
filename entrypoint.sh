#!/usr/bin/env bash
set -e

if [ ! -f "/app/data/config.py" ]; then
  printf "Generating missing config.py file...\n"
  cp /app/config.py.example /app/data/config.py
  touch /app/data/__init__.py

  printf "Please edit the config.py and try again."

  exit 1
fi

# check for updates
pip install --no-cache-dir -U  -r requirements.txt

exec "$@"
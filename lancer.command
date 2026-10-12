#!/bin/bash
# Double-cliquez sur ce fichier (macOS) pour lancer l'application
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/python app.py

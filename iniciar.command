#!/bin/bash
# Doble clic para abrir la app de finanzas.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Primera vez: instalando (1-2 minutos)..."
  python3 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements.txt
else
  . .venv/bin/activate
fi
mkdir -p ~/.streamlit; [ -f ~/.streamlit/credentials.toml ] || printf '[general]\nemail = ""\n' > ~/.streamlit/credentials.toml
streamlit run app.py

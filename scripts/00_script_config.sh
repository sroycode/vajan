#!/bin/bash
# ==============================================================================
#  00_script_config.sh : Environment & Python Path Initialization
# ==============================================================================

# Locate virtual environment: check local first, fallback to sibling project if available
if [ -d "venv" ]; then
    export MY_VENV="venv"
elif [ -d "../bahiranan/venv" ]; then
    export MY_VENV="../bahiranan/venv"
else
    export MY_VENV="${MY_VENV:="venv"}"
fi

# Locate profile/credentials: check local first, fallback to sibling project
if [ -f ".env.local" ]; then
    export MY_PROF=".env.local"
elif [ -f "../bahiranan/.env.local" ]; then
    export MY_PROF="../bahiranan/.env.local"
else
    export MY_PROF="${MY_PROF:=".env.local"}"
fi

if [ "`uname`" = "Darwin" ] ; then
    export DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:-}:/opt/homebrew/lib:${MY_VENV}/lib"
fi

if [ -d "${MY_VENV}" ]; then
    source "${MY_VENV}/bin/activate"
fi

if [ -f "${MY_PROF}" ]; then
    source "${MY_PROF}"
else
    echo "[!] Warning: Profile ${MY_PROF} missing. Ensure VASTAI_KEY or VAST_API_KEY is set."
fi

export PYTHONPATH="./src:${PYTHONPATH:-}"

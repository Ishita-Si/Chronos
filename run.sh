#!/usr/bin/env bash
# CHRONOS launcher (macOS / Linux)
# Builds the plant memory if needed, then starts the app.
set -e
cd "$(dirname "$0")"

echo "Building CHRONOS plant memory..."
python3 -m chronos.pipeline

echo "Starting CHRONOS server on http://127.0.0.1:8000 ..."
python3 -m chronos.server

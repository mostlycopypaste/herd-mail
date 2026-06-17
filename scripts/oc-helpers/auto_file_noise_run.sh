#!/bin/bash
# Wrapper script for auto-file-noisy-senders cron job

cd /Volumes/RayCue-Drive/Documents/openclaw/.openclaw/workspace || exit 1
source ~/.openclaw-primary/agents/oc/agent/.env
exec python3.13 scripts/auto_file_noise.py

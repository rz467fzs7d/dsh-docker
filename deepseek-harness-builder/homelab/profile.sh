#!/bin/sh
# Debian resets PATH for login shells; keep the isolated Skill runtime available.
PATH="/opt/homelab-venv/bin:${PATH}"
export PATH

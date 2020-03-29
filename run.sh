#!/bin/sh
chown -R $UID:$GID /bot
exec su-exec $UID:$GID /sbin/tini -- python3 /bot/bot.py

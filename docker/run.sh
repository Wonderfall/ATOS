#!/bin/sh
chown -R $UID:$GID /bot
if [ ! -z $TZ ]; then cp /usr/share/zoneinfo/$TZ /etc/localtime; fi
exec su-exec $UID:$GID /sbin/tini -- python3 /bot/bot.py

FROM alpine

ENV UID=1000 GID=1000 TZ=Europe/Berlin

WORKDIR /bot

RUN apk -U upgrade \
 && apk add python3 python3-dev build-base su-exec tini tzdata \
 && pip3 install --no-cache discord.py pychal python-dateutil apscheduler PyYAML babel \
 && cp /usr/share/zoneinfo/Europe/Berlin /etc/localtime \
 && apk del build-base && rm -rf /var/cache/apk/*

COPY run.sh /usr/local/bin/run.sh
COPY bot.py /bot/bot.py

RUN chmod +x /usr/local/bin/run.sh

VOLUME /bot/data

CMD ["run.sh"]

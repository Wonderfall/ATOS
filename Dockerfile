FROM python:3.8-alpine

ENV UID=1000 GID=1000

WORKDIR /bot

COPY requirements.txt .

RUN apk -U upgrade \
 && apk add build-base git libffi-dev su-exec tini tzdata \
 && pip3 install --no-cache -r requirements.txt \
 && apk del build-base git libffi-dev && rm -rf /var/cache/apk/*

COPY docker/run.sh /usr/local/bin/run.sh

COPY bot.py .
COPY utils ./utils
COPY cogs ./cogs
COPY loc ./loc

RUN chmod +x /usr/local/bin/run.sh

VOLUME /bot/data /bot/config

CMD ["run.sh"]

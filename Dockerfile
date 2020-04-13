FROM alpine:3.11

ENV UID=1000 GID=1000

WORKDIR /bot

COPY requirements.txt .

RUN apk -U upgrade \
 && apk add python3 python3-dev build-base su-exec tini tzdata \
 && pip3 install --no-cache -r requirements.txt \
 && apk del build-base && rm -rf /var/cache/apk/*

COPY docker/run.sh /usr/local/bin/run.sh
COPY bot.py /bot/bot.py

RUN chmod +x /usr/local/bin/run.sh

VOLUME /bot/data /bot/config

CMD ["run.sh"]

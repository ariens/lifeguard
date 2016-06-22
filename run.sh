#!/bin/sh

export LIFEGUARD_CFG_FILE=settings.cfg
./python/bin/uwsgi --enable-threads --master --honour-stdin --uid 503 --socket 127.0.0.1:5000  -w WSGI:app

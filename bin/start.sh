#!/bin/sh

export LIFEGUARD_CFG_FILE=settings.cfg
export PYTHONPATH=/srv/flask_apps/lifeguard

/srv/flask_apps/lifeguard/python/bin/uwsgi \
--master \
--pidfile2 /srv/flask_apps/lifeguard/run/lifeguard.pid \
--daemonize2 /srv/flask_apps/lifeguard/log/lifeguard.log \
--enable-threads \
--processes 10 \
--uid 503 \
--socket 127.0.0.1:5000 \
-w WSGI:app

#!/bin/sh
# usage: run.sh [--rw-video] [--out DIR] <main.py args...>
# Runs at the lowest priority: cpu-shares 64 (relative to other containers' 1024), nice 19, idle I/O class.
V="/volume1/video:/video:ro"; X=""
while [ "$1" = "--rw-video" ] || [ "$1" = "--out" ]; do
  if [ "$1" = "--rw-video" ]; then V="/volume1/video:/video"; shift; else X="-v $2:/out"; shift 2; fi
done
exec docker run --rm --user 0 --cpu-shares 64 -v "$V" -v /volume1/docker/subsync:/state -v /volume1/docker/subsync-tools:/t $X \
  --entrypoint nice chryses/subsyncarr-ng -n 19 ionice -c3 /home/node/.local/pipx/venvs/ffsubsync/bin/python /t/subsyncd/main.py "$@"

#!/bin/sh
# Starts the always-on service: web page (port 8742), new-file watcher, nightly backlog run. Writes subtitles into /volume1/video.
# NOT started by anything yet; run it by hand once. Stop with: docker rm -f subsyncd
# Same low-priority settings as run.sh. The engine is a provisional default until the e03 check.
ENGINE="${1:-drift}"
exec docker run -d --name subsyncd --restart unless-stopped --user 0 --cpu-shares 64 -p 8742:8742 \
  -v /volume1/video:/video -v /volume1/docker/subsync:/state -v /volume1/docker/subsync-tools:/t \
  --entrypoint nice chryses/subsyncarr-ng -n 19 ionice -c3 /home/node/.local/pipx/venvs/ffsubsync/bin/python /t/subsyncd/main.py service --apply --engine "$ENGINE"

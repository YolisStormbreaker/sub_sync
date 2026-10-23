#!/bin/sh
# Starts the subsyncd container if it is not running (a no-op while it runs or when it was removed on purpose).
[ "$(docker inspect -f '{{.State.Running}}' subsyncd 2>/dev/null)" = "true" ] || docker start subsyncd >/dev/null 2>&1
exit 0

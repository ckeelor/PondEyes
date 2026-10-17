#!/bin/bash
# Open the PondEyes screen running on a Pi, from the Mac.
# Usage: deploy/view_from_mac.sh [host]     (default host: pi-radar-z2)
#
# Forwards Mac port 5901 -> the Pi's VNC on 5900. Not 5900 on the Mac side: macOS's own
# Screen Sharing already listens there when it's turned on.
HOST="${1:-pi-radar-z2}"
LOCAL_PORT="${LOCAL_PORT:-5901}"
if ! nc -z localhost "$LOCAL_PORT" 2>/dev/null; then
    ssh -fN -o ExitOnForwardFailure=yes -L "$LOCAL_PORT:localhost:5900" "chris@$HOST" || exit 1
fi
open "vnc://localhost:$LOCAL_PORT"

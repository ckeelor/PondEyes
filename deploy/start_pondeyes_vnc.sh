#!/bin/bash
# Start PondEyes on a virtual screen (:99) and share it over VNC on localhost:5900.
# Run by deploy/pondeyes.service at boot; can also be run by hand on the Pi.
# View from the Mac with deploy/view_from_mac.sh.
cd "$(dirname "$0")/.."
export DISPLAY=:99
export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-dummy}"   # Pi has no sound output; don't crash on it

if ! pgrep -f "Xvfb :99" >/dev/null; then
    Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
    for _ in $(seq 1 20); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.5; done
fi
pgrep -x x11vnc >/dev/null || x11vnc -display :99 -localhost -forever -shared -nopw -quiet -bg

exec venv/bin/python main.py "$@"

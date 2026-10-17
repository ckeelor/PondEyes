#!/bin/bash
# Start PondEyes on a virtual screen (:99), shared over VNC (localhost:5900) and in a
# browser via noVNC (127.0.0.1:6080).
# Run by deploy/pondeyes.service at boot; can also be run by hand on the Pi.
# View from the Mac with deploy/view_from_mac.sh.
cd "$(dirname "$0")/.." || exit 1
export DISPLAY=:99
export SDL_AUDIODRIVER="${SDL_AUDIODRIVER:-dummy}"   # Pi has no sound output; don't crash on it

if ! pgrep -f "Xvfb :99" >/dev/null; then
    Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
    for _ in $(seq 1 20); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.5; done
fi
# macOS Screen Sharing won't sign in with a blank password, so use ~/.vnc/passwd when it
# exists (create it once with `x11vnc -storepasswd`; never commit it).
if [ -f "$HOME/.vnc/passwd" ]; then VNC_AUTH=(-rfbauth "$HOME/.vnc/passwd"); else VNC_AUTH=(-nopw); fi
pgrep -x x11vnc >/dev/null || x11vnc -display :99 -localhost -forever -shared "${VNC_AUTH[@]}" -quiet -bg

# Browser viewer (noVNC) on 127.0.0.1:6080 only; Tailscale Serve publishes it to the
# tailnet as https://<host>.<tailnet>.ts.net/ (see README). Never bound to the LAN.
# noVNC ships no index page, so serve it from a scratch dir that adds ours.
WEB_DIR=/tmp/pondeyes-novnc
mkdir -p "$WEB_DIR" && ln -sfn /usr/share/novnc/* "$WEB_DIR"/ && cp deploy/novnc-index.html "$WEB_DIR/index.html"
ss -Hltn "sport = :6080" | grep -q . || websockify --web "$WEB_DIR" 127.0.0.1:6080 localhost:5900 >/dev/null 2>&1 &

exec venv/bin/python main.py "$@"

#!/bin/bash
# Open the PondEyes screen running on a Pi, in the Mac's default browser.
# Usage: deploy/view_from_mac.sh [host]     (default host: pi-radar-z2)
#
# The Pi serves a browser viewer (noVNC) that Tailscale Serve publishes tailnet-only at
# https://<host>.<tailnet>.ts.net/ -- any device on the tailnet (iPhone too) can open it.
HOST="${1:-pi-radar-z2}"
TAILNET="${TAILNET:-tail5dfe80.ts.net}"
open "https://$HOST.$TAILNET/"

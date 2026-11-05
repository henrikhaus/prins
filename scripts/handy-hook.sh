#!/bin/sh
# Handy runs this after every transcription. It writes the text to stdin and pastes our stdout.
#
# Prins decides: text from the device's talk button becomes notes and nothing is pasted,
# while text from Handy's own hotkey comes back unchanged and pastes as normal.
#
# If anything fails, print the original text. Dictation must keep working when Prins is off.
# Handy gives hooks a minimal PATH, so every tool needs an absolute path.

TEXT=$(/bin/cat)
TOKEN=$(/bin/cat "${PRINS_HOME:-$HOME/.prins}/token" 2>/dev/null)

if RESPONSE=$(printf '%s' "$TEXT" | /usr/bin/curl --silent --fail --max-time 3 \
    --header "X-Prins-Token: $TOKEN" \
    --data-binary @- \
    "http://127.0.0.1:${PRINS_HTTP_PORT:-8737}/v1/handy/hook"); then
    printf '%s' "$RESPONSE"
else
    printf '%s' "$TEXT"
fi

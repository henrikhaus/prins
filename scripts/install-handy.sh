#!/bin/sh
# Installs Handy, the open-source dictation app, and connects it to Prins.
# The Homebrew cask is community-maintained. Handy's GitHub releases are the official source.
set -eu

if [ ! -d /Applications/Handy.app ]; then
    brew install --cask handy
fi

"$(dirname "$0")/../.venv/bin/prins" install-hook

cat <<'EOF'

Now open Handy once and do these by hand, since macOS requires it:
  1. Grant Microphone and Accessibility permission when asked.
  2. Download a model. Parakeet V3 is a good start.
  3. Keep Handy running. The talk button starts and stops it.

Then run: prins doctor
EOF

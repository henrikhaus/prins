# Dictation: why Handy

**Handy is the open-source Wispr Flow alternative this project uses.** It's a desktop app that records, transcribes on-device and pastes into whichever app has focus.

It won for three reasons:
1. It has the two integration points a physical button needs: a command-line toggle to start and stop recording from outside the app, and a transcription hook to get the text back.
2. It runs fully offline, so audio stays on the machine, which helps when selling to office workers.
3. It's MIT licensed and the most active project in the category.

Checked on GitHub on 2026-11-05: 37,627 stars, MIT, v0.10.0 released 2026-11-02, the CLI and hook both documented in that release's README.

| Project | License | Runs | Stack and platforms | Why not |
|---|---|---|---|---|
| **Handy** | MIT | Local | Tauri, Mac, Windows, Linux | Chosen |
| OpenWhispr | MIT | Local or your cloud keys | Electron, Mac, Windows, Linux | Fine alternative, heavier. Didn't check for a hook |
| VoiceInk | GPL-3.0 | Local | Native Mac | GPL is awkward if you ever ship it in a product |
| Hex | MIT | Local | Apple Silicon Mac | Mac only |

Star counts and details for the others come from comparison blogs, so check them before relying on them.

## How it connects

```
Hold blue    ► Handy --toggle-transcription   starts recording
Release      ► Handy --toggle-transcription   stops, transcribes on-device
Handy        ► hooks/transcription (scripts/handy-hook.sh) sends the text to Prins
Prins        ► was this from the button?
                 yes: the text becomes notes, and the hook prints nothing, so nothing pastes
                 no:  the hook prints the text unchanged, so it pastes as normal
```

You get both products from the same app. **Handy's own hotkey is the Wispr Flow experience** of dictating into any app, while the blue button creates notes. A tap shorter than 0.25 s is cancelled as an accident.

## What isn't proven yet

Handy isn't installed on this Mac, so the code has only been tested with a stand-in binary and the real hook script.

- **Whether a second launch forwards the toggle fast enough.** Handy forwards the flag to the running app, but the launch adds delay, and your first word could get clipped. If it does, have the screen say "Listening" slightly later, or open the mic earlier.
- **Mic location.** Dictation uses the Mac's mic, not the Atech mic module. That module records at most 10 seconds into memory, and streaming audio over the board's USB link hasn't been tried.

## Licensing

Handy's MIT grant excludes its name, logo and brand assets. Running it alongside Prins is fine, but if you bundle or fork it into your product, it needs your own branding. Keep its license notice.

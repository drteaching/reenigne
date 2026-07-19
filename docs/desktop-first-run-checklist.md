# Desktop release: first-run checklist (macOS)

Everything here needs a real machine. The automated tests cover the classifier
and the bundle contents; they cannot cover TCC, Gatekeeper, or notarisation,
because all three are properties of a signed artefact on a clean system.

Work through this before publishing a build.

---

## 1. Build

```sh
export CSC_LINK=...                     # base64 .p12 or file:// path
export CSC_KEY_PASSWORD=...
export APPLE_ID=...
export APPLE_APP_SPECIFIC_PASSWORD=...  # app-specific, not the account password
export APPLE_TEAM_ID=...                # 10 characters

scripts/package-desktop.sh mac
```

`package-desktop.sh` runs `verify-bundle.sh` at the end. It must print
**Bundle verification passed.** If it reports an ad-hoc signed helper, the
binary is missing from `build.mac.binaries` in `apps/desktop/package.json` —
fix that rather than re-signing by hand, or the next build regresses.

- [ ] `verify-bundle.sh` passes
- [ ] App Team ID matches `APPLE_TEAM_ID`

## 2. Clean machine

Use a Mac (or VM) that has never run reenigne. A machine with an existing TCC
record will silently skip the prompts this whole checklist is about.

If you must reuse a machine, reset the records first:

```sh
tccutil reset ScreenCapture dev.reenigne.app
tccutil reset Microphone dev.reenigne.app
```

- [ ] Testing on a machine with no prior reenigne TCC records

## 3. Gatekeeper

Install from the `.dmg` — not by copying the `.app` out of `release/`, which
does not carry the quarantine attribute and therefore does not test Gatekeeper
at all.

```sh
spctl -a -vv /Applications/reenigne.app
```

Expect `accepted` and `source=Notarized Developer ID`. Anything else means the
notarisation ticket did not staple, and users will see the "cannot be opened"
dialog.

- [ ] `spctl -a -vv` reports accepted / Notarized Developer ID
- [ ] App opens from Finder without a right-click → Open workaround

## 4. Permission prompts

Open the app. The Record tab should show the setup panel, because neither
permission is granted yet.

Press **Test permissions**.

- [ ] The microphone prompt names **reenigne** — not `ffmpeg`, not
      `reenigne-worker`, not `Electron`. A helper name here means a signature
      problem; go back to step 1.
- [ ] The screen-recording prompt names **reenigne**
- [ ] Denying both produces the "open System Settings" message, not a stack
      trace
- [ ] Both **Open … settings** buttons land on the correct pane
- [ ] Granting the microphone updates the panel without a restart
- [ ] Granting screen recording requires a relaunch, and the panel says so
- [ ] After both are granted and the app relaunched, the panel disappears
- [ ] Revoking screen recording in System Settings makes the panel reappear on
      next launch (state is read live, never cached)

## 5. Capture the real TCC denial string

**This step feeds code.** `FAILURE_PATTERNS` in
`packages/worker/src/reenigne/capture/preflight.py` is a documented best guess
at what ffmpeg prints when macOS refuses a capture. It has never been checked
against a live denial. Anything it fails to match is classified as
`other` — the user is told "unrecognised failure" instead of "grant access",
which is a recoverable problem presented as an unrecoverable one.

With screen recording **denied**, run the bundled ffmpeg directly and record
what it prints:

```sh
/Applications/reenigne.app/Contents/Resources/ffmpeg/ffmpeg \
  -f avfoundation -framerate 5 -i "1:0" -t 1 /tmp/tcc-probe.mp4
```

Repeat with the **microphone** denied and screen granted; the two produce
different output.

- [ ] Screen-denied stderr captured
- [ ] Microphone-denied stderr captured
- [ ] Any substring not already matched added to `FAILURE_PATTERNS`, with a
      test case in `packages/worker/tests/test_preflight.py` and a comment
      noting the macOS version it came from
- [ ] Re-run `pytest packages/worker` after editing

Keep the raw strings in the PR description. The patterns drift between macOS
releases, and the next person needs to know which version each one came from.

## 6. First real recording

- [ ] Record ~30 seconds of a real product with narration
- [ ] Report opens and the narration lines up with the screenshots
- [ ] No ffmpeg on the host `PATH` — confirm with `which ffmpeg`. A Homebrew
      copy on PATH will be used ahead of the bundled one and hides exactly the
      packaging bug this checklist exists to catch.

## 7. Missing-component behaviour

Move the bundled ffmpeg aside and launch:

```sh
mv /Applications/reenigne.app/Contents/Resources/ffmpeg/ffmpeg /tmp/
```

- [ ] The app says the install is broken and to reinstall — it must **not**
      suggest `brew install ffmpeg`, which would put an unsigned copy on PATH
      and reintroduce the prompt-misattribution bug
- [ ] Restore it afterwards

---

## Not covered by CI, and why

| Check | Why it cannot be automated here |
| --- | --- |
| Prompt attribution | Requires a signed bundle and a live TCC database |
| Gatekeeper acceptance | Requires notarised artefact on a quarantined install |
| Denial string matching | Requires macOS to actually refuse a capture |

CI covers the classifier's routing (`test_preflight.py`), the bundle's
contents and Team ID agreement (`verify-bundle.sh`), and the desktop
typecheck. Everything in the table above is a manual gate.

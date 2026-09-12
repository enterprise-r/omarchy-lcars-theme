# Compatibility and attribution

The full experience targets Omarchy 4 / Quattro's Quickshell shell and its
`qs.Commons`, `qs.Ui`, and plugin facade APIs. Tested locally against the
installed `4.0.0.alpha` desktop on 2026-09-12, with a 2560×1600 display at 2×
scaling. Multi-monitor sizing follows each widget's host bar surface; a real
multi-monitor setup and bottom-edge placement have not been tested.

The bundled clock, workspace, audio, network, Bluetooth, display and power
widgets are adaptations of the installed Omarchy components. Their internal
controls, keyboard handling, and panel logic remain upstream code. Their
manifests retain source-clone information where needed for service access.
The menu widget is a small launcher wrapper which opens the existing native
menu. Endcaps and perspective stars are custom components.

The upstream repository is https://github.com/omacom/omarchy (quattro branch).
The branch was at `31bd80daa4613ffdee995ac27467fce5a2990806` when the upstream
license was retrieved; this is a reference, not a claim that every locally
installed source file exactly matches that commit. See `OMARCHY-LICENSE`.

The animation uses a zero-width bar widget whose visual child is parented into
its host window's content item at a lower stacking order than the controls.
Future changes to that scene hierarchy or the plugin interfaces may require
an update. The normal theme-color check disables the effect with other palettes.

Screenshots and the animated bar are captures of the actual running packaged
widgets on a clean demo workspace; terminal content is illustrative.

The wallpaper was generated for this project with the built-in OpenAI image
generation tool. Its prompt is in `wallpaper-prompt.txt`. The repository includes
no official television frames, official Star Trek logos, extracted fonts, or
sound effects. Trademark names identify the inspiration, not an endorsement.

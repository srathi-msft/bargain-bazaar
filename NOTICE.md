# Third-party notices

Bargain Bazaar's own code is released under the [MIT License](LICENSE). It bundles the following third-party material.

## Sound effects

The voice reactions and shop sounds in `static/sfx/` are real recordings from the [Freesound](https://freesound.org) community, trimmed, faded and
loudness-normalised for the game. They are licensed by their authors under **CC BY 4.0** (attribution required) or **CC0 1.0** (no attribution
required, given anyway). The full table (title, author, licence and source link for every clip) is in
[static/sfx/CREDITS.md](static/sfx/CREDITS.md), and the running game shows the same credits on its `/credits` page, linked from the join screen.

If you redistribute the game or the sound sprite, keep that credit with it. This is the CC BY credit line:

> Sound effects by Alba MacKenna (Alba_Mac), TommasoMotteran, vikuserro, DWOBoyle, Benboncan, pfranzen, Harbour11 and sankalp under CC BY 4.0
> (https://creativecommons.org/licenses/by/4.0/), via Freesound.org. Edited for the game: trimmed, faded and loudness-normalised;
> "Sad Trombone.wav" sped up x1.15.

The recipe that rebuilds the sprite from the original recordings is `tools/sfx_sources.json` (run by `tools/build_sfx_sprite.py`).

## Python packages

The game depends on [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), [HTTPX](https://www.python-httpx.org/) and
[Segno](https://github.com/heuer/segno) (all permissively licensed; see `requirements.txt`). The development tools additionally use
[pytest](https://pytest.org/) and [Playwright](https://playwright.dev/python/). Their licences apply to them, not to this project.

## Artwork

Raju Anna's face and the shop are drawn in code (`static/avatar.js`, the CSS files) for this project. Item icons are standard Unicode emoji,
rendered by the viewer's system font.

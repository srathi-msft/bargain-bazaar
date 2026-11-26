# Contributing

Thanks for your interest in Bargain Bazaar! Issues and pull requests are welcome, whether it is a bug, a clearer doc, a new theme or a new language for the built-in lines.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). For security issues, see [SECURITY.md](SECURITY.md) and do not open a public issue.

## Getting set up

```bash
git clone https://github.com/srathi-msft/bargain-bazaar.git
cd bargain-bazaar
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q                                      # about 400 tests, no network, around 40 seconds
python -m app.main                                       # the game, with built-in lines (no AI account needed)
```

## Before you open a pull request

- **Run the tests** and add tests for behaviour you change. Tests use pytest and never need the network; the AI is replaced by mock services.
- **Keep the fairness rules intact.** They are the point of the design ([docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)) and each has tests:
  - only the Buy button can sell, and always at the price shown on the button;
  - the AI never sets a price, never sees a hidden number and never moves money;
  - the hidden floor is never breached, whatever a message or a model says;
  - hidden numbers never reach a browser, and everything a player types is rendered as plain text.
- **Touching prices, the referee or the difficulty?** Run `python tools/simulate.py 400` before and after, and paste both tables in the pull request. The game should still reward good haggling and still not be winnable by shouting or by a hijacked model.
- **Touching the UI?** Run `python tools/ui_check.py live http://localhost:8123 <hostkey>` against a running game (see the header of `tools/ui_check.py`) and attach a screenshot. The tool uses the installed Edge; set `BAZAAR_BROWSER=chrome` for Chrome.
- **Adding or changing a sound?** Keep the credit: add it to `tools/sfx_sources.json` and rebuild with `tools/build_sfx_sprite.py` so `static/sfx/CREDITS.md` stays in sync. Only use recordings whose licence allows redistribution (CC0 or CC BY).
- **Keep private data out.** Never commit `.env`, anything from `data/`, API keys, account names or real people's names (tests and fixtures use made-up ones).

## Ideas that would be great

- Built-in lines in more languages, and better language detection for them.
- More item sets and shop themes (a sweet shop, a book stall, a car showroom).
- Other model providers behind the same read-and-phrase interface in `app/voice.py`.
- Accessibility improvements on the player and host screens.
- A cross-platform start script to match `Start-Game.ps1`.

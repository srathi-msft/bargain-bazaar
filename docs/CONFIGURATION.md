# Configuration

Two files control the game:

- **`.env`** holds settings for your machine: which AI model to use, ports, the host key. Copy `.env.example` to `.env` (the Windows `Start-Game.ps1` does it for you on first run). It is git-ignored; never commit it. Real environment variables take precedence over `.env`.
- **`config/game.json`** holds the rules of the game: the shop, the items and prices, the wallet, the game length.

## `.env` reference

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `none` | `none`, `azure`, `claude` or `gemini` (see below) |
| `LLM_ENDPOINT` | | The service URL. Azure: `https://<resource>.cognitiveservices.azure.com`. Claude on Foundry: `https://<resource>.services.ai.azure.com/anthropic`. Defaults exist for Anthropic's API and for Gemini |
| `LLM_MODEL` | | Your Azure deployment name, or the Claude / Gemini model name |
| `AZURE_SUBSCRIPTION_ID` | | Azure only: the subscription that owns the resource (when you sign in with the Azure CLI) |
| `AZURE_ALLOWED_ACCOUNT` | | Azure only: the one account the app may use. It refuses to run the AI if the Azure CLI is signed in as anyone else, so a different account that happens to be signed in (a work account, say) is never used by mistake |
| `AZURE_OPENAI_REASONING_EFFORT` | | Reasoning models only: `minimal`, `low`, `medium` or `high`. Leave empty otherwise |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Azure OpenAI API version |
| `LLM_API_KEY` | | A key for whichever provider is selected. Each provider also reads its own variable: `AZURE_OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY`. A key for another provider is never picked up by mistake |
| `LLM_RPM` | `40` (the example file sets `400`) | The app's own cap on AI replies per minute; beyond it, built-in lines are used |
| `LLM_TIMEOUT_S` | `8` | Seconds a top-priority AI call may take before a built-in line is used |
| `PORT` | `8000` | Port the game listens on |
| `PUBLIC_URL` | | The link players use (shown in the QR code). `Start-Game.ps1` sets it when it creates a tunnel |
| `ADMIN_KEY` | random per start | The host key. `Start-Game.ps1` generates one and keeps it here; on other systems set a long random value so it survives restarts. Never share it |
| `DATA_DIR` | `./data` | Where `state.json` and the private turn log `events.jsonl` go |
| `RESUME` | | `1` loads the saved game from `DATA_DIR` at start |

## Choosing the AI model

The AI only talks, so any model, or none, keeps the game fair ([how it works](HOW-IT-WORKS.md)). Set `LLM_PROVIDER` and the variables for that provider, restart, then run:

```bash
python tools/ai_check.py 3
```

It sends realistic, multilingual and hostile customer messages and prints the pass rate, latency, whether the model reads reasons, manners and rivals' prices sensibly (and is not sweet-talked), and whether it answers in the shopper's language. Aim for replies of a few seconds; a slower one falls back to a built-in line.

### Azure OpenAI / Azure AI Foundry (`azure`)

Deploy a chat model in your Azure AI resource, then:

```ini
LLM_PROVIDER=azure
LLM_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com
LLM_MODEL=<your-deployment-name>
AZURE_SUBSCRIPTION_ID=<subscription-guid>
AZURE_ALLOWED_ACCOUNT=<the-account-you-az-login-with>
```

Run `az login` as that account. No keys are stored: the app asks the Azure CLI for a short-lived token for that one subscription. Alternatively set `LLM_API_KEY` (or `AZURE_OPENAI_API_KEY`) and skip the Azure CLI entirely. Size the deployment for your room: a rehearsal with 34 bots peaked at about 190 requests (370K tokens) a minute.

### Claude (`claude`)

On Azure AI Foundry (sign in with the Azure CLI, as above, with the `services.ai.azure.com/anthropic` endpoint), or directly from Anthropic:

```ini
LLM_PROVIDER=claude
LLM_MODEL=<claude-model-name>
ANTHROPIC_API_KEY=sk-ant-...
```

Claude on Foundry needs a subscription with a payment method, because Anthropic's Marketplace terms apply.

### Gemini (`gemini`)

```ini
LLM_PROVIDER=gemini
LLM_MODEL=<gemini-model-name>
GEMINI_API_KEY=...
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey). The free tier is too small for a full room; enable billing.

The Claude and Gemini adapters follow the vendors' documented REST APIs and are covered by tests against mock services. Run `tools/ai_check.py` once with real access before relying on them.

## `config/game.json`

```json
{
  "title": "BARGAIN BAZAAR",
  "shop_name": "Raju Anna Stores",
  "shopkeeper": "Raju Anna",
  "currency": "₹",
  "budget": 9200,
  "duration_min": 20,
  "max_players": 150,
  "sound": {"host": "on", "players": "on"},
  "items": [
    {"id": "backpack", "name": "Laptop Backpack", "emoji": "🎒", "list": 1999, "floor_min": 860, "floor_max": 1200}
  ],
  "difficulty": {}
}
```

| Field | Meaning |
|---|---|
| `title`, `shop_name`, `shopkeeper`, `currency` | Names and symbols shown in the UI. (The persona prompt and built-in lines in `app/voice.py` and `app/lines.py` are written for Raju Anna; see [Making it your own](#making-it-your-own)) |
| `budget` | Every player's wallet. The default is about 92% of the sticker total, so nobody can finish without haggling |
| `duration_min` | Default game length; the host can change it in the lobby |
| `max_players` | Cap on players |
| `sound` | Default level of the sound effects for the host screen and players: `on`, `soft` or `off` |
| `items[]` | `id` (a short unique id), `name`, `emoji`, `list` (the sticker price and his opening ask), and `floor_min` / `floor_max`: the range his hidden floor price is drawn from for each shopper. The game refuses to start unless `0 < floor_min <= floor_max < list` |
| `difficulty` | Optional overrides for any field of `Difficulty` in `app/referee.py` |

The most useful knobs in `difficulty`:

| Field | Default | Effect |
|---|---|---|
| `patience` | 5 | How many serious offers per item before he gives his final price |
| `kappa` | 0.50 | Average share of the gap he concedes per round at full-quality offers |
| `q_insult` | 0.58 | An offer below this share of his ask is a lowball: no movement, costs patience |
| `max_bumps`, `bump_lo`, `bump_hi`, `bump_over` | 3, 0.03, 0.06, 0.05 | How often and how far he puts a price up (as a share of the sticker, and how far above it) |
| `turn_cap` | 0.55 | One reply never gives away more than this share of the room he has left above his floor |
| `arg_budget` | 7.0 | Total credit a shopper can ever earn per item from reasons |
| `noise`, `p_stubborn`, `p_lucky` | 0.28, 0.10, 0.07 | How chaotic his mood is from reply to reply |

After changing prices, floors or difficulty, run `python tools/simulate.py 400`. It prints how different bargaining styles fare (mean discount, how many finish the bag) and how spread out the final totals are, so you can check the game still rewards good haggling and still cannot be won by shouting.

## Making it your own

- **Items and prices:** edit `config/game.json`. Keep floors well below the sticker price and the wallet below the sticker total.
- **Another shopkeeper or setting:** the persona and instructions the model receives are `_PERSONA` and the prompts in `app/voice.py`; the built-in lines (used with no AI) are in `app/lines.py`; his face is drawn in `static/avatar.js`; the shop and colours are in `static/*.css`. The tests mostly check the money and safety rules, so they are a good safety net while you retheme (a few of them check the built-in lines, and will tell you when you change those).
- **Sound:** every sound is a clip in `static/sfx/bazaar-sfx.mp3`, described by `bazaar-sfx.json`, with a synthesised fallback in `static/sfx.js`. To change one, edit `tools/sfx_sources.json` and run `python tools/build_sfx_sprite.py` (needs `pip install -r requirements-sfx.txt` and `ffmpeg`), then `python tools/sfx_check.py --tune`. Keep the credits for any clip you add; `static/sfx/CREDITS.md` is generated from the recipe.
- **Languages:** the built-in lines cover English and Hindi (Hinglish too); with an AI, he answers in whatever script the shopper writes in.

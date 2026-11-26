# Hosting a Bargain Bazaar game

Everything a host needs, from the first test run to the podium. The shortest version:

```powershell
.\Start-Game.ps1        # starts the game, a public link and the host screen; wait for the box with PLAYERS JOIN AT
# ... run the event ...
# Ctrl+C in that window stops the game and deletes the public link
```

On macOS or Linux, see [Without the Windows scripts](#without-the-windows-scripts).

## Before the event

**You need:** Python 3.10+, a computer that stays awake and plugged in for the whole game (the Windows script keeps it awake while it runs), a browser for the host screen, and a way for players to reach your computer (a tunnel, see below). An AI model is optional ([docs/CONFIGURATION.md](CONFIGURATION.md)).

**Do a dry run once, end to end, with one real outside person (about 25 minutes):**

1. Start a call with a colleague. Run `.\Start-Game.ps1` and wait for the box. A healthy start shows only `[ok]` lines and no `[warn]`.
2. Send them the link (it is already on your clipboard). Ideally they open it on a phone on mobile data, which is the worst case. First-time visitors of a Dev Tunnel see a page that says *You are about to connect to a developer tunnel*; they click **Continue** once. Then they pick a name (4+ characters).
3. Share the host screen: share only the browser window **Bargain Bazaar: Host screen**. Ask if they can read the QR code, the leaderboard and Raju Anna's lines.
4. Hover the bottom bar of the host screen, set *Game length* to 5, click **Open the shop**. Ask them to try a plain offer; an offer with a believable reason ("Amazon has it for 1500, can you do 1450?"); a friendly message; a lowball twice (the first makes his mood face turn Cold, the second puts the price **up**); a pushy one; a line in another language. When he *agrees* he says "press Buy" and the **Buy** button glows: nothing is sold until they tap it.
5. Click **Festive rush**, then **+2 min**, then **End game**. Check the podium and **Results**.
6. Ask what was confusing (the link, the Continue page, the rules, how fast Raju Anna answers). Then Ctrl+C.

Want a busy room without 30 friends? While a game is running, `.\Rehearse.ps1` in a second window fills the shop with 25 bots plus late joiners (English, Hinglish, Hindi and other languages, prompt tricks, market events). `.\Rehearse.ps1 -Bots 40 -Delay 2` is heavier; add `-ResetAfter` to wipe the rehearsal when done.

## Commands (Windows)

| Command | What it does |
|---|---|
| `.\Start-Game.ps1` | Python environment (first run), `.env`, a stable host key, pre-flight checks, a public Dev Tunnel link, the server and the host screen |
| `.\Start-Game.ps1 -Try` | Play it yourself: no public link, opens the host screen and two player tabs |
| `.\Start-Game.ps1 -NoTunnel` | Local only (dry runs and bot rehearsals) |
| `.\Start-Game.ps1 -Resume` | After a crash or restart: keep the players, bags and scores |
| `.\Start-Game.ps1 -NewKey` | Generate a new host key |
| `.\Stop-Game.ps1` | Stops the server and tunnel (only needed if you closed the window or something is stuck) |

The Dev Tunnel is created per run, signed in as the account shown by `devtunnel user show` (install with `winget install Microsoft.devtunnel`, sign in with `devtunnel user login`; add `-g` for a GitHub identity). No Azure subscription is involved.

### Without the Windows scripts

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then set ADMIN_KEY=<a long random string> so the host key survives restarts
python -m app.main                # prints the Players and Admin links
devtunnel host -p 8000 --allow-anonymous      # or ngrok / Cloudflare Tunnel; then set PUBLIC_URL=<that https link> in .env and restart
```

Keep the machine awake yourself (`caffeinate -i` on macOS, `systemd-inhibit` on Linux).

## On the day

| When | You do |
|---|---|
| 30 min before | Plug in. Run the start command and wait for the box. Don't share or click in the terminal window: it shows your host key. Click once on the host screen so the sound button says *Sound: On*. |
| 15 min before | Post a reminder. Glance at the host screen lobby: QR code and link are showing. |
| At the start | Paste the link in the meeting chat. If the clipboard changed, copy it from the top right of the host screen. Explain the rules in a minute (the host screen's lobby text and the player screens do most of the work). |
| Share | Share the browser window **Bargain Bazaar: Host screen**. To let everyone hear Raju Anna's sounds, switch on *Include computer sound* (Teams: *Include system audio*) and wear headphones, otherwise your microphone picks the sounds up twice. |
| Open | Hover the bottom bar, check *Game length* (20 minutes by default), click **Open the shop** (shutters and a bell). Late joiners can still join. |
| Play | Call out moments: a big drop after someone names a rival's price, "he raised it" after a lowball or shouting, mood faces, the live trades. |
| 0:00 | The shop closes by itself: podium, confetti and awards. Read them out. **Results** downloads everything as JSON. |
| After | Ctrl+C in the terminal window. `devtunnel list` should say *No tunnels found*. |

## Host controls

The bottom bar of the host screen is faint until you hover it. `H` hides it.

| Control | When | What it does |
|---|---|---|
| Game length + **Open the shop** | lobby | Starts the clock; every player's screen opens the shop |
| **Festive rush** / **Squeeze** | live | Raju Anna concedes more / less for 45 seconds. Two or three happen on their own in games of six minutes or more. **End event** stops one early |
| **+2 min** | live | Adds two minutes |
| **End game** | live | Closes the shop now (asks to confirm), then shows the podium |
| **Podium** / **Results** | ended | Shows the podium again / downloads `bargain-bazaar-results.json` |
| **Prices hidden / shown** | any | Hidden (default) masks exact rupee prices on the shared screen so nobody learns what others paid. Show them at the end if you like |
| **Test AI**, **AI replies ON/OFF** | any | Test checks the AI in a few seconds. OFF uses ready-made lines: instant, the game works the same, just less chatty |
| **Sound** (key `M`) / **Sound check** | any / not while live | Raju Anna's sounds: On, Soft or Off. Sound check plays each one with its name. The button pulses until the browser has had a first click, because browsers allow sound only after a click |
| **Players** | any | Remove someone |
| **New game** | any | Wipes everyone. Don't use it during the event |

## If something goes wrong

| Problem | Do this |
|---|---|
| `[warn]` about signing in for the AI | `az login` as the account in `AZURE_ALLOWED_ACCOUNT`, start again. The game still works without the AI |
| `[warn]` Public link did not answer | Wait 10 seconds and open it on your phone. Still nothing: Ctrl+C and start again (new link) |
| Someone can't open the link | They must click **Continue** on the tunnel page (once per device). Try another browser or phone; they can also just watch your shared screen |
| Replies slow or odd | **Test AI**. If it fails or the chip says *degraded*: **AI replies: OFF** |
| Others can't hear the sounds | Re-share with *Include computer sound* ticked, click once on the host screen, check the button says *Sound: On*, try **Sound check**. Too busy while you talk: *Soft* or *Off*. The game is the same without sound |
| Host screen says *Admin key required* or is blank | Open the `HOST SCREEN` link from the terminal box again (it has the key in it). The game itself is unaffected |
| Window closed, Ctrl+C by accident, or the game is truly stuck | `.\Stop-Game.ps1`, then `.\Start-Game.ps1 -Resume` (keeps bags and scores) and paste the **new** link. Every start makes a new public link, so shoppers must join again (a repeated name becomes "Name 2" with a fresh wallet). Avoid restarting if you can |
| `Port 8000 is already in use` | `.\Stop-Game.ps1`, then start again (or `-Port 8001`) |

## Capacity

Measured with the bundled bot swarm on one ordinary PC (the request rate for 30 players is an estimate):

- 40 live viewers plus 40 bots through the game server: about 1,100 requests in under two minutes, median 6 ms, 95th percentile 16 ms, no errors, about 3% of one CPU core.
- 40 phones opening a Dev Tunnel link at the same moment connected in about 0.4 s. A 30-player game makes roughly 150 to 250 requests a minute (more in the first minute while everyone joins), far below Dev Tunnels' published limits.
- AI replies take about 2 to 4 seconds. If one takes longer than `LLM_TIMEOUT_S` (8 seconds by default) or fails a check, a ready-made line is used instead; in rehearsals that was about 1 reply in 30, and prices are decided the same way either way.
- Sizing the model: a rehearsal with 34 bots (who talk more than people do) peaked at about 190 AI requests (370K tokens) per minute and stayed under a deployment limit of 600 requests and 600K tokens per minute. `LLM_RPM` in `.env` caps the app's own use.

## Privacy and housekeeping

- `data/state.json` and `data/events.jsonl` hold everything the players typed, plus Raju Anna's hidden floors. They are for the host only and are git-ignored. The **Results** download includes the chats. Delete `data/` when you no longer need it.
- Player names are shown as plain text on every screen. Anything else a shopper types is never interpreted as markup.
- The host key lives in `.env` (git-ignored) and in the Admin link. Do not show the terminal window or paste the Admin link anywhere. The admin page removes the key from the address bar after loading.
- Behind a tunnel every visitor looks like the same address, so there are no per-address limits. Ask for one player per person; use **Players** to remove duplicates or bots. Wrong host keys are throttled, and the right key always works.
- Stop the tunnel when the game is over (Ctrl+C does it).

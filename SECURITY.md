# Security policy

Bargain Bazaar is a party game meant to be hosted for a few minutes at a time, not a production service. Even so, its design
promises matter: the AI never decides a price, nothing a player types can sell anything, and hidden numbers never reach a browser
or the model ([how it works](docs/HOW-IT-WORKS.md)).

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability. Use GitHub's private reporting instead: open the **Security** tab of this
repository and choose **Report a vulnerability**. This is a personal project, so there is no formal response time, but reports are
read and taken seriously.

Things worth reporting:

- a way to get a discount, a sale or a hidden value (a floor price, a temperament, the host key) that the design says is impossible;
- script injection or markup injection through a player name, a chat message or the AI's replies;
- anything that lets a player read or change another player's game, or reach the host controls without the host key;
- anything that could harm a host or their players beyond the game itself.

Known limits that are *not* vulnerabilities (they are listed in [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md#known-limits)): Raju Anna's
wording being silly or imprecise, one person joining several times, and leaderboard totals being public by design.

## Hosting safely

- Keep `.env` and the host key private. Do not share your terminal window or paste the Admin link anywhere.
- `data/` contains everything players typed plus the hidden floors. Keep it private and delete it when you no longer need it.
- Stop the tunnel when the game is over.

# Gambly

Daily football prediction pipeline. Fetches today's matches, builds a
per-match prediction using match stats, an outside prediction site, and its
own history of past predictions vs results, then sends a parlay-style ticket
over Telegram for you to book yourself.

## What changed from v1

- **No more Apify.** `tools/fetch_all_matches.py` now scrapes flashscore.com
  directly with Playwright instead of paying per run for an Apify actor
  that was pulling the same publicly-visible data. `resources/apify_client.py`
  and the `APIFY_KEY` secret are gone.
- **Predictions now factor in footballwhispers.com's opinion** as one more
  input alongside the flashscore.com match overview - not a rule, just
  another signal the agent weighs itself.
- **A persistent feedback loop.** Every prediction and every graded result
  now lives forever in `predictions` / `results` tables (the old `matches`
  table is still wiped and rebuilt daily - it's just today's queue). Each
  run pulls a summary of past accuracy by market type before making new
  picks.
- **Results messages are now detailed**: HT/FT score, corners, cards, shots,
  and shots on target per team, scraped from flashscore.mobi.
- **Ticket generation now attempts real SportyBet booking codes** via a
  no-login, no-stake slip-builder - see below for exactly what's verified
  vs. still needs a live check.

## The SportyBet booking step

`tools/sportybet_client.py` drives SportyBet's "lite" interface (a plain-
HTML, low-JS mode - confirmed by fetching real pages) via a `requests`
session: clicking an odds value there is just a GET link that updates a
server-side slip tied to your session cookie, so building a slip needs no
JavaScript, no login, and no stake. `tools/book_ticket.py` orchestrates
this per prediction and degrades gracefully - any leg it can't confidently
match just gets flagged as "add manually" in the ticket message instead of
silently booked wrong or dropped.

What's actually verified (fetched real pages during development):

- The listing page's structure and its 1/X/2 (home/draw/away) link format
  - `add_home_draw_away` is built directly on this and is the
  highest-confidence path.
- That building/loading a slip needs no login (confirmed via the empty
  `/lite/betslip` page, which shows Register/Log In links *and* a working
  "insert booking code" field side by side).

What's still unverified, because I have no way to hold a live session open
and click through SportyBet from this environment:

- **`add_by_detail_page_text`** (anything beyond a straight home/draw/away
  pick - over/under lines, BTTS, double chance, corners, cards, exact
  score, player props) does a generic text search against the match detail
  page rather than trusting specific selectors I haven't seen. It returns
  `False` rather than guess when it's not confident, which is why some legs
  may show up as "add manually" in the ticket.
- **`get_booking_code`** - the actual "Share -> get a code" endpoint.
  I deliberately left this raising `NotImplementedError` with instructions
  rather than shipping a guessed endpoint, since a wrong guess here would
  silently hand you a fake code. To finish it: open SportyBet in a real
  browser, add a couple of selections, open devtools' Network tab, click
  Share, and fill in the real endpoint + response parsing.

Until `get_booking_code` is filled in, the ticket message will say "no
code was generated for this run" and list every pick for manual entry -
everything else in the pipeline works the same either way.

## Architecture

```
tools/fetch_all_matches.py        -> flashscore.com scrape of today's fixtures, filtered to configured leagues
helpers/db.py                     -> matches (daily queue) + predictions/results (permanent history)
tools/fetch_match_overview.py     -> flashscore.com match preview/news scrape (unchanged from v1)
tools/fetch_whispers_prediction.py-> footballwhispers.com search + prediction extraction
agent.py                          -> LangGraph react agent: pulls history, reasons per match, saves
                                      predictions, builds+books the ticket, sends it
tools/sportybet_client.py         -> requests-based SportyBet 'lite' session (no login, no stake)
tools/book_ticket.py               -> books each pick as a SportyBet slip, degrades per-leg on misses
helpers/generate_ticket.py        -> formats the ticket message (fixtures, picks, booking code)

helpers/fetch_match_results.py    -> flashscore.mobi scrape: FT/HT score, corners, cards, shots, SOT
helpers/generate_message.py       -> formats the detailed results message
results.py                        -> pulls today's queue, scrapes results, grades predictions,
                                      sends the results message
```

## Feedback loop details

`helpers/db.grade_prediction()` does a best-effort correctness check against
the final score for a handful of common market types (home/away/draw,
over/under total goals, BTTS, exact scoreline). Anything it can't confidently
grade (player props, corner/card markets, etc.) is left ungraded rather than
guessed at. `get_history_context()` turns graded history into a compact
text block - accuracy by market, plus the most recent graded picks - that
gets dropped into the agent's context before it makes today's calls. Over
time this is what lets the agent notice "I'm bad at BTTS calls" and adjust.

## Scraping caveats (read before relying on this)

None of the target sites (flashscore.com, flashscore.mobi,
footballwhispers.com, sportybet.com) publish a supported API, so everything
here is markup-scraping, which is inherently brittle:

- **flashscore.com fixtures** (`tools/fetch_all_matches.py`) hits each
  configured league's page directly and pulls match rows via the row-id
  convention (`div[id^="g_1_"]`), filtering to "today" by flashscore's
  bare-HH:MM-means-today display quirk. Like the results scraper below,
  this was written without a live page load to confirm against - verify it
  finds matches for at least one league before trusting the daily run, and
  double check the World Cup qualifying / Nations League slugs each season
  since those rotate.
- **flashscore.mobi** (`helpers/fetch_match_results.py`) is matched directly
  by the same `match_id` `fetch_all_matches.py` already extracted
  (`flashscore.mobi/match/{match_id}/`),
  which is convenient - but I could not load a live match page from this
  build environment to confirm exact stat labels/markup. The scraper reads
  plain page text and pattern-matches on label strings ("Corner Kicks",
  "Yellow Card", "Shots on Target"...) rather than CSS classes, to survive
  minor layout changes, but you should sanity-check its output against a
  couple of real matches before trusting it, and update the label list in
  that file if stats come back empty.
- **footballwhispers.com** (`tools/fetch_whispers_prediction.py`) uses the
  site's on-site WordPress search and matches article titles against both
  team names. It's a soft signal by design - if it can't find a matching
  article, the agent just proceeds without it.
- **flashscore.com** overview scraping is unchanged from v1 and already
  works against the site's `eventPreview` JSON blob embedded in the page.

## Persisting history across GitHub Actions runs

Actions artifacts aren't a real database - each run's artifact is a
snapshot. To keep predictions/results history flowing across days:
`daily_parlay.yml` now downloads the db artifact last produced by
`send_scores.yml` before running (this is a no-op, safely, on the very
first run when no artifact exists yet), and `send_scores.yml` re-uploads
the db after appending results. If you'd rather not depend on artifact
retention (default 90 days, and it's still not a "real" persistent store),
swap `resources/db/matches.db` for a hosted SQLite (e.g. Turso) or Postgres
and point `helpers/db.py` at it instead - the rest of the code doesn't care
where the file lives.

## Setup

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
```

Environment variables (set as GitHub Actions secrets, or in a local `.env`):

| Variable             | Used by                          |
|-----------------------|-----------------------------------|
| `OPENAI_API_KEY`      | `agent.py` (via `langchain-openai`)|
| `TELEGRAM_BOT_TOKEN`  | `tools/send_telegram_message.py`  |
| `TELEGRAM_CHAT_ID`    | `tools/send_telegram_message.py`  |

Both workflow files still have `if: false` on the job - flip that once
you've smoke-tested locally (`python tools/fetch_all_matches.py`,
`python agent.py`, `python results.py`).

## Gambling disclaimer

This tool produces football predictions for entertainment/research
purposes. Predictions - human or AI - are not guaranteed, and past
accuracy (however this feedback loop measures it) doesn't guarantee future
results. Bet only what you can afford to lose, and treat any automation
here as a research aid, not a substitute for your own judgment.

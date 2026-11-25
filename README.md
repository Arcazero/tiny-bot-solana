# tiny-bot-solana

[![make.fun · u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/Arcazero/tiny-bot-solana/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/Arcazero/tiny-bot-solana/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1?utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)

A tiny paper-trading bot for hourly Solana prices: it reads the hourly bars and decides when to hold and when to sit in USDC. Built for make.fun's "Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana" bounty, $2 in USDC.

## Strategy

A fast MACD + CCI-dip scalper, long only, one Python program, standard library only, fully deterministic:

- Per symbol, over its own hourly closes: MACD(8, 18, 9) and CCI(10). Both seed fast, so the bot trades through a 72-bar window even with no warm-up bars.
- Entry on a bar's close (filled at the next open): MACD above its signal line and CCI at or under -40 — a dip inside an uptrend — on a symbol not held.
- Exit, the whole position: MACD under its signal line, or 8% over cost (hard cap), or 8% under cost (stop loss), or held 40 bars (time exit, so the 8-trade minimum is met even in a flat window), or a trailing exit: once a position is 4% over its cost it leaves if it falls 3% under the highest value it has reached since entry, so a winner rides a rally instead of banking at +4%.
- Stake: equity over 7 slots, capped at 25% of equity per symbol; sells go first, then buys in universe order, at most 16 orders a bar. Slippage is capped at 100 bps past the deciding close.

Dev-window grade (local, `grade-local --driver process`): net PnL **+$227.16** on $10,000 paper capital, 42 trades, max drawdown 1.47% — against buy-and-hold at -$869.34 and the best house baseline (MACD-CCI) at -$20.22 on the same window.

## Run it

```sh
python3 main.py
```

The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout (see `sdk` in the competition kit); `vendor/makefun_bars.py` is the protocol shim it ships with. No network, no clock, no randomness: the same bars give the same orders, run after run.

---

<sub>Entered on [make.fun](https://make.fun/?ref=crisp-walrus-10&utm_source=github&utm_medium=readme&utm_campaign=u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1) · AI agents build software for cash rewards</sub>

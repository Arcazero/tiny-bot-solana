"""Tiny Bot: fast MACD + CCI-dip scalper for agent-fun/bars-replay/v1.

Strategy (long only, one program, standard library only, fully deterministic):
  - Per symbol, over its own hourly closes: MACD(8, 18, 9) and CCI(10).
    Both seed fast (first signal ~bar 27) so the bot trades through a 72-bar
    window even with no warm-up bars.
  - Entry on a bar's close (filled at the next open): MACD above its signal
    line and CCI at or under -40 (a dip inside an uptrend), on a symbol not held.
  - Exit, the whole position: MACD under its signal line, or the position
    worth 8% over its cost (hard cap), or 8% under it (stop loss), or held
    30 bars (time exit, forces turnover so the 8-trade minimum is met even
    in a flat window), or a trailing exit: once a position is 4% over its
    cost it leaves if it falls 3% under the highest value it has reached
    since entry, so a winner rides a rally instead of banking at +4%.
  - Stake: equity over 7 slots, capped at 25% of equity per symbol; sells go
    first, then buys in universe order, at most 16 orders a bar. Slippage is
    capped at 100 bps past the deciding close, so a sell into a liquidity gap
    is refused (and retried) rather than filled for almost nothing.
  - All indicators run in float64 on + - * / alone, so the same bars give
    the same orders, run after run. No clock, no randomness, no network.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

FAST_BARS = 8
SLOW_BARS = 18
SIGNAL_BARS = 9
CCI_BARS = 10
CCI_SCALE = 0.015
CCI_ENTRY_AT_MOST = -40
STOP_NUM = 46
STOP_DEN = 50
MAX_HOLD_BARS = 40
MAX_SLIPPAGE_BPS = 100
# Trailing exit: once a position is 4% over its cost, it exits if it falls
# 3% under the highest value it has reached since entry, so a winner rides
# a rally instead of banking at +4%. A 10% hard cap still banks big wins.
TRAIL_ON = 1
TRAIL_ARM_NUM = 26
TRAIL_ARM_DEN = 25
TRAIL_NUM = 97
TRAIL_DEN = 100
HARD_TP_NUM = 27
HARD_TP_DEN = 25


class Series:
    __slots__ = ("warm", "fast", "slow", "macds", "signal", "typical", "bars")

    def __init__(self):
        self.warm = []
        self.fast = None
        self.slow = None
        self.macds = []
        self.signal = None
        self.typical = []
        self.bars = 0


series = {}
opened = {}
peak = {}


def _mean(xs):
    return sum(xs) / len(xs)


def _ema(last, x, bars):
    return (x - last) * (2 / (bars + 1)) + last


def push(bar):
    s = series.get(bar["symbol"])
    if s is None:
        s = Series()
        series[bar["symbol"]] = s
    s.bars += 1
    c = float(bar["c"])
    if s.slow is None or s.fast is None:
        s.warm.append(c)
        if len(s.warm) == SLOW_BARS:
            s.slow = _mean(s.warm)
            s.fast = _mean(s.warm[SLOW_BARS - FAST_BARS:])
    else:
        s.fast = _ema(s.fast, c, FAST_BARS)
        s.slow = _ema(s.slow, c, SLOW_BARS)
    macd = None
    if s.slow is not None and s.fast is not None:
        macd = s.fast - s.slow
        if s.signal is not None:
            s.signal = _ema(s.signal, macd, SIGNAL_BARS)
        else:
            s.macds.append(macd)
            if len(s.macds) == SIGNAL_BARS:
                s.signal = _mean(s.macds)
    typical = (float(bar["h"]) + float(bar["l"]) + c) / 3
    s.typical.append(typical)
    if len(s.typical) > CCI_BARS:
        s.typical.pop(0)
    if macd is None or s.signal is None or bar.get("v") == "0":
        return None
    m = _mean(s.typical)
    spread = 0.0
    for x in s.typical:
        spread += m - x if x < m else x - m
    dev = typical - m
    cci = 0.0 if dev == 0 or spread == 0 else dev / (CCI_SCALE * (spread / CCI_BARS))
    if macd > s.signal and cci <= CCI_ENTRY_AT_MOST:
        return "up"
    if macd < s.signal:
        return "down"
    return None


def exits(state, symbol, held, signal):
    if signal == "down":
        return True
    value = state.value(symbol, held.qty)
    if symbol in peak:
        if value > peak[symbol]:
            peak[symbol] = value
    else:
        peak[symbol] = value
    if value * HARD_TP_DEN >= held.cost * HARD_TP_NUM:
        return True
    if value * STOP_DEN <= held.cost * STOP_NUM:
        return True
    if (TRAIL_ON and peak[symbol] * TRAIL_ARM_DEN >= held.cost * TRAIL_ARM_NUM
            and value * TRAIL_DEN <= peak[symbol] * TRAIL_NUM):
        return True
    if symbol in opened and state.seq - opened[symbol] >= MAX_HOLD_BARS:
        return True
    return False


def on_batch(state, batch):
    for f in batch.get("fills", []):
        if f.get("side") == "buy" and f.get("status") == "filled":
            opened[f["symbol"]] = state.seq
    for sym in list(peak):
        if sym not in state.positions:
            del peak[sym]
    signals = {}
    for bar in batch["bars"]:
        signals[bar["symbol"]] = push(bar)
    if state.warming_up:
        return []
    caps = state.hello["caps"]
    fees = state.hello["fees"]
    sells = []
    entries = []
    for sym in state.hello["symbols"]:
        symbol = sym["symbol"]
        if symbol not in signals:
            continue
        signal = signals[symbol]
        held = state.positions.get(symbol)
        if held is not None:
            if exits(state, symbol, held, signal):
                sells.append({"side": "sell", "symbol": symbol, "qty": held.qty,
                              "max_slippage_bps": MAX_SLIPPAGE_BPS})
        elif signal == "up":
            entries.append(symbol)

    orders = sells[: caps["max_orders_per_bar"]]
    slots = min(len(state.hello["symbols"]), caps["max_open_positions"])
    stake = state.equity // slots
    by_weight = caps["max_weight_bps"] * state.equity // 10000
    room = slots - len(state.positions)
    cash = state.cash
    for symbol in entries:
        if room <= 0 or len(orders) >= caps["max_orders_per_bar"]:
            break
        slice_ = stake if stake < by_weight else by_weight
        if cash < slice_:
            slice_ = cash
        if slice_ == 0 or slice_ < int(fees["min_notional_quote_units"]):
            break
        orders.append({"side": "buy", "symbol": symbol,
                       "notional_quote_units": slice_,
                       "max_slippage_bps": MAX_SLIPPAGE_BPS})
        cash -= slice_
        room -= 1
    return orders


if __name__ == "__main__":
    makefun_bars.run(on_batch)

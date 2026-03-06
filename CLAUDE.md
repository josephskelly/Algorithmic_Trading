# Algorithmic_Trading
Algorithmic trading script.

Using the tastytrade API and a sandbox account (paper trading only), we will execute our algorithmic trading strategy. The strategy buys 2x leveraged sector ETFs when they drop and sells them when they rise.  

- Cash account. No margin.
- List of ETFs available for trading in ETFs.csv.
- At 5 minutes before close every trading day, execute strategy. Before executing:
    - Check if the market is open that day (skip if holiday).
    - Check the actual market close time for that day — NYSE regular close is 4:00 PM ET, but early closes (e.g. day before Thanksgiving, Christmas Eve) are 1:00 PM ET. Use the NYSE calendar to determine the correct close time.
    - Schedule execution for 5 minutes before the actual close time.
    - For each ETF in the list, calculate the % price change since the previous close. Trade proportionally at a rate of $165 per 1% move per $10,000 of total liquidation value. Total liquidation value is the net liquidation value of the account queried live from TastyTrade at execution time. Buy on drops, sell on rises (e.g. a 0.5% drop = buy $82.50 per $10,000 liquidation value; a 2% rise = sell $330 per $10,000 liquidation value). No rounding — trade amount scales linearly with the % change.
    - Trade Amount = (|% Change| / 1%) × $165 × (Total Liquidation Value / $10,000)
    - Minimum trade size is $5.00. Skip the trade if the calculated Trade Amount is less than $5.00.
    - Check each ETF's `is-fractional-quantity-eligible` flag at runtime via the tastytrade instruments endpoint. If eligible: place a single `NOTIONAL_MARKET` order for the Trade Amount (applies to both buys and sells). If not eligible on a buy, skip the trade. If not eligible on a sell, convert Trade Amount to shares (`Trade Amount / current price`), floor to nearest whole share, and skip if result is 0 shares.
    - The only limit is the amount of cash available for trading that day in the account. Skip the trade if would result in a negative cash balance.
    - Sell proceeds settle T+1 and are not available for same-day buys. Only buy orders reduce the cash balance used for same-day guards.
    - Maximum one trade per ETF per day. Skip the trade if an order has already been placed for that ETF today.
    - Sells require a position. At the start of each run, query the account's open positions. If no position is held for an ETF, skip the sell. If the computed sell amount exceeds the value of shares held (quantity × current price), cap it to the position value. This prevents selling shares you don't own — the strategy is buy-on-dip / sell-on-rise, so sells only make sense against previously accumulated positions.
- Rate limiting: tastytrade's API (especially the sandbox) returns 503 errors when orders are fired in rapid succession. A 1-second delay is inserted between each order placement to stay under the rate limit.
- Connection recovery: if the connection to the tastytrade API drops during the trading window:
    - Attempt to reconnect up to 3 times with 5-second gaps between attempts.
    - If all reconnect attempts fail, log the error and abort for the day.
    - After a successful reconnect, query TastyTrade for today's executed and open orders to rebuild the "already traded today" set before resuming.
    - Resume execution for any ETFs not yet processed; skip ETFs already confirmed traded.
    - If reconnecting would push past market close, abort instead of reconnecting.
    - If an order's status is ambiguous after reconnect, skip that ETF and log it.


It is imperative that we do not trade with real money and everything is done on a sandbox account (paper trading) only.
Accuracy is important. 
Use cascading software architecture. 
Use planning mode. 
Keep strategy as simple as possible. Do not overcomplicate. 
Build out in modular pieces. Review in phases. 

In the README, include detailed information on setup from a new user's perspective.
Update the README whenever relevant.
Update the CLAUDE.md whenever relevant.

# TODO
- [x] Fix README Position Sizing section — minimum trade size is $5.00 (tastytrade NOTIONAL_MARKET fractional share minimum). **Resolved.**
- [x] Fix CLAUDE.md intro — still says "sector and bond ETFs" but bond ETFs (UBT, UJB, UST) were removed. **Resolved: removed "and bond" from all descriptions.**
- [x] Define "Total Deposited Cash" — clarify whether this is the fixed initial deposit amount or the current account net liquidation value; affects every trade calculation. **Resolved: use net liquidation value of the account queried live from TastyTrade at execution time.**
- [x] Add market open / holiday check — scheduler must confirm it's an actual trading day before triggering. **Resolved: check NYSE calendar each day; skip if holiday; determine actual close time (regular 4:00 PM ET or early close 1:00 PM ET); trigger 5 min before actual close.**
- [x] Add cap on trade size — no upper limit currently; a large % move on a large account could generate an unexpectedly large order. **Resolved: no cap on trade size.**
- [x] Add daily execution guard — prevent the strategy from firing more than once per trading day if the script restarts. **Resolved: maximum one trade per ETF per day; skip if already traded that ETF today.**
- [x] Clarify fractional shares handling — tastytrade supports fractional shares for some ETFs but not all; define behavior for unsupported ETFs. **Resolved: check `is-fractional-quantity-eligible` flag at runtime; use `NOTIONAL_MARKET` orders for eligible ETFs; skip buy if not eligible; floor to whole shares for sells if not eligible.**
- [x] Clarify sell sizing — selling a dollar amount requires converting to shares at current price; define how to handle rounding to whole shares and any residual. **Resolved: for eligible ETFs use a single `NOTIONAL_MARKET` order for the Trade Amount (both buys and sells); if not eligible on a sell, floor to whole shares; skip if result is 0 shares.**
- [x] Add connection recovery logic — define reconnect behavior if the tastytrade API connection drops during the trading window. **Resolved: retry up to 3 times with 5s gaps; abort if all fail or past market close; query TastyTrade after reconnect to rebuild traded-today set; skip ambiguous-state ETFs.**
- [x] Add position guard for sells — strategy was issuing sell orders for ETFs with no held position (e.g. ROM sell on a 0.40% rise with zero shares held). **Resolved: query positions at run start; skip sell if no position; cap sell amount to position value.**
- [ ] Verify all 11 ETFs in ETFs.csv are `is-fractional-quantity-eligible` on tastytrade before relying on `NOTIONAL_MARKET` orders.
- [ ] Confirm `NOTIONAL_MARKET` sell behavior in sandbox testing once implementation is complete.
- [x] Add `.env.example` to the repo as a credential template for new users. **Resolved.**
- [x] Add Google Cloud deployment instructions to README. **Resolved.**

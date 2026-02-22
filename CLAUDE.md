# Algorithmic_Trading
Algorithmic trading script.

Using ibapi and a paper trading account, we will execute our algorithmic trading strategy. The strategy buys 2x leveraged sector ETFs when they drop and sells them when they rise.  

- Cash account. No margin.
- List of ETFs available for trading in ETFs.csv.
- At 5 minutes before close every trading day, execute strategy:
    - For each ETF in the list, calculate the % price change since the previous close. Trade proportionally at a rate of $165 per 1% move per $10,000 of total liquidation value. Total liquidation value is the net liquidation value of the account queried live from IB at execution time. Buy on drops, sell on rises (e.g. a 0.5% drop = buy $82.50 per $10,000 liquidation value; a 2% rise = sell $330 per $10,000 liquidation value). No rounding — trade amount scales linearly with the % change.
    - Trade Amount = (|% Change| / 1%) × $165 × (Total Liquidation Value / $10,000)
    - Minimum trade size is $1.00. Skip the trade if the calculated Trade Amount is less than $1.00.
    - All ETFs in the list support fractional shares. If an ETF does not support fractional shares, skip the trade.
    - The only limit is the amount of cash available for trading that day in the account. Skip the trade if would result in a negative cash balance.


It is imperative that we do not trade with real money and everything is done on a paper trading account only.
Accuracy is important. 
Use cascading software architecture. 
Use planning mode. 
Keep strategy as simple as possible. Do not overcomplicate. 
Build out in modular pieces. Review in phases. 

In the README, include detailed information on setup from a new user's perspective.
Update the README whenever relevant.
Update the CLAUDE.md whenever relevant.

# TODO
- [x] Fix README Position Sizing section — still says "no minimum threshold" but $1.00 minimum was added. **Resolved.**
- [x] Fix CLAUDE.md intro — still says "sector and bond ETFs" but bond ETFs (UBT, UJB, UST) were removed. **Resolved: removed "and bond" from all descriptions.**
- [x] Define "Total Deposited Cash" — clarify whether this is the fixed initial deposit amount or the current account net liquidation value; affects every trade calculation. **Resolved: use net liquidation value of the account queried live from IB at execution time.**
- [ ] Add market open / holiday check — scheduler must confirm it's an actual trading day before triggering
- [ ] Add cap on trade size — no upper limit currently; a large % move on a large account could generate an unexpectedly large order
- [ ] Add daily execution guard — prevent the strategy from firing more than once per trading day if the script restarts
- [x] Clarify fractional shares handling — IB supports fractional shares for some ETFs but not all; define behavior for unsupported ETFs. **Resolved: all listed ETFs support fractional shares; skip trade if an ETF does not support fractional shares.**
- [ ] Clarify sell sizing — selling a dollar amount requires converting to shares at current price; define how to handle rounding to whole shares and any residual
- [ ] Add connection recovery logic — define reconnect behavior if TWS/Gateway drops during the trading window

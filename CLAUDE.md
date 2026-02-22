# Algorithmic_Trading
Algorithmic trading script.

Using ibapi and a paper trading account, we will execute our algorithmic trading strategy. The strategy buys 2x leveraged sector and bond ETFs when they drop and sells them when they rise.  

- Cash account. No margin.
- List of ETFs available for trading in ETFs.csv.
- At 5 minutes before close every trading day, execute strategy:
    - For each ETF in the list, calculate the % price change since the previous close. Trade proportionally at a rate of $165 per 1% move per $10,000 of total deposited cash. Buy on drops, sell on rises (e.g. a 0.5% drop = buy $82.50 per $10,000 deposited; a 2% rise = sell $330 per $10,000 deposited). No rounding — trade amount scales linearly with the % change.
    - Trade Amount = (|% Change| / 1%) × $165 × (Total Deposited / $10,000)
    - Minimum trade size is $1.00. Skip the trade if the calculated Trade Amount is less than $1.00.
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

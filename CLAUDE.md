# Algorithmic_Trading
Algorithmic trading script.

Using ibapi and a paper trading account, we will execute our algorithmic trading strategy.

- Cash account. No margin.
- List of ETFs available for trading in ETFs.csv.
- At 5 minutes before close every trading day, execute strategy:
    - For each etf in the list of ETFs available for trading, for every 1% drop in the price since previous, buy X dollars worth of the ETF at market price and for every 1% rise in the price, sell X dollars worth of the ETF at market price.
    - The value of X is determined at a rate of $165 per $10,000 of total deposited cash.
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

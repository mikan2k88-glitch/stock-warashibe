# Historical data source v0.1

The first real-market-data research provider uses a public daily snapshot for
NTT (Tokyo: 9432.T):

- Source repository: https://github.com/SeedFlora/idx-daily-data
- CSV: data/9432.T.csv
- Upstream described by that repository: Yahoo Finance
- Fields: Date, Open, High, Low, Close, Adj Close, Volume

This source is used only for research/backtesting. The repository fetches a
fresh snapshot at runtime and records a SHA-256 of the exact CSV bytes so each
stored experiment identifies the input it actually used.

Price policy:

- execution uses unadjusted OHLC
- adjusted close is not mixed into execution prices
- adjusted close is used only as a corporate-action/split detection signal
- suspected split/corporate-action discontinuities fail closed
- rows after the execution date are rejected by the provider
- in-sample and out-of-sample periods are split chronologically
- G5 is frozen before the real-data test; in-sample data is not used to tune it

This endpoint does not place orders and does not connect to a brokerage.

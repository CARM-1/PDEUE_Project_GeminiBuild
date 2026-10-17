# Weather replay fixtures

Both station feeds are **SYNTHETIC_REPRESENTATIVE** qualification fixtures.
The NOAA GeoJSON shape and KJFK/KORD station IDs are representative; temperatures,
availability times, strike definitions, and executions are constructed test data.
These are not observed NOAA measurements or official settlement records.

`features[]` uses station URLs, timestamps, publication times, and Celsius values
accepted by `authentic_weather_tape_loader.py`. Half-open Fahrenheit brackets
are declared in `strike_ladder`. Late publication and expiry barriers are covered.

KJFK also includes `execution_tape.trades[]`, using the Kalshi trade schema, plus
a normalized `initial_book`. These distinct records drive Strategy D maker
execution. Temperatures never become trade prices, lots, or aggressor flow.
KORD is deliberately observation-only and must abstain with `NO_EXECUTION_TAPE`.

Direct NOAA/venue acquisition was unavailable under the environment's outbound
policy. Replace fixtures with independently archived feeds before claiming
authentic provenance. NOAA API reference: https://www.weather.gov/documentation/services-web-api

Reproduce all venue reports from the repository root:

```sh
cd backend
PYTHONPATH=. python scripts/run_batch_authentic_replay.py --calibrate
PYTHONPATH=. pytest --rootdir=. tests/ -v
```

Calibration assumes fair probability 0.99, a winning 100-cent payout, ten lots,
and a queue floor of five lots (or initial best-bid depth, whichever is larger).
Without L2, a two-cent spread is assumed from the initial print. Selection uses
initial-time records only; expiry is initial + 300 seconds, or a predeclared
weather strike expiry. All resulting PnL is simulated.

An external scenario manifest can supply a weather wrapper containing `scenario`
(complete WeatherReplayScenario fields), `execution_scenario` (complete
IndependentReplayScenario fields), and optional `queue_ahead`. Contract, capital,
and all time bounds must match between both scenarios; the station and expiry
must match the declared bracket. Explicit execution inputs take precedence over
calibration, including losing settlement payouts. Without separate execution
inputs, an external observation scenario continues to abstain.

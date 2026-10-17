# Archived METAR observations (WP-8S)

Three historical station observations replace the former synthetic production
fixtures. Synthetic execution and expiry vectors now live under
`backend/tests/fixtures/representative_venues/weather/`.

| Station | Observed UTC | ASOS temperature C | Exact converted F |
| --- | --- | ---: | ---: |
| KORD | 2019-07-01 11:51 | 21.1 | 69.98 |
| KDEN | 2019-07-01 11:53 | 16.7 | 62.06 |
| KJFK | 2019-07-01 11:51 | 21.7 | 71.06 |

Source: [Unidata MetPy archived bulletin](https://github.com/Unidata/MetPy/blob/f4e4d2509a485b969efb8270401d7585f8bec68e/staticdata/metar_20190701_1200.txt).
The complete 1,540,621-byte bulletin was retrieved through the GitHub connector
and checked against Git blob `156ffa9ee255827566c35ed09b99976902b07998`
before extraction. `sources/metar_20190701_1200_excerpt.txt` retains the exact
three station messages. Each tape records excerpt and full bulletin SHA-256,
upstream commit URL, blob ID, retrieval time, and parsing year/month.
The signed ASOS `T` group supplies tenth-degree temperatures instead of the
rounded whole-degree field. Bulletin retransmissions collapse to one observation.

These sparse observations are not complete daily tapes, official daily climate
maxima, exchange executions, or settlement certificates. No verified strike
terms exist in this archive. `strike_ladder` is empty: no 0/100-cent settlement
brackets or trade prints are invented. Nanosecond times preserve the original
minute resolution. Historical publication times are unknown; `available_at`
conservatively uses retrieval time, preventing assumed historical availability.

Reproduce the offline parse from the backend directory:

```sh
PYTHONPATH=. python -m app.adapters.noaa_asos_harvester \
  --archive ../data/venues/weather/sources/metar_20190701_1200_excerpt.txt \
  --year 2019 --month 7 \
  --source-url https://github.com/Unidata/MetPy/blob/f4e4d2509a485b969efb8270401d7585f8bec68e/staticdata/metar_20190701_1200.txt \
  --output-dir ../work/reparsed_weather
```

Fetch a full IEM day when the environment permits the destination:

```sh
PYTHONPATH=. python -m app.adapters.noaa_asos_harvester \
  --start 2019-07-01 --end 2019-07-02 --output-dir ../work/iem_weather
```

IEM/NOAA currently return proxy CONNECT 403: a destination-policy denial, not
Cloudflare. Offline import needs no network. Supply independently archived
venue strike definitions, rules, and execution prints before qualifying PnL.

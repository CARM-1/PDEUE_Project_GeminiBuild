# Synthetic regression vectors

These four fixtures moved from `data/venues/kalshi` and `data/venues/weather`.
Their original `SYNTHETIC_REPRESENTATIVE` labels and bytes are retained. They
exercise queues, partial fills, settlement overrides, publication timing, and
expiry barriers; they never qualify authentic venue coverage.

Exercise stress mechanics without claiming authentic performance:

```sh
cd backend
PYTHONPATH=. python scripts/run_batch_authentic_replay.py \
  --venues-root tests/fixtures/representative_venues --stress \
  --output ../work/representative_stress.json
```

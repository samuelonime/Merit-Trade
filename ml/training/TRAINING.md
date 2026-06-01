# Merit-Trade AI — Model Training Guide

Three models must be trained and placed in `ml/models/` before the signal engine
will use real ML predictions. Without them the service falls back to a simple
RSI-only rule.

---

## Quick start (recommended path)

### 1. Install dependencies

```bash
cd ml/training
pip install xgboost torch scikit-learn pandas numpy requests pyarrow
```

### 2. Set your Twelve Data API key

Free tier gives 800 requests/day — enough to fetch data for all 5 symbols.
Get a key at <https://twelvedata.com>.

```bash
export TWELVE_DATA_API_KEY=your_key_here
```

### 3. Fetch data and train

```bash
python train_models.py \
  --fetch \
  --symbols "EUR/USD,GBP/USD,USD/JPY,AUD/USD,XAU/USD" \
  --timeframe 1h \
  --outputpoints 5000 \
  --output-dir ../../ml/models
```

This will:
- Fetch ~5 000 hourly candles per symbol from Twelve Data (~40 MB total)
- Compute all 21 technical indicators (EMA, SMA, RSI, MACD, ATR, Bollinger, VWAP)
- Cache the combined dataset to `ml/models/training_data.parquet`
- Train XGBoost → `xgboost_v1.json`
- Train LSTM → `lstm_v1.pt`
- Train Transformer → `transformer_v1.pt`
- Save the feature scaler → `scaler_v1.pkl`

Typical training time: **10–20 minutes on CPU**, 3–5 minutes with a GPU.

---

## Alternative: use your own data

If you already have a CSV or Parquet file with the required columns:

```
ema_20, ema_50, ema_200, sma_20, sma_50,
rsi_14, macd_line, macd_signal, macd_hist,
atr_14, bb_upper, bb_middle, bb_lower, bb_width,
vwap, volume_sma_20,
open, high, low, close, volume
```

Run:

```bash
python train_models.py \
  --data /path/to/your/data.csv \
  --output-dir ../../ml/models
```

---

## Re-training without re-fetching

After the first `--fetch` run, the combined dataset is saved locally.
You can retrain any time without hitting the API:

```bash
python train_models.py \
  --data ../../ml/models/training_data.parquet \
  --output-dir ../../ml/models
```

---

## Deploying models to production

The signal engine expects model files at these paths (set in `.env`):

| Variable | Default |
|---|---|
| `MODEL_XGBOOST_PATH` | `/app/models/xgboost_v1.json` |
| `MODEL_LSTM_PATH` | `/app/models/lstm_v1.pt` |
| `MODEL_TRANSFORMER_PATH` | `/app/models/transformer_v1.pt` |
| `MODEL_SCALER_PATH` | `/app/models/scaler_v1.pkl` |

The `docker-compose.prod.yml` mounts `./ml/models` → `/app/models` (read-only)
inside the `signal-engine` and `celery-worker` containers. Just place your
trained files in `ml/models/` on the host and restart those two services:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  restart signal-engine celery-worker
```

Verify models loaded successfully:

```bash
curl https://app.merittrade.ai/api/signals/health
# "xgboost": true, "lstm": true, "transformer": true
```

---

## Troubleshooting

**`TWELVE_DATA_API_KEY is not set`** — export the env var before running.

**Rate limit hit mid-fetch** — the script pauses 8 seconds between symbols.
If you still hit limits, reduce `--outputpoints` or fetch fewer symbols.

**CUDA out of memory** — reduce batch size in `train_lstm` / `train_transformer`
(search for `batch_size = 64` and lower it).

**Models load but accuracy seems low** — try more data (`--outputpoints 10000`)
or a shorter timeframe (`--timeframe 15min`) which gives more samples per day.

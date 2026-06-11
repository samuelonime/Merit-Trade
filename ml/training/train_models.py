"""
Merit-Trade AI — ML Model Training Pipeline
Trains XGBoost, LSTM, and Transformer models on historical market data.

Usage (fetch data then train):
    python train_models.py \\
        --fetch \\
        --symbols "EUR/USD,GBP/USD,USD/JPY,AUD/USD,XAU/USD" \\
        --timeframe 1h \\
        --outputpoints 5000 \\
        --output-dir ../../ml/models

Usage (train from existing data):
    python train_models.py \\
        --data /path/to/data.csv \\
        --output-dir ../../ml/models

Requirements:
    pip install xgboost torch scikit-learn pandas numpy requests pyarrow
"""
import argparse
import os
import pickle
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score
import xgboost as xgb


# ── Shared sequence-length constants ─────────────────────────────
# These MUST stay in sync with services/signal-engine/main.py
LSTM_SEQ_LEN        = 30
TRANSFORMER_SEQ_LEN = 20

# ── Feature columns ───────────────────────────────

FEATURE_COLS = [
    "ema_20", "ema_50", "ema_200", "sma_20", "sma_50",
    "rsi_14", "macd_line", "macd_signal", "macd_hist",
    "atr_14", "bb_upper", "bb_middle", "bb_lower", "bb_width",
    "vwap", "volume_sma_20",
    "open", "high", "low", "close", "volume",
]

LABEL_HORIZON = 5  # Predict direction 5 bars ahead


# ── Label Engineering ─────────────────────────────

def create_labels(df: pd.DataFrame, horizon: int = LABEL_HORIZON, threshold: float = 0.001) -> np.ndarray:
    """
    Create BUY/SELL/HOLD labels based on forward returns.
    0 = SELL, 1 = HOLD, 2 = BUY
    """
    future_close = df["close"].shift(-horizon)
    pct_change   = (future_close - df["close"]) / df["close"]

    labels = np.where(pct_change >  threshold, 2,   # BUY
             np.where(pct_change < -threshold, 0,   # SELL
             1))                                     # HOLD
    return labels


# ── Indicator computation (mirrors market-data/main.py) ──────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all 21 technical indicators from OHLCV data.
    df must have columns: open, high, low, close, volume (chronological order).
    """
    df = df.copy()
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # Moving averages
    df["ema_20"]  = close.ewm(span=20, adjust=False).mean()
    df["ema_50"]  = close.ewm(span=50, adjust=False).mean()
    df["ema_200"] = close.ewm(span=200, adjust=False).mean()
    df["sma_20"]  = close.rolling(20).mean()
    df["sma_50"]  = close.rolling(50).mean()

    # RSI
    delta = close.diff()
    gain  = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss  = -delta.where(delta < 0, 0.0).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd_line"]   = ema12 - ema26
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd_line"] - df["macd_signal"]

    # ATR
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # Bollinger Bands
    df["bb_middle"] = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["bb_upper"] = df["bb_middle"] + 2 * bb_std
    df["bb_lower"] = df["bb_middle"] - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

    # VWAP — rolling 20-period (matches market-data service, stateless across batches)
    typical_price = (high + low + close) / 3
    df["vwap"] = (
        (typical_price * volume).rolling(20).sum() /
        volume.rolling(20).sum()
    )

    # Volume SMA
    df["volume_sma_20"] = volume.rolling(20).mean()

    return df


# ── Data fetching ─────────────────────────────────
# FIX #2: Implement the --fetch path that TRAINING.md documents.
# Previously these CLI flags were absent from argparse, causing an immediate
# failure when following the documented training command.

def fetch_from_twelve_data(symbol: str, timeframe: str, outputpoints: int, api_key: str) -> pd.DataFrame:
    """
    Fetch historical OHLCV from Twelve Data API.
    Free tier: 800 req/day — sufficient for all 5 forex/gold symbols.
    """
    import requests

    tf_map = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day"}
    interval = tf_map.get(timeframe, "1h")

    # Twelve Data max outputsize per request is 5000
    chunk_size = min(outputpoints, 5000)

    print(f"  Fetching {symbol} ({interval}) — {outputpoints} bars from Twelve Data...")
    resp = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol":     symbol,
            "interval":   interval,
            "outputsize": chunk_size,
            "apikey":     api_key,
            "format":     "JSON",
            "order":      "ASC",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") == "error":
        raise RuntimeError(f"Twelve Data error for {symbol}: {data.get('message')}")

    values = data.get("values", [])
    if not values:
        raise RuntimeError(f"No data returned for {symbol}")

    rows = []
    for row in values:
        rows.append({
            "datetime": row["datetime"],
            "open":     float(row["open"]),
            "high":     float(row["high"]),
            "low":      float(row["low"]),
            "close":    float(row["close"]),
            "volume":   float(row.get("volume", 0)),
        })

    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    print(f"  ✓ {symbol}: {len(df)} bars fetched")
    return df


def fetch_from_binance(symbol: str, timeframe: str, outputpoints: int) -> pd.DataFrame:
    """
    Fetch historical OHLCV from Binance public API (crypto only, no auth needed).
    """
    import requests

    tf_map  = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
    interval = tf_map.get(timeframe, "1h")
    limit    = min(outputpoints, 1000)

    print(f"  Fetching {symbol} ({interval}) — {outputpoints} bars from Binance...")
    resp = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    klines = resp.json()

    rows = []
    for k in klines:
        rows.append({
            "datetime": pd.Timestamp(k[0], unit="ms", tz="UTC"),
            "open":     float(k[1]),
            "high":     float(k[2]),
            "low":      float(k[3]),
            "close":    float(k[4]),
            "volume":   float(k[5]),
        })

    df = pd.DataFrame(rows).set_index("datetime").sort_index()
    print(f"  ✓ {symbol}: {len(df)} bars fetched")
    return df


CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}


def fetch_training_data(
    symbols_str: str,
    timeframe: str,
    outputpoints: int,
    output_dir: str,
    api_key: str | None,
) -> str:
    """
    Fetch data for all symbols, compute indicators, combine into one DataFrame,
    save to parquet, and return the path.
    """
    os.makedirs(output_dir, exist_ok=True)
    symbols = [s.strip() for s in symbols_str.split(",")]
    all_dfs = []

    for i, symbol in enumerate(symbols):
        # Binance symbol names use no slash (BTCUSDT); Twelve Data uses slash (EUR/USD)
        binance_sym = symbol.replace("/", "")

        try:
            if binance_sym in CRYPTO_SYMBOLS:
                df = fetch_from_binance(binance_sym, timeframe, outputpoints)
            else:
                if not api_key:
                    raise RuntimeError(
                        "TWELVE_DATA_API_KEY is not set. "
                        "Export it or pass --api-key to fetch forex/gold data."
                    )
                df = fetch_from_twelve_data(symbol, timeframe, outputpoints, api_key)

            df = compute_indicators(df)
            df["symbol"] = symbol
            all_dfs.append(df)

        except Exception as e:
            print(f"  ✗ {symbol}: {e} — skipping")

        # Respect free-tier rate limits (8s between symbols)
        if i < len(symbols) - 1:
            print("  Pausing 8s for API rate limit...")
            time.sleep(8)

    if not all_dfs:
        raise RuntimeError("No data fetched for any symbol. Check API keys and symbol names.")

    combined = pd.concat(all_dfs).reset_index()
    out_path = os.path.join(output_dir, "training_data.parquet")
    combined.to_parquet(out_path, index=False)
    print(f"\n✓ Combined dataset: {len(combined)} rows across {len(all_dfs)} symbols")
    print(f"✓ Saved to {out_path}")
    return out_path


# ── XGBoost Model ─────────────────────────────────

def train_xgboost(X_train, y_train, X_val, y_val) -> xgb.XGBClassifier:
    """Train XGBoost classifier on engineered features."""
    model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        # FIX #11: use_label_encoder was removed in XGBoost 1.6 — drop it
        eval_metric="mlogloss",
        objective="multi:softprob",
        num_class=3,
        tree_method="hist",
        early_stopping_rounds=50,
        random_state=42,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=100,
    )

    val_preds = model.predict(X_val)
    acc = accuracy_score(y_val, val_preds)
    print(f"\nXGBoost Validation Accuracy: {acc:.4f}")
    print(classification_report(y_val, val_preds, target_names=["SELL", "HOLD", "BUY"]))
    return model


# ── LSTM Model ────────────────────────────────────

class LSTMModel(nn.Module):
    """
    LSTM for sequential OHLCV prediction.
    Input:  (batch, seq_len=LSTM_SEQ_LEN, features=5)
    Output: (batch, 3) class logits
    """
    def __init__(self, input_size: int = 5, hidden_size: int = 128,
                 num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True,
        )
        self.attention   = nn.MultiheadAttention(hidden_size, num_heads=4, batch_first=True)
        self.norm        = nn.LayerNorm(hidden_size)
        self.classifier  = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 3),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _  = self.lstm(x)
        attn_out, _  = self.attention(lstm_out, lstm_out, lstm_out)
        out = self.norm(lstm_out + attn_out)
        out = out[:, -1, :]   # last timestep
        return self.classifier(out)


def prepare_sequences(df: pd.DataFrame, labels: np.ndarray, seq_len: int = LSTM_SEQ_LEN):
    """
    Create (sequence, label) pairs for LSTM training.
    Sequences are in chronological order (oldest first) to match inference.
    FIX #9 (training side): sequences here are already chronological because
    the DataFrame is sorted oldest-first. The inference fix reverses the
    DESC-ordered DB rows to match.
    """
    ohlcv_cols  = ["open", "high", "low", "close", "volume"]
    data        = df[ohlcv_cols].values
    scaler      = StandardScaler()
    data_scaled = scaler.fit_transform(data)

    X, y = [], []
    for i in range(seq_len, len(data_scaled) - LABEL_HORIZON):
        X.append(data_scaled[i - seq_len:i])   # chronological: oldest → newest
        y.append(labels[i])

    return np.array(X), np.array(y), scaler


def train_lstm(X_train, y_train, X_val, y_val, epochs: int = 50) -> LSTMModel:
    """Train LSTM model."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nTraining LSTM on {device}")

    model     = LSTMModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss(
        weight=torch.FloatTensor([1.0, 0.5, 1.0]).to(device)   # down-weight HOLD class
    )

    X_tr = torch.FloatTensor(X_train).to(device)
    y_tr = torch.LongTensor(y_train).to(device)
    X_v  = torch.FloatTensor(X_val).to(device)
    y_v  = torch.LongTensor(y_val).to(device)

    best_val_acc = 0
    best_state   = None

    for epoch in range(epochs):
        model.train()
        batch_size = 64
        indices    = torch.randperm(len(X_tr))
        total_loss = 0

        for i in range(0, len(X_tr), batch_size):
            batch_idx = indices[i:i + batch_size]
            xb, yb = X_tr[batch_idx], y_tr[batch_idx]
            optimizer.zero_grad()
            out  = model(xb)
            loss = criterion(out, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()

        scheduler.step()

        model.eval()
        with torch.no_grad():
            val_out   = model(X_v)
            val_preds = val_out.argmax(dim=1).cpu().numpy()
            val_acc   = accuracy_score(y_val, val_preds)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state   = {k: v.clone() for k, v in model.state_dict().items()}

        if (epoch + 1) % 10 == 0:
            print(f"Epoch {epoch+1}/{epochs} | Loss: {total_loss:.4f} | Val Acc: {val_acc:.4f}")

    if best_state:
        model.load_state_dict(best_state)

    print(f"\nBest LSTM Validation Accuracy: {best_val_acc:.4f}")
    return model.cpu()


# ── Transformer Model ─────────────────────────────

class MarketTransformer(nn.Module):
    """
    Transformer encoder for multi-timeframe market context.
    Input:  (batch, seq_len=TRANSFORMER_SEQ_LEN, features=len(FEATURE_COLS))
    Output: dict {"logits": Tensor(batch, 3), "confidence": Tensor(batch,)}
    """
    def __init__(
        self,
        input_size: int = len(FEATURE_COLS),
        d_model: int = 128,
        nhead: int = 8,
        num_layers: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.input_proj  = nn.Linear(input_size, d_model)
        self.pos_encoding = PositionalEncoding(d_model, dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=256,
            dropout=dropout, batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.pool    = nn.AdaptiveAvgPool1d(1)
        self.classifier = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, 3),
        )
        self.confidence_head = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.GELU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> dict:
        x      = self.input_proj(x)
        x      = self.pos_encoding(x)
        x      = self.encoder(x)
        pooled = self.pool(x.transpose(1, 2)).squeeze(-1)   # (batch, d_model)
        return {
            "logits":     self.classifier(pooled),            # (batch, 3)
            "confidence": self.confidence_head(pooled).squeeze(-1),  # (batch,) scalar per sample
        }


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 500):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        import math
        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(max_len, 1, d_model)
        pe[:, 0, 0::2] = torch.sin(position * div_term)
        pe[:, 0, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:x.size(1)].transpose(0, 1)
        return self.dropout(x)


def train_transformer(X_train, y_train, X_val, y_val, epochs: int = 40) -> MarketTransformer:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nTraining Transformer on {device}")

    model     = MarketTransformer().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=1e-3, total_steps=epochs * (len(X_train) // 64 + 1)
    )
    criterion = nn.CrossEntropyLoss()

    X_tr = torch.FloatTensor(X_train).to(device)
    y_tr = torch.LongTensor(y_train).to(device)
    X_v  = torch.FloatTensor(X_val).to(device)
    y_v  = torch.LongTensor(y_val).to(device)

    best_val_acc = 0
    best_state   = None

    for epoch in range(epochs):
        model.train()
        batch_size = 64
        indices    = torch.randperm(len(X_tr))
        total_loss = 0

        for i in range(0, len(X_tr), batch_size):
            batch_idx = indices[i:i + batch_size]
            xb, yb = X_tr[batch_idx], y_tr[batch_idx]
            optimizer.zero_grad()
            out  = model(xb)
            loss = criterion(out["logits"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()

        model.eval()
        with torch.no_grad():
            val_out   = model(X_v)
            val_preds = val_out["logits"].argmax(dim=1).cpu().numpy()
            val_acc   = accuracy_score(y_val, val_preds)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state   = {k: v.clone() for k, v in model.state_dict().items()}

        if (epoch + 1) % 10 == 0:
            print(f"Epoch {epoch+1}/{epochs} | Loss: {total_loss:.4f} | Val Acc: {val_acc:.4f}")

    if best_state:
        model.load_state_dict(best_state)
    print(f"\nBest Transformer Validation Accuracy: {best_val_acc:.4f}")
    return model.cpu()


# ── Main Training Pipeline ────────────────────────

def train_all(data_path: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Loading data from {data_path}...")
    df = pd.read_parquet(data_path) if data_path.endswith(".parquet") else pd.read_csv(data_path)

    # If data was fetched with a "symbol" column, run indicators per symbol and recombine
    if "symbol" in df.columns and not all(c in df.columns for c in FEATURE_COLS):
        print("Computing indicators per symbol...")
        parts = []
        for sym, grp in df.groupby("symbol"):
            grp = grp.sort_values("datetime" if "datetime" in grp.columns else grp.index.name or "index")
            parts.append(compute_indicators(grp.reset_index(drop=True)))
        df = pd.concat(parts).reset_index(drop=True)

    df = df.dropna(subset=FEATURE_COLS)
    print(f"Dataset size after dropping NaN: {len(df)} rows")

    # Create labels
    labels     = create_labels(df)
    valid_mask = ~np.isnan(labels) & (np.arange(len(labels)) < len(labels) - LABEL_HORIZON)
    df         = df[valid_mask].reset_index(drop=True)
    labels     = labels[valid_mask]

    # Distribution
    unique, counts = np.unique(labels, return_counts=True)
    for cls, cnt in zip(["SELL", "HOLD", "BUY"], counts):
        print(f"  {cls}: {cnt} ({cnt/len(labels)*100:.1f}%)")

    # Train/val split (time-series: no shuffle)
    split = int(len(df) * 0.8)
    X     = df[FEATURE_COLS].values.astype(np.float32)
    y     = labels.astype(np.int32)

    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    # Fit scaler on training data only
    scaler        = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled   = scaler.transform(X_val)

    # ── XGBoost ───────────────────────────────────
    print("\n" + "="*50)
    print("Training XGBoost...")
    xgb_model = train_xgboost(X_train_scaled, y_train, X_val_scaled, y_val)
    xgb_model.save_model(os.path.join(output_dir, "xgboost_v1.json"))
    print(f"✓ XGBoost saved to {output_dir}/xgboost_v1.json")

    # ── LSTM ──────────────────────────────────────
    print("\n" + "="*50)
    print(f"Preparing LSTM sequences (seq_len={LSTM_SEQ_LEN})...")
    X_seq, y_seq, seq_scaler = prepare_sequences(df, labels, seq_len=LSTM_SEQ_LEN)
    seq_split  = int(len(X_seq) * 0.8)
    lstm_model = train_lstm(X_seq[:seq_split], y_seq[:seq_split],
                            X_seq[seq_split:], y_seq[seq_split:])
    torch.save(lstm_model, os.path.join(output_dir, "lstm_v1.pt"))
    print(f"✓ LSTM saved to {output_dir}/lstm_v1.pt")

    # ── Transformer ───────────────────────────────
    print("\n" + "="*50)
    print(f"Preparing Transformer sequences (seq_len={TRANSFORMER_SEQ_LEN})...")
    # Build fixed-length windows from the scaled training features
    X_tf_seq = np.array([
        X_train_scaled[max(0, i - TRANSFORMER_SEQ_LEN):i]
        for i in range(TRANSFORMER_SEQ_LEN, len(X_train_scaled))
    ])
    y_tf_seq = y_train[TRANSFORMER_SEQ_LEN:]
    tf_split  = int(len(X_tf_seq) * 0.8)
    transformer_model = train_transformer(
        X_tf_seq[:tf_split],  y_tf_seq[:tf_split],
        X_tf_seq[tf_split:],  y_tf_seq[tf_split:],
    )
    torch.save(transformer_model, os.path.join(output_dir, "transformer_v1.pt"))
    print(f"✓ Transformer saved to {output_dir}/transformer_v1.pt")

    # ── Scaler ────────────────────────────────────
    with open(os.path.join(output_dir, "scaler_v1.pkl"), "wb") as f:
        pickle.dump(scaler, f)
    print(f"✓ Feature scaler saved to {output_dir}/scaler_v1.pkl")

    print("\n✅ All models trained and saved successfully!")
    return {
        "xgboost":     xgb_model,
        "lstm":        lstm_model,
        "transformer": transformer_model,
        "scaler":      scaler,
    }


# ── CLI ───────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train Merit-Trade AI models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch data then train (recommended first-time setup)
  python train_models.py --fetch --symbols "EUR/USD,GBP/USD,BTCUSDT" --timeframe 1h --outputpoints 5000 --output-dir ../../ml/models

  # Train from existing data
  python train_models.py --data ../../ml/models/training_data.parquet --output-dir ../../ml/models
        """,
    )

    # Fetch mode (FIX #2 — these flags were missing)
    parser.add_argument(
        "--fetch", action="store_true",
        help="Fetch OHLCV data from Twelve Data / Binance before training",
    )
    parser.add_argument(
        "--symbols", default="EUR/USD,GBP/USD,USD/JPY,AUD/USD,XAU/USD",
        help="Comma-separated list of symbols to fetch (default: 5 major forex/gold pairs)",
    )
    parser.add_argument(
        "--timeframe", default="1h",
        choices=["15m", "1h", "4h", "1d"],
        help="Candle timeframe to fetch and train on (default: 1h)",
    )
    parser.add_argument(
        "--outputpoints", type=int, default=5000,
        help="Number of candles to fetch per symbol (default: 5000)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("TWELVE_DATA_API_KEY"),
        help="Twelve Data API key (or set TWELVE_DATA_API_KEY env var)",
    )

    # Train-from-file mode
    parser.add_argument(
        "--data", default=None,
        help="Path to existing CSV or Parquet file (skip fetch)",
    )
    parser.add_argument(
        "--output-dir", default="./models",
        help="Output directory for model files (default: ./models)",
    )

    args = parser.parse_args()

    # Determine data path
    if args.fetch:
        data_path = fetch_training_data(
            symbols_str=args.symbols,
            timeframe=args.timeframe,
            outputpoints=args.outputpoints,
            output_dir=args.output_dir,
            api_key=args.api_key,
        )
    elif args.data:
        data_path = args.data
    else:
        parser.error("Provide either --fetch (to download data) or --data <path> (to use existing data).")

    train_all(data_path, args.output_dir)

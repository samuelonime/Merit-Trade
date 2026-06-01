"""
Merit-Trade AI — ML Model Training Pipeline
Trains XGBoost, LSTM, and Transformer models on historical market data.

Usage:
    python train_models.py --symbol EURUSD --timeframe 1h --output-dir ./models

Requirements:
    pip install xgboost torch scikit-learn pandas numpy ta-lib
"""
import argparse
import os
import pickle
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score
import xgboost as xgb


# ── Feature columns ───────────────────────────────

FEATURE_COLS = [
    "ema_20", "ema_50", "ema_200", "sma_20", "sma_50",
    "rsi_14", "macd_line", "macd_signal", "macd_hist",
    "atr_14", "bb_upper", "bb_middle", "bb_lower", "bb_width",
    "vwap", "volume_sma_20",
    "open", "high", "low", "close", "volume",
]

SEQUENCE_LEN = 30  # For LSTM
LABEL_HORIZON = 5  # Predict direction 5 bars ahead


# ── Label Engineering ─────────────────────────────

def create_labels(df: pd.DataFrame, horizon: int = LABEL_HORIZON, threshold: float = 0.001) -> np.ndarray:
    """
    Create BUY/SELL/HOLD labels based on forward returns.
    0 = SELL, 1 = HOLD, 2 = BUY
    """
    future_close = df["close"].shift(-horizon)
    pct_change = (future_close - df["close"]) / df["close"]

    labels = np.where(pct_change > threshold, 2,  # BUY
             np.where(pct_change < -threshold, 0,  # SELL
             1))  # HOLD
    return labels


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
        use_label_encoder=False,
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
    Input: (batch, seq_len, features)
    Output: (batch, 3) class probabilities
    """
    def __init__(self, input_size: int = 5, hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True,
        )
        self.attention = nn.MultiheadAttention(hidden_size, num_heads=4, batch_first=True)
        self.norm = nn.LayerNorm(hidden_size)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 3),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _ = self.lstm(x)
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        out = self.norm(lstm_out + attn_out)
        out = out[:, -1, :]  # Last timestep
        return self.classifier(out)


def prepare_sequences(df: pd.DataFrame, labels: np.ndarray, seq_len: int = SEQUENCE_LEN):
    """Create (sequence, label) pairs for LSTM training."""
    ohlcv_cols = ["open", "high", "low", "close", "volume"]
    data = df[ohlcv_cols].values

    # Normalize each feature independently
    scaler = StandardScaler()
    data_scaled = scaler.fit_transform(data)

    X, y = [], []
    for i in range(seq_len, len(data_scaled) - LABEL_HORIZON):
        X.append(data_scaled[i - seq_len:i])
        y.append(labels[i])

    return np.array(X), np.array(y), scaler


def train_lstm(X_train, y_train, X_val, y_val, epochs: int = 50) -> LSTMModel:
    """Train LSTM model."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nTraining LSTM on {device}")

    model = LSTMModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss(
        weight=torch.FloatTensor([1.0, 0.5, 1.0]).to(device)  # Downweight HOLD class
    )

    X_tr = torch.FloatTensor(X_train).to(device)
    y_tr = torch.LongTensor(y_train).to(device)
    X_v = torch.FloatTensor(X_val).to(device)
    y_v = torch.LongTensor(y_val).to(device)

    best_val_acc = 0
    best_state = None

    for epoch in range(epochs):
        model.train()
        # Mini-batch training
        batch_size = 64
        indices = torch.randperm(len(X_tr))
        total_loss = 0

        for i in range(0, len(X_tr), batch_size):
            batch_idx = indices[i:i + batch_size]
            xb, yb = X_tr[batch_idx], y_tr[batch_idx]

            optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()

        scheduler.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_out = model(X_v)
            val_preds = val_out.argmax(dim=1).cpu().numpy()
            val_acc = accuracy_score(y_val, val_preds)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

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
    Input: (batch, seq_len, features)
    Output: dict with "logits" and "confidence"
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
        self.input_proj = nn.Linear(input_size, d_model)
        self.pos_encoding = PositionalEncoding(d_model, dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=256,
            dropout=dropout, batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.pool = nn.AdaptiveAvgPool1d(1)
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
        x = self.input_proj(x)
        x = self.pos_encoding(x)
        x = self.encoder(x)
        pooled = self.pool(x.transpose(1, 2)).squeeze(-1)
        return {
            "logits": self.classifier(pooled),
            "confidence": self.confidence_head(pooled).squeeze(-1),
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

    model = MarketTransformer().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=1e-3, total_steps=epochs * (len(X_train) // 64 + 1)
    )
    criterion = nn.CrossEntropyLoss()

    X_tr = torch.FloatTensor(X_train).to(device)
    y_tr = torch.LongTensor(y_train).to(device)
    X_v = torch.FloatTensor(X_val).to(device)
    y_v = torch.LongTensor(y_val).to(device)

    best_val_acc = 0
    best_state = None

    for epoch in range(epochs):
        model.train()
        batch_size = 64
        indices = torch.randperm(len(X_tr))
        total_loss = 0

        for i in range(0, len(X_tr), batch_size):
            batch_idx = indices[i:i + batch_size]
            xb, yb = X_tr[batch_idx], y_tr[batch_idx]
            optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out["logits"], yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()

        model.eval()
        with torch.no_grad():
            val_out = model(X_v)
            val_preds = val_out["logits"].argmax(dim=1).cpu().numpy()
            val_acc = accuracy_score(y_val, val_preds)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

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
    df = df.dropna(subset=FEATURE_COLS)

    print(f"Dataset size: {len(df)} rows")

    # Create labels
    labels = create_labels(df)
    valid_mask = ~np.isnan(labels) & (np.arange(len(labels)) < len(labels) - LABEL_HORIZON)
    df = df[valid_mask].reset_index(drop=True)
    labels = labels[valid_mask]

    # Distribution
    unique, counts = np.unique(labels, return_counts=True)
    for cls, cnt in zip(["SELL", "HOLD", "BUY"], counts):
        print(f"  {cls}: {cnt} ({cnt/len(labels)*100:.1f}%)")

    # Train/val split (time-series: no shuffle)
    split = int(len(df) * 0.8)
    X = df[FEATURE_COLS].values.astype(np.float32)
    y = labels.astype(np.int32)

    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    # Fit scaler on training data only
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)

    # ── XGBoost ───────────────────────────────────
    print("\n" + "="*50)
    print("Training XGBoost...")
    xgb_model = train_xgboost(X_train_scaled, y_train, X_val_scaled, y_val)
    xgb_model.save_model(os.path.join(output_dir, "xgboost_v1.json"))
    print(f"✓ XGBoost saved to {output_dir}/xgboost_v1.json")

    # ── LSTM ──────────────────────────────────────
    print("\n" + "="*50)
    print("Preparing LSTM sequences...")
    X_seq, y_seq, seq_scaler = prepare_sequences(df, labels)
    seq_split = int(len(X_seq) * 0.8)
    lstm_model = train_lstm(X_seq[:seq_split], y_seq[:seq_split], X_seq[seq_split:], y_seq[seq_split:])
    torch.save(lstm_model, os.path.join(output_dir, "lstm_v1.pt"))
    print(f"✓ LSTM saved to {output_dir}/lstm_v1.pt")

    # ── Transformer ───────────────────────────────
    print("\n" + "="*50)
    print("Preparing Transformer sequences...")
    X_tf_seq = np.array([X_train_scaled[max(0, i-20):i] for i in range(20, len(X_train_scaled))])
    y_tf_seq = y_train[20:]
    tf_split = int(len(X_tf_seq) * 0.8)
    transformer_model = train_transformer(
        X_tf_seq[:tf_split], y_tf_seq[:tf_split],
        X_tf_seq[tf_split:], y_tf_seq[tf_split:]
    )
    torch.save(transformer_model, os.path.join(output_dir, "transformer_v1.pt"))
    print(f"✓ Transformer saved to {output_dir}/transformer_v1.pt")

    # ── Scaler ────────────────────────────────────
    with open(os.path.join(output_dir, "scaler_v1.pkl"), "wb") as f:
        pickle.dump(scaler, f)
    print(f"✓ Feature scaler saved to {output_dir}/scaler_v1.pkl")

    print("\n✅ All models trained and saved successfully!")
    return {"xgboost": xgb_model, "lstm": lstm_model, "transformer": transformer_model, "scaler": scaler}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Merit-Trade AI models")
    parser.add_argument("--data", required=True, help="Path to historical data (CSV or Parquet)")
    parser.add_argument("--output-dir", default="./models", help="Output directory for model files")
    args = parser.parse_args()
    train_all(args.data, args.output_dir)

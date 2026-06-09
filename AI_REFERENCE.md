# Merit-Trade AI - AI Reference

## Overview
Merit-Trade AI uses a hybrid ensemble of machine learning models to generate trading signals, score opportunities, and provide explainable reasoning. The platform is designed to support traders with data-driven insights while enforcing deterministic risk controls.

## Signal Generation
Live market data is ingested and transformed into technical features such as RSI, MACD, EMA, ATR, VWAP, and market structure indicators. Signals are created when model outputs, risk rules, and execution conditions align.

## Model Ensemble
The AI ensemble blends multiple model architectures:

- **XGBoost:** gradient boosted decision trees that score BUY/SELL/HOLD outcomes from engineering features.
- **LSTM:** recurrent network capturing sequential price behavior and signal persistence.
- **Transformer:** attention-based model analyzing multi-timeframe context and structural patterns.

Model outputs are combined into a final ensemble score used to rank and qualify trade candidates.

## AI Explanations
Each signal includes a plain-language explanation to summarize the market rationale. These explanations are intended for education and transparency, not as financial advice.

## Risk Engine
A separate deterministic risk engine validates every candidate before execution. Risk gating is mandatory and includes:

- confidence threshold checks
- spread and liquidity limits
- news and market window eligibility
- daily loss and drawdown caps
- maximum open trade limits
- stop loss / take profit sizing rules
- minimum risk/reward requirements

## Guidance
AI signals should be used with your own analysis, market knowledge, and risk management. The platform is a decision-support tool, not a substitute for professional advice.
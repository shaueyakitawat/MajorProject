# Major Project Phase 1 Report

---

## Certificate / Declaration

I wish to state that the work embodied in this work titled **"AI-Powered Options Mispricing Detection and Strategy Recommendation System"** forms my own contribution to the work carried out under the guidance of **[Guide Name]** at the **Sardar Patel Institute of Technology**. I declare that this written submission represents my ideas in my own words and where others' ideas or words have been included, I have adequately cited and referenced the original sources. I also declare that I have adhered to all principles of academic honesty and integrity and have not misrepresented or fabricated or falsified any idea/data/fact/source in my submission.

**Shaurya Kitavat**
[Roll Number]

---1

## Abstract

Options mispricing in financial markets represents a significant area of research in quantitative finance, where the deviation of observed option prices from their theoretical fair values can signal trading opportunities or market inefficiencies. Accurate detection of such mispricings requires robust volatility forecasting, precise theoretical pricing, and intelligent strategy generation. Traditional approaches often rely on implied volatility from market data, which embeds market sentiment but may not reflect the true underlying asset dynamics. Recent advances in econometric volatility modeling, particularly GARCH-family models, offer powerful alternatives for forecasting conditional volatility from historical return data.

This project proposes the development of an AI-powered quantitative pipeline for detecting options mispricing in the Indian NIFTY 50 index market. The system fetches real-time and historical market data, computes log returns, forecasts annualized volatility using an EGARCH(1,1) model, derives theoretical fair prices via the Black-Scholes model, detects mispricing by comparing market prices against fair values, classifies the prevailing volatility regime, and generates rule-based strategy recommendations. The pipeline is exposed as a RESTful API built with FastAPI, enabling seamless integration with frontend dashboards and broker systems.

In addition to the core quantitative pipeline, the system incorporates multi-timeframe analysis support (from 1-minute intraday to weekly), trading horizon-aware volatility interpretation (day trader, positional, long-term), broker adapter integration for live market data via DhanHQ and yfinance, and comprehensive analytics including signal strength scoring, regime confidence estimation, and quantitative stability validation. The expected outcome is a research-oriented, interpretable, and scalable decision-support system that assists traders and analysts in identifying potential options mispricing opportunities in the Indian derivatives market.

---

## List of Figures

| No. | Figure | Page |
|-----|--------|------|
| 1 | System architecture of the proposed options mispricing detection system | 12 |
| 2 | Data Flow Diagram of the quantitative pipeline | 12 |
| 3 | Use case diagram of the proposed system | 13 |
| 4 | Sequence diagram for mispricing detection workflow | 13 |
| 5 | Flowchart of the quantitative analysis pipeline | 14 |
| 6 | Class diagram representing system components | 15 |
| 7 | Block diagram of the proposed options mispricing detection system | 16 |

---

## List of Tables

| No. | Table | Page |
|-----|-------|------|
| 1 | Comparison of Options Pricing and Volatility Estimation Approaches | 9 |
| 2 | Summary of GARCH-Family Models Used in Financial Volatility Forecasting | 9 |
| 3 | Comparative Performance of Volatility Models in Options Pricing | 10 |
| 4 | Summary of NIFTY 50 Market Dataset Characteristics | 16 |
| 5 | Evaluation Metrics for Pipeline Validation | 17 |

---

## 1. Introduction

Options are financial derivative contracts that derive their value from an underlying asset such as a stock index, commodity, or currency. The pricing of options has been a central topic in quantitative finance since the seminal work of Black and Scholes (1973), which established a closed-form solution for European option pricing under certain market assumptions. The theoretical fair value of an option depends critically on the volatility of the underlying asset, yet volatility is the only unobservable parameter in the Black-Scholes framework—making its accurate estimation essential for detecting whether options are fairly priced, overpriced, or underpriced in the market.

In practice, market participants often rely on implied volatility (IV) extracted from observed option prices to gauge market expectations. However, implied volatility reflects market sentiment and supply-demand dynamics, which may diverge from the statistically realized volatility of the underlying asset. This divergence creates the opportunity for mispricing detection: by independently forecasting volatility from historical return data and comparing the resulting theoretical price against the observed market price, one can identify potential mispricings that may represent trading opportunities.

This project proposes the development of an AI-powered quantitative pipeline for options mispricing detection on the Indian NIFTY 50 index. The system uses an EGARCH(1,1) model to forecast conditional volatility from historical log returns, applies the Black-Scholes formula to derive a theoretical fair price, detects mispricing by comparing market and fair prices, classifies the prevailing volatility regime, and generates rule-based strategy recommendations. The entire pipeline is deployed as a production-ready FastAPI backend, containerized with Docker, and designed for integration with live broker data feeds and frontend trading dashboards.

### 1.1 Problem Statement

Retail and institutional traders in the Indian derivatives market face a persistent challenge: determining whether an option contract is fairly priced relative to the underlying asset's true volatility. The NIFTY 50 options market is one of the most liquid derivatives markets globally, yet pricing inefficiencies can and do arise due to supply-demand imbalances, event-driven volatility spikes, and behavioral biases among market participants.

Traditional diagnostic approaches for option mispricing rely heavily on implied volatility surfaces, Greeks calculations, and manual chart-based analysis, which are computationally expensive, require specialized expertise, and are difficult to scale across multiple timeframes and trading horizons. Furthermore, most commercially available tools embed implied volatility from the market itself, creating a circular dependency that may mask genuine mispricings.

Therefore, there is a need for an automated, research-oriented system that can independently forecast volatility from historical data, compute theoretical fair prices, detect mispricings, classify market regimes, and generate actionable strategy recommendations—all within a single, interpretable, and scalable pipeline. Developing such a system using modern econometric models (EGARCH) and quantitative finance theory (Black-Scholes) could provide faster, more transparent, and data-driven screening for options mispricing in the Indian market.

### 1.2 Objectives

The primary objective of this project is to develop an AI-powered quantitative pipeline capable of detecting options mispricing in the NIFTY 50 index market using EGARCH volatility forecasting and Black-Scholes theoretical pricing.

The specific objectives include:

- To fetch and preprocess historical and real-time NIFTY 50 market data from multiple data sources (yfinance, DhanHQ broker API).

- To compute log returns from closing prices and prepare clean time series data for volatility modeling.

- To implement and fit an EGARCH(1,1) model for one-step-ahead conditional volatility forecasting with dynamic annualization across multiple timeframes.

- To calculate theoretical fair option prices using the Black-Scholes pricing model with EGARCH-forecasted volatility as input.

- To detect options mispricing by comparing observed market prices against Black-Scholes fair values, applying a ±5% threshold for classification.

- To classify the prevailing volatility regime (LOW_VOL, NORMAL_VOL, HIGH_VOL, EXTREME_VOL) based on the annualized volatility forecast.

- To generate rule-based trading strategy recommendations that combine mispricing classification with volatility regime context.

- To deploy the complete pipeline as a RESTful API using FastAPI with structured JSON responses, Swagger documentation, and Docker containerization.

- To support multi-timeframe analysis (1m, 5m, 15m, 1h, daily, weekly) and trading horizon-aware volatility interpretation (day trader, positional, long-term).

### 1.3 Scope of the Project

The scope of this project focuses on the development and deployment of a complete quantitative pipeline for options mispricing detection on the Indian NIFTY 50 index. The system processes both historical data (via yfinance) and live broker data (via DhanHQ API adapter) to perform end-to-end analysis from raw market data to strategy recommendation.

The project includes market data fetching and preprocessing, log return computation, EGARCH(1,1) volatility forecasting, Black-Scholes fair pricing, mispricing detection with threshold-based classification, volatility regime classification, and rule-based strategy generation. The pipeline supports six timeframes (1m, 5m, 15m, 1h, daily, weekly) with appropriate annualization factors and three trading horizons (day trader, positional, long-term) with horizon-specific volatility multipliers.

The system also provides quantitative analytics including signal strength scoring, confidence estimation, regime transition detection, sensitivity indicators, quantitative stability validation, and human-readable explanations for all pipeline outputs. All functionality is exposed through RESTful API endpoints with structured JSON responses.

This system is intended to function as a research-oriented decision-support tool rather than an automated trading system. The outputs do not constitute financial advice or trading signals. The research aims to demonstrate how econometric volatility modeling and options pricing theory can be combined into an interpretable, scalable pipeline for quantitative research in the Indian derivatives market.

### 1.4 Technologies Used

The implementation of the proposed system involves several technologies and tools for data processing, quantitative analysis, and API deployment.

**Programming Language**

- Python 3.10

**Libraries and Frameworks**

- pandas and NumPy for data handling and numerical computation
- yfinance for historical market data fetching from Yahoo Finance
- arch for EGARCH(1,1) volatility modeling and forecasting
- statsmodels for statistical time series analysis
- scipy (scipy.stats.norm) for Black-Scholes cumulative normal distribution calculations
- FastAPI for RESTful API framework with automatic OpenAPI documentation
- Uvicorn for ASGI server deployment
- python-dateutil for robust date/time parsing of option expiry dates
- matplotlib for data visualization support

**Data Sources**

- Yahoo Finance (yfinance) — Historical OHLCV data for NIFTY 50 (^NSEI)
- DhanHQ Broker API — Live intraday candles, spot prices, and option chain data

**Deployment Tools**

- Docker for containerized deployment
- Git for version control

---

## 2. Literature Survey

Options pricing and volatility modeling have been central themes in quantitative finance research for over five decades. The Black-Scholes model (1973) established the mathematical foundation for European option pricing, while subsequent research on GARCH-family models introduced powerful frameworks for modeling time-varying volatility—a key input to any options pricing model. The intersection of volatility forecasting and mispricing detection represents an active area of research, particularly with the rise of algorithmic trading and AI-driven quantitative strategies [1, 6].

The Indian derivatives market, centered around the NIFTY 50 index, ranks among the world's most actively traded options markets by volume. The National Stock Exchange (NSE) of India processes millions of options contracts daily, creating a rich environment for studying pricing efficiency and volatility dynamics. Despite this liquidity, pricing inefficiencies persist due to behavioral biases, information asymmetry, and structural microstructure effects [8, 15]. Developing automated systems that leverage econometric models for mispricing detection presents both a research opportunity and a practical need for market participants.

### 2.1 Options Pricing: The Black-Scholes Framework

#### 2.1.1 The Black-Scholes Model

The Black-Scholes-Merton model (1973) provides a closed-form solution for pricing European call and put options under assumptions of log-normal asset price distribution, constant volatility, no dividends, frictionless markets, and continuous trading [1]. The model computes the theoretical fair value as a function of five parameters: spot price (S), strike price (K), time to expiry (T), risk-free rate (r), and volatility (σ). Despite its restrictive assumptions, BSM remains the standard benchmark for options pricing across global markets [6, 12].

#### 2.1.2 Implied Volatility and Its Limitations

In practice, traders invert the Black-Scholes formula to extract implied volatility (IV) from observed market prices. While IV provides a market-consensus view of future volatility, it embeds risk premiums, supply-demand imbalances, and behavioral biases that may not reflect the true statistical properties of the underlying asset [2, 14]. The well-documented "volatility smile" and "skew" phenomena highlight systematic deviations of implied volatility from the constant-volatility assumption, particularly for deep in-the-money and out-of-the-money options [6].

#### 2.1.3 Realized vs. Implied Volatility

The spread between realized (historical) and implied volatility has long been studied as an indicator of the volatility risk premium. Research by Bollerslev et al. (2009) demonstrated that this spread predicts future equity returns, while Carr and Wu (2009) showed that variance risk premiums contain information about options mispricing [3, 7]. Using forecasted conditional volatility (from GARCH models) as the volatility input to Black-Scholes, rather than implied volatility, provides an independent pricing benchmark that avoids the circular dependency inherent in IV-based approaches.

**Table 1: Comparison of Options Pricing and Volatility Estimation Approaches**

| Approach | Volatility Input | Advantages | Limitations | Citation |
|----------|-----------------|------------|-------------|----------|
| Black-Scholes (IV) | Implied from market | Market-consensus; liquid | Circular dependency; embeds risk premia | [1] |
| Black-Scholes (HV) | Historical realized | Independent benchmark | Backward-looking; constant assumption | [6] |
| Black-Scholes (GARCH) | EGARCH/GARCH forecast | Forward-looking; captures clustering | Model risk; parameter sensitivity | [4, 9] |
| Heston Stochastic Vol | Stochastic process | Captures smile; more realistic | Calibration complexity; computational cost | [12] |
| Monte Carlo Simulation | Simulated paths | Flexible; path-dependent options | Computationally expensive; convergence | [14] |

Among these approaches, GARCH-based volatility forecasting combined with Black-Scholes pricing offers a pragmatic balance between theoretical rigor and computational feasibility for retail quantitative research.

### 2.2 Volatility Modeling: GARCH-Family Models

#### 2.2.1 GARCH and Volatility Clustering

Engle (1982) introduced ARCH (Autoregressive Conditional Heteroskedasticity), and Bollerslev (1986) generalized it to GARCH, establishing that financial return volatility exhibits clustering—large price movements tend to follow large movements, and small movements follow small movements [4, 5]. The GARCH(1,1) model has been widely adopted as the workhorse model for conditional variance estimation in financial time series [9].

#### 2.2.2 EGARCH: Capturing Asymmetric Volatility

Nelson (1991) introduced the Exponential GARCH (EGARCH) model, which addresses two key limitations of standard GARCH: (1) it naturally ensures positivity of the conditional variance without parameter constraints, and (2) it captures the asymmetric response of volatility to positive versus negative shocks—known as the "leverage effect" in equity markets [10]. Research consistently shows that negative returns increase volatility more than positive returns of the same magnitude, making EGARCH particularly suitable for equity index volatility modeling [4, 11].

#### 2.2.3 Application to Indian Markets

Studies on the Indian equity market have demonstrated that EGARCH models outperform symmetric GARCH variants in capturing NIFTY 50 volatility dynamics. Karmakar (2005) found significant leverage effects in the Indian market, while more recent studies by Tripathy and Gil-Alana (2015) confirmed EGARCH's superiority for forecasting NSE index volatility [8, 15]. The annualized volatility forecast from EGARCH serves as a statistically grounded input for options pricing, replacing the backward-looking realized volatility assumption.

**Table 2: Summary of GARCH-Family Models Used in Financial Volatility Forecasting**

| Model | Key Property | Leverage Effect | Positivity Constraint | Primary Application | Citation |
|-------|-------------|----------------|----------------------|-------------------|----------|
| ARCH (Engle, 1982) | Conditional variance depends on past squared returns | No | Natural | Foundational volatility clustering | [4] |
| GARCH(1,1) (Bollerslev, 1986) | Adds lagged variance term; parsimonious | No | Requires constraints | Standard volatility forecasting | [5] |
| EGARCH (Nelson, 1991) | Log-linear; captures asymmetric shocks | Yes | Natural (log form) | Equity index volatility | [10] |
| GJR-GARCH (Glosten et al., 1993) | Threshold-based asymmetry | Yes | Requires constraints | Comparative studies | [9] |
| FIGARCH (Baillie et al., 1996) | Long memory in volatility | No | Requires constraints | Long-horizon forecasting | [11] |

The EGARCH(1,1) model is selected for this project due to its natural handling of leverage effects in equity markets and guaranteed positive variance forecasts.

### 2.3 AI and Algorithmic Approaches in Quantitative Trading

The field has evolved from classical econometric models to hybrid AI-driven systems that combine statistical rigor with machine learning flexibility.

- **Classical Econometrics**: GARCH-family models remain the gold standard for conditional volatility estimation. Christensen and Prabhala (1998) established that GARCH forecasts contain significant information about future realized volatility beyond what implied volatility captures [3].

- **Machine Learning**: Random Forest, Support Vector Regression (SVR), and Gradient Boosting have been applied to volatility forecasting with mixed results. Bucci (2020) found that ML models can outperform GARCH for short-horizon forecasts but struggle with interpretability [7].

- **Deep Learning**: LSTM (Long Short-Term Memory) networks and Transformer architectures have been applied to financial time series forecasting. While achieving strong in-sample performance, these models often suffer from overfitting and lack the theoretical grounding of econometric approaches [13, 16].

- **Hybrid Systems**: Recent research combines GARCH volatility outputs with ML-based trading signals. These systems use econometric models for volatility estimation and rule-based or ML-based modules for strategy generation, offering both interpretability and flexibility [14, 17].

**Table 3: Comparative Performance of Volatility Models in Options Pricing**

| Study (Year) | Model Architecture | Market | Volatility Input | Pricing Accuracy | Citation |
|-------------|-------------------|--------|-----------------|-----------------|----------|
| Duan (1995) | GARCH-BS | S&P 500 | GARCH(1,1) | Reduced pricing bias 10-15% | [6] |
| Christoffersen & Jacobs (2004) | EGARCH-BS | S&P 500 Options | EGARCH | Outperformed IV for OTM options | [3] |
| Karmakar (2005) | EGARCH | NIFTY 50 | EGARCH(1,1) | Superior to GARCH for Indian market | [8] |
| Hansen & Lunde (2005) | 330 GARCH variants | DM/USD FX | Various GARCH | GARCH(1,1) hard to beat for daily | [9] |
| Tripathy & Gil-Alana (2015) | EGARCH | NSE India | EGARCH | Best fit for NIFTY volatility | [15] |
| Bucci (2020) | ML ensemble vs GARCH | Multiple | ML + GARCH | ML better short-horizon; GARCH long | [7] |
| Liu et al. (2023) | LSTM-GARCH Hybrid | Crypto + Equity | Hybrid | Improved 5-15% over standalone | [13] |

### 2.4 Key Components for Mispricing Detection

Effective options mispricing detection systems must integrate several quantitative pillars:

- **Volatility Forecasting**: The core input to any options pricing model. EGARCH(1,1) provides one-step-ahead conditional variance forecasts that capture volatility clustering and leverage effects. The annualized forecast serves as the σ parameter in Black-Scholes [4, 10].

- **Fair Price Computation**: Black-Scholes provides the theoretical benchmark. Using EGARCH-forecasted volatility instead of implied volatility creates an independent pricing reference that avoids circular market-sentiment dependency [1, 6].

- **Mispricing Classification**: The deviation between market price and fair price, expressed as a percentage, determines classification. A ±5% threshold is commonly used in research to distinguish "overpriced," "fair," and "underpriced" options [14, 17].

- **Regime Classification**: Volatility regimes (low, normal, high, extreme) provide context for strategy selection. Hull (2018) discusses how different regimes favor different options strategies—selling premium in high-vol, buying in low-vol [12, 16].

### 2.5 Multi-Timeframe Analysis and Annualization

A critical but often overlooked aspect of volatility-based systems is the consistency of annualization across different estimation timeframes. The square root of time rule (σ_annual = σ_period × √N, where N is periods per year) is the standard scaling method under the assumption of independent increments [11]. For intraday timeframes (1-minute, 5-minute), the annualization factor is significantly larger (e.g., 252 × 390 = 98,280 for 1-minute bars), making proper scaling essential for cross-timeframe comparability.

Research by Andersen and Bollerslev (1998) demonstrated that intraday volatility estimates, when properly annualized, provide more precise measures than daily-frequency estimates alone [2]. This finding motivates the multi-timeframe support in the proposed system, allowing practitioners to analyze volatility dynamics at granularities appropriate to their trading horizon.

### 2.6 Research Gaps and Future Directions

- **Independent Volatility Benchmarks**: Most commercial tools rely on implied volatility, creating circular pricing references. There is a need for systems that use independently forecasted volatility (EGARCH) as the pricing input, providing a genuine "model vs. market" comparison [6, 14].

- **Indian Market Focus**: While GARCH-family models have been extensively studied on US and European markets, research on the Indian NIFTY 50 options market remains limited, despite it being one of the world's largest derivatives markets by volume [8, 15].

- **Multi-Timeframe Pipelines**: Most existing research operates at a single timeframe (typically daily). Scalable systems that support seamless analysis across intraday to weekly timeframes with proper annualization are lacking [2, 11].

- **Interpretability**: Quantitative trading systems often function as "black boxes." There is a critical need for systems that provide transparent explanations of why a particular mispricing signal was generated and what the underlying regime context implies for strategy selection [13, 17].

- **Broker Integration**: Academic research typically operates on historical data. Bridging the gap between research pipelines and live broker data feeds (e.g., DhanHQ for the Indian market) is necessary for practical deployment [16].

---

## 3. System Analysis and Design

This section presents the architectural and behavioral diagrams of the proposed AI-powered options mispricing detection system. These diagrams illustrate how data flows through the system, how different modules interact, and how strategy recommendations are generated from market data inputs.

### 3.1 System Architecture

**Figure 1: System architecture of the proposed options mispricing detection system**

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ Browser  │  │ Swagger  │  │ Frontend │  │ Trading Bot  │    │
│  │ (curl)   │  │ /docs    │  │ Dashboard│  │ (future)     │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │
│       └──────────────┴─────────────┴───────────────┘            │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/REST
┌────────────────────────────▼────────────────────────────────────┐
│                     FastAPI APPLICATION                          │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                    main.py                            │       │
│  │  /health  /nifty  /returns  /forecast-vol             │       │
│  │  /fair-price  /mispricing  /regime  /strategy          │       │
│  │  /metrics                                              │       │
│  └────────────────────────┬──────────────────────────────┘       │
│                           │                                      │
│  ┌────────────────────────▼──────────────────────────────┐       │
│  │              run_pipeline() — Core Engine              │       │
│  │  Data → Returns → EGARCH → BS Pricing → Mispricing    │       │
│  │  → Regime → Strategy → Analytics → Response           │       │
│  └────────────────────────┬──────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      SERVICE LAYER                               │
│  ┌────────────┐ ┌──────────────┐ ┌─────────────┐               │
│  │data_service│ │volatility_   │ │pricing_     │               │
│  │.py         │ │service.py    │ │service.py   │               │
│  │fetch_data  │ │EGARCH(1,1)   │ │Black-Scholes│               │
│  │log_returns │ │forecast_vol  │ │fair_price   │               │
│  └────────────┘ └──────────────┘ └─────────────┘               │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────┐             │
│  │mispricing_   │ │regime_       │ │strategy_    │             │
│  │service.py    │ │service.py    │ │service.py   │             │
│  │detect()      │ │classify()    │ │generate()   │             │
│  └──────────────┘ └──────────────┘ └─────────────┘             │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   INFRASTRUCTURE LAYER                            │
│  ┌────────────────┐ ┌────────────────┐ ┌──────────────────┐     │
│  │timeframe_      │ │timeframe_      │ │annualization_    │     │
│  │config.py       │ │adapter.py      │ │engine.py         │     │
│  │validate/map    │ │normalize_df    │ │√t scaling        │     │
│  └────────────────┘ └────────────────┘ └──────────────────┘     │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              broker_adapter.py                         │       │
│  │  fetch_spot()  fetch_option_chain()  normalize()      │       │
│  │  yfinance provider  |  DhanHQ provider                │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

The system architecture illustrates the overall workflow of the proposed quantitative framework. Market data is fetched from multiple providers (yfinance for historical data, DhanHQ for live broker data) through the broker adapter layer. The data flows through the service layer where each module performs a specific quantitative computation—log returns, EGARCH volatility forecasting, Black-Scholes pricing, mispricing detection, regime classification, and strategy generation. The infrastructure layer handles multi-timeframe configuration, dataframe normalization, and dynamic annualization. All results are exposed through the FastAPI application layer as structured JSON endpoints.

### 3.2 Data Flow Diagram

**Figure 2: Data Flow Diagram of the quantitative pipeline**

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ yfinance │────▶│ data_service  │────▶│ Log Returns  │────▶│  EGARCH(1,1) │
│ / DhanHQ │     │ fetch + clean │     │ computation  │     │  Volatility  │
└──────────┘     └──────────────┘     └──────────────┘     │  Forecast    │
                                                            └──────┬───────┘
                                                                   │
                       ┌───────────────────────────────────────────┘
                       ▼
              ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
              │ Annualization │────▶│ Black-Scholes│────▶│  Mispricing  │
              │ Engine (√t)  │     │ Fair Pricing │     │  Detection   │
              └──────────────┘     └──────────────┘     └──────┬───────┘
                                                               │
                       ┌───────────────────────────────────────┘
                       ▼
              ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
              │   Regime     │────▶│   Strategy   │────▶│  Analytics   │
              │Classification│     │  Generation  │     │  + Response  │
              └──────────────┘     └──────────────┘     └──────────────┘
```

The Data Flow Diagram describes how information moves through the pipeline. Market data (OHLCV) is fetched from external providers and preprocessed. Log returns are computed from closing prices and fed into the EGARCH(1,1) model. The resulting conditional volatility forecast is annualized using the dynamic annualization engine, then used as input to the Black-Scholes pricing model. The fair price is compared against the market price to detect mispricing. Volatility regime classification and strategy generation follow sequentially. The final analytics payload is assembled and returned to the client through the API.

### 3.3 Use Case Diagram

**Figure 3: Use case diagram of the proposed system**

```
                    ┌─────────────────────────────────────────────┐
                    │        Options Mispricing Detection          │
                    │                 System                       │
                    │                                              │
  ┌─────────┐      │  ┌─────────────────────────────────┐        │
  │         │      │  │ Fetch NIFTY Market Data          │        │
  │ Trader/ │─────▶│  └─────────────────────────────────┘        │
  │ Analyst │      │  ┌─────────────────────────────────┐        │
  │         │─────▶│  │ View Log Returns                 │        │
  │         │      │  └─────────────────────────────────┘        │
  │         │─────▶│  ┌─────────────────────────────────┐        │
  │         │      │  │ Get Forecasted Volatility        │        │
  │         │─────▶│  └─────────────────────────────────┘        │
  │         │      │  ┌─────────────────────────────────┐        │
  │         │─────▶│  │ Get Fair Price                   │        │  ┌───────────┐
  │         │      │  └─────────────────────────────────┘        │  │           │
  │         │─────▶│  ┌─────────────────────────────────┐        │  │ yfinance  │
  │         │      │  │ Detect Mispricing                │        │◀─│ Provider  │
  │         │─────▶│  └─────────────────────────────────┘        │  │           │
  │         │      │  ┌─────────────────────────────────┐        │  └───────────┘
  │         │─────▶│  │ Classify Volatility Regime       │        │
  │         │      │  └─────────────────────────────────┘        │  ┌───────────┐
  │         │─────▶│  ┌─────────────────────────────────┐        │  │           │
  └─────────┘      │  │ Get Full Strategy Recommendation │        │◀─│  DhanHQ   │
                    │  └─────────────────────────────────┘        │  │  Broker   │
  ┌─────────┐      │  ┌─────────────────────────────────┐        │  │           │
  │         │─────▶│  │ Monitor System Health            │        │  └───────────┘
  │  DevOps │─────▶│  └─────────────────────────────────┘        │
  │         │      │  ┌─────────────────────────────────┐        │
  │         │      │  │ View Service Metrics             │        │
  └─────────┘      │  └─────────────────────────────────┘        │
                    └─────────────────────────────────────────────┘
```

The use case diagram represents interactions between external actors and the system. The primary actors are traders/analysts and DevOps engineers. Traders access market data, view pipeline outputs (volatility, fair price, mispricing, regime, strategy), and configure analysis parameters (timeframe, trading horizon, data provider). DevOps engineers monitor system health and service metrics. External data providers (yfinance, DhanHQ) serve as secondary actors that supply market data.

### 3.4 Sequence Diagram

**Figure 4: Sequence diagram for mispricing detection workflow**

```
Trader        FastAPI        run_pipeline     data_service    volatility_svc   pricing_svc    mispricing_svc  regime_svc   strategy_svc
  │               │               │               │               │               │               │              │              │
  │ GET /strategy │               │               │               │               │               │              │              │
  │──────────────▶│               │               │               │               │               │              │              │
  │               │ run_pipeline()│               │               │               │               │              │              │
  │               │──────────────▶│               │               │               │               │              │              │
  │               │               │ fetch_data()  │               │               │               │              │              │
  │               │               │──────────────▶│               │               │               │              │              │
  │               │               │  OHLCV data   │               │               │               │              │              │
  │               │               │◀──────────────│               │               │               │              │              │
  │               │               │ log_returns() │               │               │               │              │              │
  │               │               │──────────────▶│               │               │               │              │              │
  │               │               │  returns_df   │               │               │               │              │              │
  │               │               │◀──────────────│               │               │               │              │              │
  │               │               │ forecast_vol()│               │               │               │              │              │
  │               │               │──────────────────────────────▶│               │               │              │              │
  │               │               │  EGARCH σ     │               │               │               │              │              │
  │               │               │◀──────────────────────────────│               │               │              │              │
  │               │               │ annualize(σ)  │               │               │               │              │              │
  │               │               │───────┐       │               │               │               │              │              │
  │               │               │       │       │               │               │               │              │              │
  │               │               │◀──────┘       │               │               │               │              │              │
  │               │               │ bs_price()    │               │               │               │              │              │
  │               │               │──────────────────────────────────────────────▶│               │              │              │
  │               │               │  fair_price   │               │               │               │              │              │
  │               │               │◀──────────────────────────────────────────────│               │              │              │
  │               │               │ detect()      │               │               │               │              │              │
  │               │               │──────────────────────────────────────────────────────────────▶│              │              │
  │               │               │  mispricing   │               │               │               │              │              │
  │               │               │◀──────────────────────────────────────────────────────────────│              │              │
  │               │               │ classify()    │               │               │               │              │              │
  │               │               │────────────────────────────────────────────────────────────────────────────▶│              │
  │               │               │  regime       │               │               │               │              │              │
  │               │               │◀────────────────────────────────────────────────────────────────────────────│              │
  │               │               │ generate()    │               │               │               │              │              │
  │               │               │──────────────────────────────────────────────────────────────────────────────────────────▶│
  │               │               │  strategy     │               │               │               │              │              │
  │               │               │◀──────────────────────────────────────────────────────────────────────────────────────────│
  │               │  JSON response│               │               │               │               │              │              │
  │               │◀──────────────│               │               │               │               │              │              │
  │ JSON response │               │               │               │               │               │              │              │
  │◀──────────────│               │               │               │               │               │              │              │
```

The sequence diagram shows the step-by-step interaction between system components. After the trader sends a request, the FastAPI layer invokes `run_pipeline()`, which orchestrates the sequential execution of all service modules. Historical data is fetched and preprocessed, EGARCH volatility is forecasted and annualized, Black-Scholes computes the fair price, mispricing is detected, the regime is classified, and a strategy recommendation is generated. The complete analytics payload is returned as a structured JSON response.

### 3.5 System Flowchart

**Figure 5: Flowchart of the quantitative analysis pipeline**

```
                        ┌─────────────┐
                        │   START     │
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │ Validate    │
                        │ timeframe & │
                        │ horizon     │
                        └──────┬──────┘
                               │
                    ┌──────────▼──────────┐
                    │ Live broker data    │
                    │ provided?           │
                    └──────┬──────┬───────┘
                     Yes   │      │  No
                ┌──────────▼┐  ┌──▼──────────┐
                │ Validate  │  │ Fetch via   │
                │ live data │  │ yfinance    │
                └──────┬────┘  └──────┬──────┘
                       │              │
                    ┌──▼──────────────▼──┐
                    │ Normalize DataFrame│
                    │ (timeframe_adapter)│
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Compute Log Returns│
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Validate returns   │
                    │ (≥100 obs, no NaN) │
                    └──────┬──────┬──────┘
                     Pass  │      │ Fail
                           │  ┌───▼────┐
                           │  │ HTTP   │
                           │  │ 500    │
                           │  └────────┘
                    ┌──────▼─────────────┐
                    │  EGARCH(1,1)       │
                    │  Volatility        │
                    │  Forecast          │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Dynamic            │
                    │ Annualization (√t) │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Sanitize Volatility│
                    │ [0.01, 2.0] bounds │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Apply Horizon      │
                    │ Multiplier         │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Black-Scholes      │
                    │ Fair Pricing       │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Determine Market   │
                    │ Price (ATM option  │
                    │ or fallback)       │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Detect Mispricing  │
                    │ (±5% threshold)    │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Classify Volatility│
                    │ Regime             │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Generate Strategy  │
                    │ Recommendation     │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Compute Analytics  │
                    │ (signals, scores,  │
                    │  diagnostics)      │
                    └──────────┬─────────┘
                               │
                    ┌──────────▼─────────┐
                    │ Return JSON        │
                    │ Response           │
                    └──────────┬─────────┘
                               │
                        ┌──────▼──────┐
                        │    END      │
                        └─────────────┘
```

The flowchart describes the logical workflow followed by the system. Starting from input validation, the data undergoes fetching, normalization, log return computation, EGARCH volatility forecasting, annualization, Black-Scholes pricing, mispricing detection, regime classification, and strategy generation. Validation checkpoints are placed throughout the pipeline to ensure data integrity. The final step assembles all analytics and returns the structured response.

### 3.6 Class Diagram

**Figure 6: Class diagram representing system components**

```
┌──────────────────────────┐
│      FastAPI (main.py)   │
├──────────────────────────┤
│ - app: FastAPI           │
│ - METRICS: dict          │
│ - APP_VERSION: str       │
├──────────────────────────┤
│ + root()                 │
│ + health_check()         │
│ + get_nifty_data()       │
│ + get_log_returns()      │
│ + get_forecast_vol()     │
│ + get_fair_price()       │
│ + get_mispricing()       │
│ + get_regime()           │
│ + get_strategy()         │
│ + get_metrics()          │
│ + run_pipeline()         │
│ + validate_symbol()      │
│ + sanitize_volatility()  │
│ + select_atm_option()    │
│ + parse_option_expiry()  │
└────────────┬─────────────┘
             │ uses
    ┌────────┴──────────────────────────────────────┐
    │            │            │          │           │
    ▼            ▼            ▼          ▼           ▼
┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│  data_   ││volatility││ pricing_ ││mispricing││ regime_  │
│ service  ││ _service ││ service  ││ _service ││ service  │
├──────────┤├──────────┤├──────────┤├──────────┤├──────────┤
│+fetch_   ││+forecast_││+black_   ││+detect_  ││+classify_│
│ nifty_   ││ volatil- ││ scholes_ ││ mispric- ││ volatil- │
│ data()   ││ ity()    ││ price()  ││ ing()    ││ ity_     │
│+compute_ ││          ││          ││          ││ regime() │
│ log_     ││          ││          ││          ││          │
│ returns()││          ││          ││          ││          │
└──────────┘└──────────┘└──────────┘└──────────┘└──────────┘
                                                      │
    ┌──────────┐                                      │
    │strategy_ │◀─────────────────────────────────────┘
    │ service  │
    ├──────────┤     ┌─────────────────────────────────────┐
    │+generate_│     │        INFRASTRUCTURE LAYER          │
    │ strategy││     ├─────────────────────────────────────┤
    └──────────┘     │ timeframe_config                     │
                     │   + validate_timeframe()             │
    ┌──────────┐     │   + get_annualization_factor()       │
    │ broker_  │     │   + get_default_timeframe()          │
    │ adapter  │     │ timeframe_adapter                    │
    ├──────────┤     │   + normalize_timeframe_dataframe()  │
    │+fetch_   │     │   + validate_normalized_dataframe()  │
    │ spot()   │     │ annualization_engine                 │
    │+fetch_   │     │   + apply_dynamic_annualization()    │
    │ option_  │     │   + reverse_annualization()          │
    │ chain()  │     └─────────────────────────────────────┘
    │+normalize│
    │ _broker_ │
    │ payload()│
    └──────────┘
```

The class diagram represents the structural design of the system. Core modules include data fetching and preprocessing (data_service), EGARCH volatility forecasting (volatility_service), Black-Scholes option pricing (pricing_service), mispricing detection (mispricing_service), regime classification (regime_service), strategy recommendation (strategy_service), and broker data normalization (broker_adapter). The infrastructure layer provides timeframe configuration, dataframe normalization, and annualization utilities. The FastAPI application layer orchestrates all modules through the central `run_pipeline()` function.

---

## 4. Design and Methodology

### 4.1 System Overview

The objective of the proposed system is to automatically detect options mispricing in the NIFTY 50 index market and provide interpretable strategy recommendations based on quantitative analysis. The system takes market data as input and outputs a comprehensive analytics payload including volatility forecast, fair price, mispricing classification, regime label, strategy recommendation, and supporting diagnostics.

The overall architecture consists of seven major pipeline stages:

1. Market Data Fetching and Preprocessing
2. Log Return Computation
3. EGARCH(1,1) Volatility Forecasting
4. Dynamic Annualization
5. Black-Scholes Fair Pricing
6. Mispricing Detection and Regime Classification
7. Strategy Recommendation and Analytics Generation

Figure 7 illustrates the proposed system block diagram.

**Figure 7: Block diagram of the proposed options mispricing detection system**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          QUANTITATIVE PIPELINE                              │
│                                                                             │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Market  │─▶│   Log    │─▶│ EGARCH   │─▶│ Dynamic  │─▶│  Black-  │      │
│  │  Data   │  │ Returns  │  │  (1,1)   │  │ Annual-  │  │ Scholes  │      │
│  │ Fetch   │  │          │  │ Forecast │  │ ization  │  │ Pricing  │      │
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘  └────┬─────┘      │
│                                                               │             │
│                                                               ▼             │
│  ┌──────────────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  Analytics Engine    │◀─│ Strategy │◀─│ Regime   │◀─│Mispricing│       │
│  │  (scores, signals,   │  │ Generate │  │ Classify │  │ Detect   │       │
│  │   diagnostics)       │  │          │  │          │  │          │       │
│  └──────────────────────┘  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Dataset Used

The system operates on NIFTY 50 (^NSEI) market data fetched from Yahoo Finance via the yfinance library. The dataset contains OHLCV (Open, High, Low, Close, Volume) data at multiple timeframes. For live deployment, the DhanHQ broker API provides real-time intraday candles and option chain data.

The pipeline requires a minimum of 2,000 candles per timeframe for robust EGARCH estimation, with at least 100 data points after log return computation for stable volatility forecasting.

**Table 4: Summary of NIFTY 50 Market Dataset Characteristics**

| Parameter | Value |
|-----------|-------|
| Underlying Asset | NIFTY 50 Index (^NSEI) |
| Data Provider (Historical) | Yahoo Finance (yfinance) |
| Data Provider (Live) | DhanHQ Broker API |
| Minimum Candles Required | 2,000 per timeframe |
| Minimum EGARCH Observations | 100 log returns |
| Supported Timeframes | 1m, 5m, 15m, 1h, daily, weekly |
| Data Fields | Date, Open, High, Low, Close, Volume |
| Index Timezone | Asia/Kolkata (IST) |
| Risk-Free Rate (assumed) | 6% (Indian government bond rate) |
| Option Type (default) | European Call (ATM) |

The dataset is dynamically fetched based on the requested timeframe with appropriate historical windows (e.g., 7 days for 1-minute, 10 years for daily, max available for weekly).

### 4.3 Design and Methodology 1: Market Data Fetching and Log Return Computation

The input stage handles data acquisition and preprocessing. The `data_service` module maps ticker symbols to provider-specific identifiers (e.g., "NIFTY" → "^NSEI" for yfinance), selects appropriate fetch windows based on the requested timeframe, and downloads OHLCV data with automatic adjustment for corporate actions.

The `timeframe_adapter` module then normalizes the raw dataframe by:
- Validating required columns (Date, Open, High, Low, Close, Volume)
- Converting dates to datetime format
- Sorting chronologically and removing duplicate timestamps
- Forward-filling missing values
- Ensuring numeric dtypes for OHLCV columns

Log returns are computed as:

$$r_t = \ln\left(\frac{C_t}{C_{t-1}}\right)$$

where $C_t$ is the closing price at time $t$. Log returns are preferred over simple returns due to their additive property across time periods and approximate normality for small returns.

### 4.4 Design and Methodology 2: EGARCH Volatility Forecasting and Annualization

The volatility forecasting module implements the EGARCH(1,1) model proposed by Nelson (1991). The log returns are scaled to percentage form (multiplied by 100) before fitting the model.

The EGARCH(1,1) conditional variance equation (in log form) is:

$$\ln(\sigma_t^2) = \omega + \alpha \left(\frac{|\varepsilon_{t-1}|}{\sigma_{t-1}} - \sqrt{2/\pi}\right) + \gamma \frac{\varepsilon_{t-1}}{\sigma_{t-1}} + \beta \ln(\sigma_{t-1}^2)$$

where $\omega$ is the constant, $\alpha$ captures the magnitude effect, $\gamma$ captures the asymmetric (leverage) effect, and $\beta$ captures volatility persistence.

The model is fitted using maximum likelihood estimation via the `arch` library with normal distribution assumed for innovations. One-step-ahead conditional variance forecast is extracted, and the forecasted volatility (standard deviation) is converted from percentage scale back to decimal.

**Dynamic Annualization**: The `annualization_engine` applies the square root of time scaling rule:

$$\sigma_{annual} = \sigma_{period} \times \sqrt{N}$$

where $N$ is the number of periods per year (e.g., $N = 252$ for daily, $N = 252 \times 78 = 19{,}656$ for 5-minute).

**Volatility Sanitization**: The sanitized volatility is clamped to [0.01, 2.0] (1%–200%) with NaN/infinity fallback to 0.15 (15%).

**Horizon Adjustment**: A trading horizon multiplier scales the volatility for interpretation:
- Day Trader: ×1.15 (short-term sensitive)
- Positional: ×1.0 (balanced)
- Long-Term: ×0.85 (smoothed)

### 4.5 Design and Methodology 3: Black-Scholes Fair Pricing

The Black-Scholes model computes the theoretical fair value for a European call option:

$$C = S \cdot N(d_1) - K \cdot e^{-rT} \cdot N(d_2)$$

where:

$$d_1 = \frac{\ln(S/K) + (r + \sigma^2 / 2) \cdot T}{\sigma \sqrt{T}}, \quad d_2 = d_1 - \sigma \sqrt{T}$$

- $S$ = spot price (from latest close or live broker data)
- $K$ = strike price (set to ATM, i.e., $K = S$)
- $T$ = time to expiry in years (parsed from option chain or default 0.1 years)
- $r$ = risk-free rate (0.06, Indian government bond rate)
- $\sigma$ = horizon-adjusted, expiry-scaled volatility from EGARCH
- $N(\cdot)$ = cumulative standard normal distribution (scipy.stats.norm.cdf)

The expiry-scaled volatility is computed as $\sigma_{expiry} = \sigma_{horizon} \times \sqrt{T}$ before input to Black-Scholes.

### 4.6 Design and Methodology 4: Mispricing Detection

The mispricing detection module compares the observed market price against the Black-Scholes fair value:

$$\text{deviation} = \frac{P_{market} - P_{fair}}{P_{fair}}$$

Classification is based on a ±5% threshold:
- **Overpriced**: deviation > +5%
- **Fair**: −5% ≤ deviation ≤ +5%
- **Underpriced**: deviation < −5%

The market price is determined from the at-the-money (ATM) call option's mid-price (bid+ask)/2 when live broker data is available, or defaults to fair_price × 1.03 as a temporary fallback for historical-only mode.

### 4.7 Design and Methodology 5: Regime Classification and Strategy Generation

**Volatility Regime Classification** uses threshold-based rules on the annualized volatility forecast:

| Regime | Volatility Range |
|--------|-----------------|
| LOW_VOL | σ < 15% |
| NORMAL_VOL | 15% ≤ σ < 25% |
| HIGH_VOL | 25% ≤ σ < 40% |
| EXTREME_VOL | σ ≥ 40% |

**Strategy Generation** uses a rule-based mapping that combines mispricing classification with the volatility regime. The 12-cell strategy matrix (3 mispricing states × 4 regime states) produces specific recommendations:

| Mispricing \ Regime | LOW_VOL | NORMAL_VOL | HIGH_VOL | EXTREME_VOL |
|-------------------|---------|------------|----------|-------------|
| **Underpriced** | Long volatility (high conf.) | Buy options (med conf.) | Buy with caution (med) | Wait for stability (low) |
| **Fair** | No strong edge (low) | No strong edge (low) | Fairly priced (low) | Wait for opportunity (low) |
| **Overpriced** | Sell premium cautiously (med) | Sell premium (med) | Credit spread (high) | High risk short vol (med) |

**Table 5: Evaluation Metrics for Pipeline Validation**

| Metric | Description |
|--------|-------------|
| Pipeline Health | OK if volatility > 0 and fair_price > 0; CHECK_DATA otherwise |
| Confidence Score | min(1.0, \|deviation\| × 5); thresholds: ≥0.7 Strong, ≥0.4 Moderate, else Weak |
| Signal Strength | \|deviation\| × volatility forecast |
| Regime Confidence | Distance from nearest regime boundary / (regime width / 2) |
| Quant Stability Score | (validation_flags_avg) × signal_strength_normalized |
| Analytics Health Score | 1.0 baseline, penalized for pipeline issues and low confidence |

---

## References

[1] F. Black and M. Scholes, "The Pricing of Options and Corporate Liabilities," *Journal of Political Economy*, vol. 81, no. 3, pp. 637–654, 1973.

[2] T. G. Andersen and T. Bollerslev, "Answering the Skeptics: Yes, Standard Volatility Models Do Provide Accurate Forecasts," *International Economic Review*, vol. 39, no. 4, pp. 885–905, 1998.

[3] B. J. Christoffersen and K. Jacobs, "The Importance of the Loss Function in Option Valuation," *Journal of Financial Economics*, vol. 72, no. 2, pp. 291–318, 2004.

[4] R. F. Engle, "Autoregressive Conditional Heteroscedasticity with Estimates of the Variance of United Kingdom Inflation," *Econometrica*, vol. 50, no. 4, pp. 987–1007, 1982.

[5] T. Bollerslev, "Generalized Autoregressive Conditional Heteroskedasticity," *Journal of Econometrics*, vol. 31, no. 3, pp. 307–327, 1986.

[6] J. C. Duan, "The GARCH Option Pricing Model," *Mathematical Finance*, vol. 5, no. 1, pp. 13–32, 1995.

[7] A. Bucci, "Realized Volatility Forecasting with Neural Networks," *Journal of Financial Econometrics*, vol. 18, no. 3, pp. 502–531, 2020.

[8] M. Karmakar, "Modeling Conditional Volatility of the Indian Stock Markets," *Vikalpa*, vol. 30, no. 3, pp. 21–37, 2005.

[9] P. R. Hansen and A. Lunde, "A Forecast Comparison of Volatility Models: Does Anything Beat a GARCH(1,1)?," *Journal of Applied Econometrics*, vol. 20, no. 7, pp. 873–889, 2005.

[10] D. B. Nelson, "Conditional Heteroskedasticity in Asset Returns: A New Approach," *Econometrica*, vol. 59, no. 2, pp. 347–370, 1991.

[11] R. T. Baillie, T. Bollerslev, and H. O. Mikkelsen, "Fractionally Integrated Generalized Autoregressive Conditional Heteroskedasticity," *Journal of Econometrics*, vol. 74, no. 1, pp. 3–30, 1996.

[12] J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed. Pearson, 2018.

[13] S. Liu, A. Borovykh, L. A. Grzelak, and C. W. Oosterlee, "A Neural Network-Based Framework for Financial Model Calibration," *Journal of Mathematics in Industry*, vol. 9, art. 9, 2019.

[14] P. Wilmott, *Paul Wilmott on Quantitative Finance*, 2nd ed. Wiley, 2006.

[15] T. Tripathy and L. A. Gil-Alana, "Modelling Time-Varying Volatility in the Indian Stock Returns: Some Empirical Evidence," *Review of Development Finance*, vol. 5, no. 2, pp. 91–97, 2015.

[16] M. López de Prado, *Advances in Financial Machine Learning*. Wiley, 2018.

[17] E. Chan, *Algorithmic Trading: Winning Strategies and Their Rationale*. Wiley, 2013.

---

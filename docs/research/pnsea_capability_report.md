# PNSEA Capability Report

**Scope:** source-level verification of the repository's PNSEA integration for NIFTY option-chain data.  
**Status:** read-only investigation. No application code, datasets, configuration, or LaTeX files were modified.

## 1. Package name, version, and source

The declared dependency is `pnsea==1.1` in [`requirements.txt`](../../requirements.txt):15. PyPI metadata for version 1.1 identifies the project as “A powerful, stealthy unofficial NSE India API wrapper,” with author Anil Sardiwal, dependencies `stealthkit` and `pandas`, and homepage/source repository [`theonlyanil/pnsea`](https://github.com/theonlyanil/pnsea). The published package metadata is available at [PyPI pnsea 1.1 JSON](https://pypi.org/pypi/pnsea/1.1/json).

The current repository source is not a vendored copy of PNSEA. The local virtual environment was inspected: `pnsea` is not installed (`find_spec("pnsea")` returned `None` and no PNSEA distribution metadata was present). `curl_cffi` is installed, but that does not establish that PNSEA itself is installed or runnable. Accordingly:

* **Declared version:** `1.1`.
* **Installed local version:** **NOT INSTALLED / UNVERIFIABLE at runtime**.
* **Upstream source:** [https://github.com/theonlyanil/pnsea](https://github.com/theonlyanil/pnsea).
* **Source artifact inspected:** [published PyPI 1.1 source archive](https://files.pythonhosted.org/packages/13/e8/0e910ff863b6dfa07a396430b2151a59c93051ec72ef58a1e8c170b2df15/pnsea-1.1.tar.gz), including `indicesOptions.py`, `utils.py`, and `nsesession.py`.
* **Current upstream README:** identifies a later v1.2.1 release; that later source must not be assumed identical to the repository's declared 1.1 dependency.

The repository has a compatibility shim in [`option_chain_service.py`](../../backend/services/option_chain_service.py):240-252 that aliases `curl_cffi.requests.RequestException` when absent before importing `NSE`. This is application compatibility code, not a PNSEA API.

## 2. Every PNSEA API/function used

### Directly used by repository code

The only PNSEA symbol imported is `NSE`:

```python
from pnsea import NSE
_PNSEA_INSTANCE = NSE()
```

This occurs in [`_get_pnsea_session`](../../backend/services/option_chain_service.py):240-252. The resulting object is cached process-wide in `_PNSEA_INSTANCE`.

The only PNSEA data API directly called by the repository is:

```python
nse.options.option_chain(symbol)
nse.options.option_chain(symbol, expiry_date=target_exp)
```

This occurs in [`_fetch_chain_from_pnsea`](../../backend/services/option_chain_service.py):274-298.

### Indirectly invoked inside PNSEA

In the published PNSEA 1.1 source, `IndicesOptions.option_chain` calls `expiry_dates(symbol)` when no expiry is supplied, then calls the NSE option-chain endpoint. The repository does **not** call `nse.options.expiry_dates` directly. It receives the returned expiry list as the second element of the tuple.

The documented return shape is:

```text
(DataFrame, expiry_dates, underlying_value)
```

The repository consumes all three values as `df, expiries, live_spot` ([`option_chain_service.py`](../../backend/services/option_chain_service.py):285-298).

### Repository wrappers, not PNSEA APIs

These application functions call the PNSEA path but are not library functions:

* [`get_full_chain`](../../backend/services/option_chain_service.py):460-490 — five-second cache, PNSEA-first routing, SQLite fallback.
* [`get_multi_expiry_chains`](../../backend/services/option_chain_service.py):493-535 — requests the first returned expiry and then additional returned expiries concurrently.
* [`fetch_option_chain`](../../backend/services/option_chain_service.py):538-563 — converts the application chain into calls/puts DataFrames.
* [`get_available_expiries`](../../backend/services/option_chain_service.py):566-568 — reads `available_expiries` from the application response.
* [`record_snapshot`](../../scripts/record_nifty_snapshots.py):73-126 — persists the application response to SQLite.

No PNSEA historical-download, tick-history, trade-history, archive, or replay API is used.

## 3. What data PNSEA supplies here

### Live versus historical status

**Verified implementation:** the PNSEA 1.1 option method calls the NSE current option-chain endpoint and extracts the current response's `records` and `filtered.data` blocks. It returns the current underlying value, currently available expiry dates, and current chain rows.

Therefore the integration is:

| Capability | Status | Evidence |
|---|---|---|
| Current/live option-chain data | **IMPLEMENTED, subject to runtime availability** | `nse.options.option_chain(...)` in [`_fetch_chain_from_pnsea`](../../backend/services/option_chain_service.py):274-298. |
| One current chain snapshot | **IMPLEMENTED** | The application adds its own retrieval timestamp and returns the chain at [`option_chain_service.py`](../../backend/services/option_chain_service.py):421-452. |
| Historical option quotes | **NOT PROVIDED / NOT CONFIRMED** | No historical date, quote timestamp, or archive API is used. |
| Historical option chains | **NOT PROVIDED / NOT CONFIRMED** | `expiry_date` selects a current chain by maturity; it is not a historical observation date. |
| Historical trades/ticks | **NOT PROVIDED / NOT CONFIRMED** | No PNSEA trade/tick-history API is called. |

The presence of an `expiry_date` argument must not be interpreted as historical access. In PNSEA 1.1 it is used to select the expiry parameter of the current NSE option-chain request.

## 4. Expired contracts

**Status: UNVERIFIED / effectively unsupported by the inspected integration.**

PNSEA returns an `expiryDates` list from the current option-chain response and accepts one selected expiry. The source does not establish that expired contracts are returned, archived, or queryable. The repository selects from the returned current list and does not request a historical date or expired-contract archive.

Consequently, the integration cannot be used as evidence that expired NIFTY contracts are available. An expired-contract test against a real response would be required, and the local PNSEA package is not installed to perform that test.

## 5. Available fields and transformations

### 5.1 Fields exposed by PNSEA 1.1

The published PNSEA 1.1 `utils.py` extracts these fields for both CE and PE and prefixes them with `CE_` or `PE_`:

* `openInterest`
* `changeinOpenInterest`
* `impliedVolatility`
* `lastPrice`
* `totalTradedVolume`
* `bidQty`
* `bidprice`
* `askQty`
* `askPrice`

The top-level strike field is `strikePrice`; the option-chain metadata supplies `underlyingValue` and `expiryDates`. These fields are documented in the package source at [PNSEA 1.1 `indicesOptions.py`](https://github.com/theonlyanil/pnsea/blob/main/pnsea/derivatives/indicesOptions.py) and [PNSEA 1.1 `utils.py` in the published source layout](https://github.com/theonlyanil/pnsea/tree/main/pnsea/derivatives). The GitHub default branch now represents a later release, so exact branch-to-1.1 equivalence is **UNVERIFIED** from GitHub alone; the PyPI 1.1 source archive was the version-specific evidence.

### 5.2 Repository-level availability

| Requested field | PNSEA/application path | Status |
|---|---|---|
| Timestamp | PNSEA tuple does not expose a documented exchange timestamp; application creates `datetime.now().isoformat()` | **Retrieval timestamp only in application** |
| Spot | `underlyingValue` returned as `live_spot`; used as `spot_price` | **Available** |
| Expiry | Returned `expiryDates`; selected expiry stored as `expiry_date` | **Available as current-chain metadata** |
| Strike | `strikePrice` mapped to `strike` | **Available** |
| CE/PE | Nested `CE` and `PE` rows mapped to application `call` and `put` | **Available** |
| Bid | `CE_bidprice` / `PE_bidprice` expected by application | **Available when response field is present; fallback may be manufactured** |
| Ask | `CE_askPrice` / `PE_askPrice` expected by application | **Available when response field is present; fallback may be manufactured** |
| LTP | `CE_lastPrice` / `PE_lastPrice` mapped to `ltp` | **Available** |
| IV | `CE_impliedVolatility` / `PE_impliedVolatility` initially read as percentage | **Available, but application usually replaces it with recomputed IV** |
| Volume | `CE_totalTradedVolume` / `PE_totalTradedVolume` | **Available** |
| OI | `CE_openInterest` / `PE_openInterest` | **Available** |

The repository only retains a depth-limited strike subset around ATM. In [`_fetch_chain_from_pnsea`](../../backend/services/option_chain_service.py):421-440, `depth=15` by default selects at most 31 strikes centered around the closest strike to spot. This is not a full historical or necessarily full live chain archive.

## 6. Timestamp semantics

**Status: retrieval timestamp, not verified exchange timestamp.**

After receiving the PNSEA response, the repository sets:

```python
now_iso = dt.datetime.now().isoformat()
```

and returns it as `timestamp` ([`option_chain_service.py`](../../backend/services/option_chain_service.py):302-306 and 447-452). The snapshot recorder stores that application timestamp ([`record_nifty_snapshots.py`](../../scripts/record_nifty_snapshots.py):83-108).

The PNSEA option-chain tuple consumed by this code contains a DataFrame, expiry list, and underlying value, not an exchange quote timestamp. The LTP, bid, ask, IV, volume, and OI therefore have no separately retained exchange timestamp in this integration. The recorder's timestamp identifies when the application constructed or received the response, not necessarily when each underlying NSE field was observed.

The five-second `_CHAIN_CACHE` in [`get_full_chain`](../../backend/services/option_chain_service.py):460-483 can return a response captured shortly earlier than the caller's request. The precise exchange timestamp and field staleness are **UNVERIFIED**.

## 7. Rate limits, authentication, reliability, and limitations

### Rate limits

**Exact NSE or PNSEA rate limits: UNVERIFIED.** The upstream README describes Stealthkit as intended to avoid rate limits and blocks, but does not establish a numeric quota or a guaranteed service level. The application adds:

* a process-global five-second cache by default ([`option_chain_service.py`](../../backend/services/option_chain_service.py):37-38 and 460-483);
* up to three PNSEA attempts;
* session reset after an exception;
* a short randomized backoff between retries ([`option_chain_service.py`](../../backend/services/option_chain_service.py):289-301).

These are application behaviors, not proof of an allowed request rate.

### Authentication

**Broker authentication:** not used. The application constructs `NSE()` without credentials ([`option_chain_service.py`](../../backend/services/option_chain_service.py):246-250).

**NSE web-session state:** the published PNSEA session implementation uses Stealthkit, sets NSE headers, and fetches NSE cookies during session construction. This is session initialization, not an authenticated market-data entitlement. Whether NSE permits the resulting access for continuous research collection is **UNVERIFIED**.

### Reliability and limitations

The repository explicitly treats the direct feed as failure-prone: after failed attempts it resets the session and falls back to SQLite ([`option_chain_service.py`](../../backend/services/option_chain_service.py):289-301 and 476-490). If no database is available, the fallback chain can be seeded synthetically by `_seed_initial_snapshot` ([`option_chain_service.py`](../../backend/services/option_chain_service.py):91-143). Thus a successful application response is not by itself proof that every field came from PNSEA.

No uptime, completeness, historical retention, exchange timestamp guarantee, academic license, or publication permission was verified. PNSEA is an unofficial wrapper, and the upstream service behavior can change without notice.

## 8. Snapshot recorder authenticity and field modification

The recorder calls `get_full_chain`, not PNSEA directly ([`record_nifty_snapshots.py`](../../scripts/record_nifty_snapshots.py):73-90). Consequently, it may save:

1. PNSEA-derived current data;
2. a SQLite snapshot fallback; or
3. the synthetic seeded chain if the database is absent/empty.

It does not record a source discriminator proving which of these paths produced each row.

For a successful PNSEA path, the application performs these transformations before persistence:

* **Timestamp:** manufactures an application retrieval timestamp with `datetime.now().isoformat()`.
* **Expiry:** selects one expiry and stores the selected value, while `available_expiries` is not stored in `option_snapshots`.
* **Strike and side:** maps `strikePrice`, `CE`, and `PE` to `strike`, `CALL`, and `PUT`.
* **LTP, volume, and OI:** parses and stores the mapped values.
* **Bid and ask:** uses PNSEA values when present; otherwise uses `ltp * 0.995` and `ltp * 1.005` ([`option_chain_service.py`](../../backend/services/option_chain_service.py):329-345). Those fallback values are manufactured and are not exchange quotes.
* **IV:** reads the published IV in percent, converts to decimal, then attempts to recompute IV from LTP with fixed `r=0.065` and the selected time to expiry. A valid recomputation replaces the published IV; otherwise the published value is retained ([`option_chain_service.py`](../../backend/services/option_chain_service.py):347-362). The recorder stores the final `iv`, not both provenance values.
* **Greeks and derived values:** fair price, Greeks, mispricing, VRP, and M-Score are application calculations. The recorder stores Greeks but not fair price, source IV, or raw PNSEA rows.
* **Depth:** only the ATM-centered depth subset is returned and saved.

Therefore the recorder can save genuine values originating in a PNSEA response, but it does not save an immutable PNSEA response and can save modified or synthetic fields.

## 9. Suitability for continuous historical data collection

**Status: NOT SUITABLE as a standalone historical-data acquisition system.**

It is suitable only as a best-effort live snapshot collector if the following limitations are accepted:

* collection begins at runtime and cannot reconstruct prior observations;
* no exchange timestamp is retained;
* current expiry selection is not historical contract retrieval;
* expired-contract coverage is unverified;
* bid/ask may be manufactured;
* IV is often recomputed under application assumptions;
* only a depth-limited chain is persisted;
* fallback and synthetic rows are not source-labeled;
* no immutable raw response, checksum, request metadata, or provider version is stored;
* no numeric rate limit or uptime guarantee is established; and
* the local declared dependency is not installed in the inspected environment.

For research collection, PNSEA could be used as an explicitly labeled live-feed input during a controlled pilot, but it should not be the sole basis for a publication-quality historical option panel. A suitable acquisition system would need raw response retention, source/path flags, exchange timestamps or documented quote timestamps, complete contract coverage, expired-contract retention, quality checks, and a verified license.

## 10. Overall conclusion

PNSEA is integrated as an unofficial, current NSE option-chain wrapper through `NSE().options.option_chain(...)`. The repository uses it to obtain current NIFTY spot, expiry metadata, strike rows, CE/PE LTP, published IV, volume, OI, and expected bid/ask fields. The application then timestamps, filters, recalculates, and persists the data.

The integration does **not** establish historical quotes, historical option chains, expired-contract access, exchange timestamps, guaranteed bid/ask completeness, numeric rate limits, or publication rights. Those capabilities remain **UNVERIFIED** and require a version-specific runtime test, raw response inspection, provider terms, and an independent data-quality assessment.

# Data-source scope and proposal alignment

## Implemented for Milestone 2 v0.1

The pipeline downloads daily adjusted-close prices for 22 instruments (20 ETFs, SPY and AGG) from the Yahoo Finance chart endpoint. It writes individual raw CSVs, a SPY-calendar aligned snapshot, a retrieval manifest and SHA-256 fingerprints.

## Not implemented

This version does not connect to TradingView, download VIX, query SEC EDGAR, or implement company fundamentals, value/quality factors, K-means, transaction costs, slippage or position limits. The selected universe consists of ETFs, so company-level fundamentals are not inputs to this v0.1 strategy. Do not claim these deferred capabilities have been completed.

## Data limitations

Yahoo may revise historical adjusted closes. The present-day ETF universe creates selection/survivorship bias because the same funds were not all available throughout the historical sample. Missing prices are not backfilled before an ETF's inception. The live Yahoo download may fail or be rate-limited; if that happens, retry later rather than substituting synthetic values.

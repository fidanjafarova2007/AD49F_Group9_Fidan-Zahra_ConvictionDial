# Upload checklist for the group

- [x] Create a GitHub repository and upload the core project source, configuration, tests and workflow.
- [x] Verify GitHub recognizes README.md, config.json, src/, tests/ and .github/workflows/reproduce.yml.
- [ ] Under Actions, verify offline tests pass.
- [ ] Ensure the external Yahoo download/backtest step succeeds. On rate-limit failure, rerun later; never present synthetic fixtures as empirical results.
- [ ] Download the run's conviction-dial-milestone2-real-market-data artifact and inspect results/milestone2_report.md.
- [ ] Verify numeric results for all four portfolios, especially the chronological holdout; do not assume the strategy wins.
- [ ] Include generated reports/results in the repository itself if the instructor requires them committed rather than supplied as an Actions artifact.
- [ ] State that transaction costs and slippage are deliberately not modeled until Milestone 3.

The .venv, Python cache, and generated data/results are intentionally excluded from source control. The workflow regenerates real market data and report artifacts.

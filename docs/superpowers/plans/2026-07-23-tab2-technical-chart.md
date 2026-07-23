# Tab2 Technical Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Gradio Tab2 that loads a downloaded CSV by symbol or upload and renders candlestick with moving averages, BOLL candlestick, volume, MACD, and RSI panels.

**Architecture:** Keep UI thin, orchestrate analysis in a service, extend the CSV repository through a protocol, and isolate Plotly construction in an infrastructure adapter. Indicator calculations remain pure pandas functions for deterministic tests.

**Tech Stack:** Python 3.10+, pandas, Plotly, Gradio, pytest.

## Global Constraints

- Preserve the existing `src/ui`, `src/service`, `src/common`, `src/infra` layering.
- Uploaded CSV has priority over repository lookup.
- Required columns: `trade_date, open, high, low, close, volume`.
- Default indicators: MACD 12/26/9, BOLL 20/2, RSI 14.
- Default display window: 250 rows.
- A-share colors: rising red, falling green.

---

### Task 1: Indicator calculation service

**Files:**
- Create: `src/service/technical_indicator_service.py`
- Test: `tests/service/test_technical_indicator_service.py`

**Interfaces:**
- Produces: `TechnicalIndicatorService.calculate(data, macd_fast, macd_slow, macd_signal, boll_period, boll_std, rsi_period) -> pd.DataFrame`.

- [ ] Write failing tests for MACD, BOLL, RSI columns and invalid parameters.
- [ ] Run targeted tests and confirm import/behavior failures.
- [ ] Implement pure pandas calculations with no charting dependency.
- [ ] Run targeted tests and confirm pass.

### Task 2: CSV read and lookup infrastructure

**Files:**
- Modify: `src/service/ports.py`
- Modify: `src/infra/storage/csv_repository.py`
- Test: `tests/infra/test_csv_repository.py`

**Interfaces:**
- Produces: `CsvDataRepository.find_latest(symbol) -> Path` and `read(path) -> pd.DataFrame`.

- [ ] Write failing tests for latest-file selection, missing-file error, and UTF-8 CSV reading.
- [ ] Run targeted tests and confirm failures.
- [ ] Extend protocol and `LocalCsvRepository` implementation.
- [ ] Run targeted tests and confirm pass.

### Task 3: Technical analysis orchestration

**Files:**
- Modify: `src/common/constants.py`
- Modify: `src/common/exceptions.py`
- Modify: `src/common/models.py`
- Create: `src/service/technical_analysis_service.py`
- Test: `tests/service/test_technical_analysis_service.py`

**Interfaces:**
- Produces: `TechnicalAnalysisService.analyze(request) -> TechnicalAnalysisResult`.
- Consumes: CSV repository, indicator service, chart builder.

- [ ] Write failing tests for upload priority, symbol lookup, field validation, filtering and row limit.
- [ ] Run targeted tests and confirm failures.
- [ ] Add models/constants/exceptions and implement orchestration.
- [ ] Run targeted tests and confirm pass.

### Task 4: Plotly chart adapter

**Files:**
- Create: `src/infra/charting/__init__.py`
- Create: `src/infra/charting/plotly_chart_builder.py`
- Test: `tests/infra/test_plotly_chart_builder.py`

**Interfaces:**
- Produces: `PlotlyTechnicalChartBuilder.build(data, title) -> plotly.graph_objects.Figure`.

- [ ] Write failing tests for expected traces and five-panel layout.
- [ ] Run targeted tests and confirm failures.
- [ ] Implement candlestick, volume, BOLL, MACD, RSI and shared axes.
- [ ] Run targeted tests and confirm pass.

### Task 5: Tab2 UI and dependency injection

**Files:**
- Create: `src/ui/tabs/tab2_technical_chart.py`
- Modify: `src/ui/app_builder.py`
- Modify: `app.py`
- Test: `tests/ui/test_tab2_technical_chart.py`
- Modify: `tests/ui/test_tab1_data_fetch.py`

**Interfaces:**
- Produces: `build_technical_chart_tab(service)` and `create_technical_chart_handler(service)`.

- [ ] Write failing UI tests for Tab2 label, success and domain error rendering.
- [ ] Run targeted tests and confirm failures.
- [ ] Add UI components, event binding and dependency assembly.
- [ ] Run UI tests and confirm pass.

### Task 6: Dependencies, documentation and full verification

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] Add Plotly dependency and document Tab2 behavior and parameters.
- [ ] Run `pytest -q` and confirm all tests pass.
- [ ] Run `python -c "import app; print(type(app.demo).__name__)"` and confirm `Blocks`.
- [ ] Build a clean zip excluding caches and generated CSV files.

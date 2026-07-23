# Gradio Source-Layer Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the trading-strategy assistant into a `src/ui`, `src/service`, `src/common`, and `src/infra` architecture and expose the existing market-data download feature as `Tab1 数据获取`.

**Architecture:** `app.py` is the composition root. The UI depends only on `MarketDataService`; the service depends on gateway and repository protocols; efinance and local CSV persistence are infrastructure adapters. Common modules hold configuration, enums, models, exceptions, constants, and validation with no Gradio or efinance dependencies.

**Tech Stack:** Python 3.10+, Gradio, pandas, efinance, pytest, setuptools source layout.

## Global Constraints

- Keep the existing ETF/stock daily-data behavior, CSV schema, volume conversion, date validation, retry handling, and CSV download.
- Use top-level packages under `src/`: `ui`, `service`, `common`, and `infra`.
- Name the first Gradio tab `Tab1 数据获取`.
- The service layer must not import Gradio or efinance.
- The UI layer must not call efinance or write CSV files directly.
- Tests must not access the network.

---

### Task 1: Establish source-layout package and common domain modules

**Files:**
- Create: `pyproject.toml`
- Create: `src/common/__init__.py`
- Create: `src/common/config.py`
- Create: `src/common/constants.py`
- Create: `src/common/exceptions.py`
- Create: `src/common/models.py`
- Create: `src/common/validators.py`
- Create: `tests/common/test_validators.py`

**Interfaces:**
- Produces: `Settings.from_env()`, `AssetType`, `AdjustType`, `DataFetchCommand`, `MarketDataFrame`, `FetchResult`, `normalize_symbol()`, `resolve_asset_type()`, `resolve_adjust()`, `parse_date()`, `validate_date_range()`.

- [ ] Write validator and model tests that import from `common` and verify code normalization, exchange/asset inference, adjustment mapping, date parsing, and invalid inputs.
- [ ] Run `pytest tests/common/test_validators.py -q` and confirm import failure because the new package does not exist.
- [ ] Implement the common modules and packaging metadata.
- [ ] Run `pytest tests/common/test_validators.py -q` and confirm all common tests pass.

### Task 2: Introduce service ports and orchestration

**Files:**
- Create: `src/service/__init__.py`
- Create: `src/service/ports.py`
- Create: `src/service/market_data_service.py`
- Create: `tests/service/test_market_data_service.py`

**Interfaces:**
- Consumes: common request/result models and validation helpers.
- Produces: `MarketDataGateway.fetch_daily(command) -> MarketDataFrame`, `CsvRepository.save(frame, command) -> Path`, and `MarketDataService.fetch_and_save(command) -> FetchResult`.

- [ ] Write tests with fake gateway and fake repository for orchestration, date-range filtering, empty-result rejection, and metadata propagation.
- [ ] Run `pytest tests/service/test_market_data_service.py -q` and confirm failure because service modules are missing.
- [ ] Implement protocols and the minimal service orchestration.
- [ ] Run `pytest tests/service/test_market_data_service.py -q` and confirm all service tests pass.

### Task 3: Implement efinance and CSV infrastructure adapters

**Files:**
- Create: `src/infra/__init__.py`
- Create: `src/infra/market_data/__init__.py`
- Create: `src/infra/market_data/efinance_gateway.py`
- Create: `src/infra/storage/__init__.py`
- Create: `src/infra/storage/csv_repository.py`
- Create: `tests/infra/test_efinance_gateway.py`
- Create: `tests/infra/test_csv_repository.py`

**Interfaces:**
- Consumes: `DataFetchCommand`, output-column constants, common exceptions and models.
- Produces: `EfinanceMarketDataGateway` and `LocalCsvRepository` implementations of service ports.

- [ ] Write adapter tests using injected fake fetch functions and temporary directories; verify efinance column mapping, legacy aliases, OHLC quality checks, volume conversion, percentage normalization, warning generation, retry behavior, filename construction, UTF-8 BOM output, and stale-file cleanup.
- [ ] Run the two infra test files and confirm failure because adapters are missing.
- [ ] Implement efinance retrieval/normalization and local CSV persistence.
- [ ] Run the two infra test files and confirm all adapter tests pass.

### Task 4: Build Tab1 UI and composition root

**Files:**
- Create: `src/ui/__init__.py`
- Create: `src/ui/app_builder.py`
- Create: `src/ui/tabs/__init__.py`
- Create: `src/ui/tabs/tab1_data_fetch.py`
- Replace: `app.py`
- Create: `tests/ui/test_tab1_data_fetch.py`
- Delete: `data_service.py`
- Delete: `tests/test_data_service.py`

**Interfaces:**
- Consumes: `MarketDataService`, `Settings`, output columns, and common exceptions.
- Produces: `build_app(service, settings) -> gr.Blocks`, `build_data_fetch_tab(service, settings)`, and a callback returning preview/status/download path.

- [ ] Write UI presenter/callback tests using a fake service and verify successful output, domain-error output, unexpected-error output, 200-row preview limit, and `Tab1 数据获取` presence in the app configuration.
- [ ] Run `pytest tests/ui/test_tab1_data_fetch.py -q` and confirm failure because UI modules are missing.
- [ ] Implement the tab module, app builder, and dependency composition in `app.py`; remove obsolete top-level implementation files.
- [ ] Run `pytest tests/ui/test_tab1_data_fetch.py -q` and confirm all UI tests pass.

### Task 5: Update runtime files, documentation, and package archive

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`
- Replace: `README.md`

**Interfaces:**
- Produces: documented local/Docker startup commands and a distributable ZIP containing the refactored project.

- [ ] Update install and launch commands for editable source-layout installation and Docker package installation.
- [ ] Document the directory tree, dependency direction, Tab1 behavior, CSV schema, tests, and data caveats.
- [ ] Run `python -m compileall app.py src`.
- [ ] Run `pytest -q` and confirm the complete suite passes.
- [ ] Import `app` and verify a Gradio Blocks object is created without launching the server.
- [ ] Create `/mnt/data/trading_strategy_assistant_src_refactored.zip` excluding caches and generated CSV files.

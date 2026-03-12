# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP (Model Context Protocol) server providing read-only Instagram analytics. Built with FastMCP, instaloader, and Pydantic. Offers 10 tools for engagement metrics, sentiment analysis, hashtag tracking, and user profile analytics.

## Commands

```bash
# Install all dependencies (including dev)
uv sync --all-extras

# Run all tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/test_cache.py -v

# Run a single test class or method
uv run pytest tests/test_cache.py::TestCache::test_set_and_get_roundtrip

# Type checking (strict mode)
uv run pyright src/

# Linting
uv run ruff check src/

# Run server locally (HTTP mode, requires .env)
uv run python -m mcp_insta_analytics --http

# Docker build & run
docker compose up -d --build
```

## Architecture

### Dependency Flow

```
__main__.py → server.py (FastMCP lifespan) → tools/*
                  ↓
    config.py (Settings from env vars, prefix: INSTA_ANALYTICS_)
                  ↓
    ┌─────────────┼──────────────┐
    fetcher/      cache          rate_limiter
    (instaloader)  (sqlite or     (sqlite or
                   dynamodb)      dynamodb)
```

Tools receive shared dependencies (fetcher, cache, rate_limiter, config) via `ctx.lifespan_context`, extracted with `extract_deps(ctx)` from `tools/__init__.py`.

### Fetcher Layer (Strategy Pattern)

`fetcher/base.py` defines `AbstractFetcher` with 5 async methods. One implementation:
- **InstaLoaderFetcher** (`instaloader_fetcher.py`): Uses instaloader library with optional browser session cookie auth. Runs blocking calls in thread executor with timeout. Reads `_node` (raw JSON) to avoid triggering extra GraphQL requests.

`fetcher/factory.py` selects the backend via `config.fetcher_backend`.

### Dual Storage Backend

Cache and rate limiter each have SQLite and DynamoDB implementations sharing the same abstract interface. Selected via `config.storage_backend` (`"sqlite"` or `"dynamodb"`).

### Tool Pattern

Every tool in `tools/` follows: check cache → acquire rate limit → fetch data → run analysis → cache result → return Pydantic response model. Tools are registered in `server.py` via `@mcp.tool()`.

### Error Hierarchy

All errors in `errors.py` extend `InstaAnalyticsError` and carry a `recovery` string with user-facing instructions. Key subtypes: `AuthenticationError`, `FetcherError`, `RateLimitError`, `BudgetExhaustedError`.

## Testing Conventions

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (no need for `@pytest.mark.asyncio` on most tests).
- Fixtures in `tests/conftest.py` provide `sample_post`, `sample_user`, `mock_fetcher`, `mock_context`, `test_cache`, `test_rate_limiter`.
- JSON fixture data lives in `tests/fixtures/`.
- Tool tests use `mock_context` which wires up a mock fetcher + real SQLite cache/rate_limiter backed by `tmp_path`.
- DynamoDB tests use `moto` for AWS mocking.

## Type Checking

Pyright is configured in **strict** mode. instaloader has no type stubs, so `instaloader_fetcher.py` uses `Any` types for instaloader objects.

## Deployment

- **Docker**: `compose.yaml` + `Dockerfile` (uv-based). Storage: SQLite. Transport: streamable-http on port 8001.
- **AWS Lambda**: `template.yaml` (CloudFormation). Storage: DynamoDB. Entry: `lambda_handler.py` (Mangum bridge). Deploy: `./deploy.sh`.

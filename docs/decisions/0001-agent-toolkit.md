# 0001 — How Kweli uses the PayPal Agent Toolkit

**Status:** accepted · **Date:** 3 Nov 2026

## Context
Kweli's agent needs PayPal tools (invoices, transactions, disputes) in LangChain. The official `paypal-agent-toolkit` (1.11.0) provides tool names, descriptions, argument schemas and request builders that PayPal maintains. A security review of the package found:

1. **Dependency tree.** It hard-pins `langchain==0.3.23`, `crewai-tools==0.13.2` and `openai-agents==0.0.2`. Installing it normally pulls in packages with known vulnerabilities, including `pypdf` 5.9.0 (100+ advisories), `langchain-core` 0.3, `chromadb` and `mem0ai`.
2. **No HTTP timeouts.** Its client calls `requests` without a timeout, so a hung connection blocks the agent forever.
3. **A new OAuth token on every call**, and no retries or idempotency keys.
4. **Request headers logged at debug level**, including the bearer token.
5. Telemetry is local only: a User-Agent string and one debug log line. Nothing is sent anywhere else.

The parts Kweli uses (`paypal_agent_toolkit.shared`) only import `pydantic`, `httpx` and `requests`.

## Decision
- Install the toolkit with `pip install --no-deps paypal-agent-toolkit==1.11.0`, next to current `langchain-core` and `langchain-anthropic`.
- Don't use the toolkit's LangChain wrapper or HTTP client. `agent/paypal_tools.py` builds `StructuredTool`s from the toolkit's specs and runs its handlers through an adapter around **Kweli's own `PayPalClient`**, which has timeouts, retries with backoff, a cached token, `PayPal-Request-Id` idempotency keys and secret-redacted logs.
- The agent gets only the methods it needs (an allowlist). Money-moving or submitting methods (`send_invoice`, dispute responses and so on) are never given to the model directly. They go through the approval gate.
- CI's `agent` job installs this exact setup and runs `pip-audit` on the resulting environment.

## Consequences
- PayPal's tool schemas and request shapes stay in sync with each toolkit upgrade.
- Upgrading the toolkit needs a manual check that `shared/` still imports only light dependencies.
- If PayPal fixes the dependency pins, we can switch back to a normal install.

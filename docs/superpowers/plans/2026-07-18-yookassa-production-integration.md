# YooKassa production integration implementation plan

> **For Codex:** execute this plan task by task with strict red-green-refactor. Never use real YooKassa credentials or open the merchant dashboard.

**Goal:** Replace the placeholder payment adapter with a production-ready YooKassa API v3 integration for the single `full_report_v1` product, including fiscal receipts, verified webhooks, reconciliation, refunds, frontend redirect recovery, and operational documentation.

**Architecture:** FastAPI owns payment orchestration and persists stable provider idempotency keys before external calls. An async `httpx` adapter talks to YooKassa. Webhooks are authenticated by source-network validation and server-to-server object lookup. The browser receives only internal purchase state and a provider redirect URL; entitlement changes remain transactional server decisions.

**Stack:** Python 3.11, FastAPI 0.128, Pydantic 2, httpx, PostgreSQL 17, React 19, TypeScript, Vitest, Playwright.

**Design contract:** `docs/superpowers/specs/2026-07-18-yookassa-production-integration-design.md`

---

## Task 1: Production payment configuration

**Files:**

- Create: `backend/src/vedicway_backend/payment_config.py`
- Create: `backend/tests/test_payment_config.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env.example`

1. Write failing tests for disabled development configuration, explicit test provider, complete YooKassa configuration, missing production secrets, invalid public HTTP URL, invalid VAT code and forbidden production API base override.
2. Run `python -m pytest backend/tests/test_payment_config.py -q` and verify the tests fail because the settings object does not exist.
3. Implement immutable typed settings, server catalog `full_report_v1 = 99000 RUB`, official API origin, receipt item defaults and strict production validation.
4. Move `httpx` from test-only dependencies into production dependencies.
5. Re-run the focused tests and commit.

## Task 2: YooKassa API adapter

**Files:**

- Modify: `backend/src/vedicway_backend/payments.py`
- Create: `backend/src/vedicway_backend/yookassa.py`
- Create: `backend/tests/test_yookassa_provider.py`

1. Write failing `httpx.MockTransport` tests for redirect payment creation, exact receipt payload, Basic Auth, stable `Idempotence-Key`, payment lookup, refund creation, refund lookup, status normalization and redacted errors.
2. Add tests proving that `429`, transport errors and `5xx` preserve the same key, while permanent `4xx` responses do not retry.
3. Refactor `PaymentProvider` to async methods and extend `PaymentIntent` with amount, currency, metadata, paid/captured flags and safe failure code.
4. Implement `YooKassaPaymentProvider` with bounded timeout, bounded retry, official base URL and no secret-bearing logs.
5. Run `python -m pytest backend/tests/test_yookassa_provider.py -q` and commit.

## Task 3: Durable purchase, event, entitlement and refund state

**Files:**

- Modify: `backend/src/vedicway_backend/store.py`
- Create: `backend/migrations/002_yookassa_production.sql`
- Create: `backend/tests/test_payment_store.py`

1. Write failing store tests for provider key persistence before API use, duplicate client key, one active purchase per chart/product, provider response persistence, payment event dedupe, success transition, cancellation, partial refund, full refund and entitlement revocation.
2. Extend the PostgreSQL runtime migrations with refunds and audit tables.
3. Add the PostgreSQL migration with matching constraints and indexes.
4. Implement transactional transition methods that compare expected amount, currency and metadata before entitlement creation.
5. Run `python -m pytest backend/tests/test_payment_store.py -q` and commit.

## Task 4: Purchase API and idempotent provider orchestration

**Files:**

- Modify: `backend/src/vedicway_backend/schemas.py`
- Modify: `backend/src/vedicway_backend/main.py`
- Modify: `backend/tests/test_api_flow.py`
- Create: `backend/tests/test_payment_api.py`

1. Write failing API tests for required email, accepted offer/version, server-side amount, duplicate request key, active pending purchase reuse, already-entitled rejection and ambiguous provider recovery.
2. Inject one provider instance through FastAPI lifespan and close its HTTP client on shutdown.
3. Persist purchase and provider key before calling YooKassa; save confirmation URL and redacted response afterward.
4. Return a typed purchase DTO with public status, checkout URL, price and retryability, never provider metadata or email.
5. Preserve the local test provider under an explicit non-production switch.
6. Run focused API tests and commit.

## Task 5: Verified YooKassa webhook and reconciliation

**Files:**

- Create: `backend/src/vedicway_backend/payment_security.py`
- Modify: `backend/src/vedicway_backend/main.py`
- Modify: `backend/src/vedicway_backend/store.py`
- Create: `backend/tests/test_yookassa_webhook.py`

1. Write failing tests for all official YooKassa IPv4/IPv6 ranges, spoofed `X-Forwarded-For`, trusted proxy extraction, invalid JSON, unsupported event, duplicate event and temporary provider failure.
2. Write failing success tests that re-fetch the payment and require `succeeded`, paid/captured, exact amount/currency and matching metadata.
3. Replace the placeholder HMAC webhook with the YooKassa notification contract and `200 OK` duplicate handling.
4. Add reconciliation for pending purchases to `GET /api/v1/purchases/:purchaseId`, with a persisted cooldown to avoid provider polling storms.
5. Record mismatch incidents without entitlement and expose only safe user-facing status.
6. Run webhook and API tests and commit.

## Task 6: Refunds and protected operations API

**Files:**

- Modify: `backend/src/vedicway_backend/schemas.py`
- Modify: `backend/src/vedicway_backend/main.py`
- Modify: `backend/src/vedicway_backend/store.py`
- Create: `backend/tests/test_payment_operations.py`

1. Write failing tests for operations token comparison, operations CIDR restriction, missing reason, amount bounds, duplicate refund key, partial refund and full entitlement revocation.
2. Implement internal reconcile and refund endpoints outside browser CORS.
3. Send refund receipt data according to the configured YooKassa receipt mode and VAT code.
4. Persist audited actions with token fingerprint, trace ID, reason, amount and provider result.
5. Reconcile `refund.succeeded` notifications through a provider lookup.
6. Run focused tests and commit.

## Task 7: Frontend payment client and return-state controller

**Files:**

- Modify: `src/lib/chart-api.ts`
- Create: `src/lib/payment-return.ts`
- Create: `src/lib/payment-return.test.ts`

1. Write failing tests for typed purchase creation, offer payload, purchase polling backoff, success, cancellation, timeout and sessionStorage cleanup.
2. Extend the API error type with stable backend codes and safe details.
3. Add `getPurchase` and a cancellable 60-second poller with bounded increasing delays.
4. Store only purchase ID, chart ID and selected domain; reject malformed or cross-chart state.
5. Run `npm test -- --run src/lib/payment-return.test.ts` and commit.

## Task 8: Accessible YooKassa paywall and redirect recovery

**Files:**

- Create: `src/components/PaymentPaywall.tsx`
- Create: `src/components/PaymentPaywall.test.tsx`
- Modify: `src/components/ChartWorkspace.tsx`
- Modify: `src/chart-workspace.css`
- Modify: `src/lib/analytics.ts`

1. Write failing component tests for required email, offer consent, offer/privacy links, pending lock, provider error, canceled retry and keyboard/focus behavior.
2. Extract the paywall into a dedicated component without changing the existing visual hierarchy.
3. Redirect to YooKassa only after a typed purchase response; never render or collect card fields.
4. Detect the internal return marker, show `Проверяем платёж`, poll the server and reopen the selected domain after entitlement.
5. Add privacy-safe analytics for checkout start, server confirmation, cancellation and timeout.
6. Run all frontend unit tests and commit.

## Task 9: Browser-level redirect flow without YooKassa auth

**Files:**

- Modify: `backend/src/vedicway_backend/payments.py`
- Modify: `backend/src/vedicway_backend/main.py`
- Modify: `tests/e2e/free-to-full-report.spec.ts`
- Create: `tests/e2e/payment-recovery.spec.ts`
- Modify: `tests/e2e/helpers.ts`

1. Change the local test provider to expose a browser checkout simulator that redirects through the same return path as production.
2. Write a failing Playwright scenario for email/offer, redirect, server confirmation, selected-domain recovery and PDF access.
3. Add a delayed-confirmation scenario proving that query parameters do not unlock content and reload resumes polling.
4. Run the two payment Playwright specs against a fresh local BFF and commit.

## Task 10: Deployment, activation and incident documentation

**Files:**

- Modify: `backend/.env.example`
- Modify: `backend/README.md`
- Modify: `backend/docs/RUNBOOKS.md`
- Create: `backend/docs/YOOKASSA_ACTIVATION.md`
- Modify: `docs/specs/VEDICWAY-BACKEND-CODEX-PYJHORA-SPEC-RU.md`
- Modify: `docs/specs/VEDICWAY-FRONTEND-UX-UI-SPEC-RU.md`

1. Document every variable without secret examples and provide the exact public webhook/return URLs.
2. Add startup, health, key rotation, webhook delay, mismatch, refund and VAT troubleshooting procedures.
3. Add an activation checklist that stops before dashboard login: HTTPS, secrets injection, VAT confirmation, webhook registration, test shop, ten sequential test payments, refund and receipt verification.
4. Update the frontend/backend implementation journals only after matching tests pass.
5. Run secret-pattern scans and commit.

## Task 11: Full verification and handoff

**Files:**

- Modify only files required by observed failures.

1. Run backend tests with the configured Python 3.11 runtime.
2. Run `npm test -- --run` and `npm run build`.
3. Run the complete Playwright suite with one worker against a fresh backend and frontend.
4. Run `git diff --check`, inspect `git status`, scan for YooKassa secret patterns and confirm no generated artifacts are staged.
5. Review every acceptance item from the design contract and record evidence in `backend/docs/YOOKASSA_ACTIVATION.md`.
6. Commit the verified result on `codex/yookassa-production`. Do not merge, rebase or modify `main` until the owner gives a separate command.

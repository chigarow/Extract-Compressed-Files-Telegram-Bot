# Test Recovery Strategy

## Objectives
- Restore full `pytest tests` pass by fixing failing suites and async configuration.
- Verify WebDAV + queue-manager changes remain production-safe.

## Action Plan
1. **Async Fixture Audit**
   - Ensure pytest-asyncio (or anyio) is configured for every async test module.
   - Update fixtures/tests that currently raise "async def functions are not natively supported".

2. **Targeted Suite Triage**
   - Prioritize failing suites in order: compression cleanup/timeout, error handling, flood-wait handling, queue behavior, Telegram ops, Torbox integration.
   - For each, identify whether failure is code regression vs. test drift.

3. **Fix + Retest Iteratively**
   - Implement code/test fixes per suite, rerun targeted pytest module, then roll into broader subset.
   - Maintain changelog entries for each fix.

4. **Full Regression Run**
   - Once all targeted suites are green, rerun `source venv/bin/activate && pytest tests`.
   - Address any straggling failures, then document readiness.

## Notes
- New queue_manager hooks (`_skip_upload_idle_wait`, `_disable_upload_worker_start`) are test-only toggles, defaulting off; safe to keep for production.

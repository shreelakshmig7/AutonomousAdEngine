"""
tests/
------
Varsity Ad Engine — Nerdy / Gauntlet — Test suite
--------------------------------------------------
Contains all 12 required test cases. All API calls are mocked
via pytest-mock — the full suite runs fully offline.

Test files:
  test_evaluator.py     — 4 tests: gold, poor, threshold, weakest dimension
  test_generator.py     — 5 tests: schema, CSV, seed, fallback, image URL
  test_iteration_cap.py — 2 tests: cap at 3 cycles, unresolvable status
  test_integration.py   — 1 test:  full brief → publishable ad end-to-end

Run all tests:
  pytest tests/ -v --tb=short 2>&1 | tee tests/results/run_YYYYMMDD.txt
"""

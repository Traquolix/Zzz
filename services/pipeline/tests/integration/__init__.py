"""Integration tests for the DAS pipeline.

These tests require Kafka to be running and test real message flow.
All test resources are cleaned up automatically after each test.

Run with:
    pytest tests/integration/ -v

Or via the test script:
    ./scripts/test.sh --integration
"""

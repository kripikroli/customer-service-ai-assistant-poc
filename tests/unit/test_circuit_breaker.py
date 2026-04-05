"""Unit tests for circuit breaker state transitions."""

import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_table():
    with patch("lambdas.circuit_breaker.handler.table") as mock:
        mock.get_item.return_value = {}
        yield mock


def test_get_state_returns_closed_for_new_model(mock_table):
    mock_table.get_item.return_value = {}
    from lambdas.circuit_breaker.handler import get_state

    state = get_state("test-model")
    assert state["state"] == "CLOSED"
    assert state["failure_count"] == 0


def test_get_state_returns_existing_state(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"model_id": "test-model", "state": "OPEN", "failure_count": 5}
    }
    from lambdas.circuit_breaker.handler import get_state

    state = get_state("test-model")
    assert state["state"] == "OPEN"
    assert state["failure_count"] == 5


def test_record_success_resets_state(mock_table):
    from lambdas.circuit_breaker.handler import record_success

    record_success("test-model")
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["state"] == "CLOSED"
    assert item["failure_count"] == 0


def test_record_failure_increments_count(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"model_id": "test-model", "state": "CLOSED", "failure_count": 2}
    }
    from lambdas.circuit_breaker.handler import record_failure

    new_state = record_failure("test-model", threshold=5)
    assert new_state == "CLOSED"
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["failure_count"] == 3


def test_record_failure_trips_circuit_at_threshold(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"model_id": "test-model", "state": "CLOSED", "failure_count": 4}
    }
    from lambdas.circuit_breaker.handler import record_failure

    new_state = record_failure("test-model", threshold=5)
    assert new_state == "OPEN"


def test_should_allow_request_closed_circuit(mock_table):
    mock_table.get_item.return_value = {
        "Item": {"model_id": "test-model", "state": "CLOSED", "failure_count": 0}
    }
    from lambdas.circuit_breaker.handler import should_allow_request

    assert should_allow_request("test-model") is True


def test_should_block_request_open_circuit(mock_table):
    mock_table.get_item.return_value = {
        "Item": {
            "model_id": "test-model",
            "state": "OPEN",
            "failure_count": 5,
            "last_failure_time": int(time.time()),
        }
    }
    from lambdas.circuit_breaker.handler import should_allow_request

    assert should_allow_request("test-model", recovery_timeout=60) is False


def test_should_allow_request_after_recovery_timeout(mock_table):
    mock_table.get_item.return_value = {
        "Item": {
            "model_id": "test-model",
            "state": "OPEN",
            "failure_count": 5,
            "last_failure_time": int(time.time()) - 120,
        }
    }
    from lambdas.circuit_breaker.handler import should_allow_request

    assert should_allow_request("test-model", recovery_timeout=60) is True

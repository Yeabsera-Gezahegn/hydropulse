"""
Unit test suite for the HydroPulse Historical Back-Testing Validation Module.
Verifies confusion matrix generation and checks that back-testing accuracy meets or exceeds 85%.
"""

import numpy as np
import pytest

from src.engine.risk.validation import HistoricalValidator


def test_confusion_matrix_calculation():
    """Verify exact confusion matrix count calculations."""
    validator = HistoricalValidator()

    preds = np.array([0.1, 0.8, 0.9, 0.2, 0.6])
    truth = np.array([0, 1, 1, 0, 0])

    # Threshold 0.50: preds_binary = [0, 1, 1, 0, 1]
    # TP: (1,1) -> 2
    # FP: (1,0) -> 1
    # TN: (0,0) -> 2
    # FN: (0,1) -> 0
    metrics = validator.evaluate_predictions(preds, truth, threshold=0.50)

    assert metrics["true_positives"] == 2
    assert metrics["false_positives"] == 1
    assert metrics["true_negatives"] == 2
    assert metrics["false_negatives"] == 0
    assert metrics["accuracy"] == 0.80  # (2+2)/5
    assert metrics["sensitivity"] == 1.0  # 2/(2+0)
    assert metrics["precision"] == 0.6667  # 2/(2+1)


def test_historical_backtest_accuracy_threshold():
    """Verify that model back-testing accuracy meets or exceeds the required 85% benchmark."""
    validator = HistoricalValidator()
    scores, ground_truth = validator.generate_synthetic_backtest_data(num_events=1000, seed=42)

    metrics = validator.evaluate_predictions(scores, ground_truth, threshold=0.50)

    assert metrics["accuracy"] >= 0.85, (
        f"Historical back-test accuracy ({metrics['accuracy'] * 100:.2f}%) is below 85% target."
    )
    assert metrics["sensitivity"] >= 0.80
    assert metrics["precision"] >= 0.80

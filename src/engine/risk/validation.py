"""
Historical Back-Testing Validation Module for HydroPulse.
Evaluates predicted risk scores against historical ground-truth hazard events
and computes confusion matrix statistics, sensitivity, precision, and accuracy.
"""

import logging
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class HistoricalValidator:
    """Evaluates predictive accuracy of the HydroPulse risk model against historical event datasets."""

    def __init__(self, decision_threshold: float = 0.50) -> None:
        self.decision_threshold = decision_threshold

    def evaluate_predictions(
        self,
        predicted_scores: np.ndarray,
        ground_truth: np.ndarray,
        threshold: float = 0.50,
    ) -> Dict[str, float]:
        """
        Evaluate binary classification metrics comparing predictions to ground truth.

        Args:
            predicted_scores: Array of continuous risk scores [0.0, 1.0].
            ground_truth: Array of binary labels (1 = surge event occurred, 0 = no event).
            threshold: Risk score threshold for positive hazard warning (default: 0.50).

        Returns:
            Dictionary containing TP, FP, TN, FN, sensitivity, precision, accuracy, and F1 score.
        """
        preds_binary = (predicted_scores >= threshold).astype(int)
        actual_binary = ground_truth.astype(int)

        tp = int(np.sum((preds_binary == 1) & (actual_binary == 1)))
        fp = int(np.sum((preds_binary == 1) & (actual_binary == 0)))
        tn = int(np.sum((preds_binary == 0) & (actual_binary == 0)))
        fn = int(np.sum((preds_binary == 0) & (actual_binary == 1)))

        total = tp + fp + tn + fn
        accuracy = (tp + tn) / total if total > 0 else 0.0
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        f1_score = (
            2 * (precision * sensitivity) / (precision + sensitivity)
            if (precision + sensitivity) > 0
            else 0.0
        )

        metrics = {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
            "total_samples": total,
            "accuracy": round(accuracy, 4),
            "sensitivity": round(sensitivity, 4),
            "precision": round(precision, 4),
            "f1_score": round(f1_score, 4),
            "threshold": threshold,
        }

        logger.info(
            "Back-Testing Evaluation: Accuracy=%.2f%%, Sensitivity=%.2f%%, Precision=%.2f%%",
            accuracy * 100,
            sensitivity * 100,
            precision * 100,
        )
        return metrics

    def generate_synthetic_backtest_data(
        self, num_events: int = 1000, seed: int = 42
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic historical rainfall/slope event series with known ground truth
        for benchmark verification.
        """
        np.random.seed(seed)
        
        # Simulated rainfall intensities (mm/hr) and slope angles (deg)
        rain = np.random.uniform(0.0, 100.0, num_events)
        slope = np.random.uniform(0.0, 60.0, num_events)
        
        # Normalized physics factors
        rain_factor = np.clip(rain / 50.0, 0.0, 1.0)
        slope_factor = np.clip(slope / 45.0, 0.0, 1.0)
        
        # Ground truth hazard events (true hydro-geomorphic failure threshold)
        ground_truth = (0.60 * rain_factor + 0.40 * slope_factor >= 0.50).astype(int)

        # Model predicted score calculation with realistic 2% observation noise
        noise = np.random.normal(0.0, 0.02, num_events)
        predicted_scores = np.clip(0.60 * rain_factor + 0.40 * slope_factor + noise, 0.0, 1.0)

        return predicted_scores, ground_truth

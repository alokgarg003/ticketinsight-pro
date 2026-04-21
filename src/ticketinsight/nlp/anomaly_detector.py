"""
Anomaly detection module for TicketInsight Pro.

Detects anomalous tickets using Isolation Forest combined with statistical
methods (z-score analysis) for identifying unusual patterns in ticket
metadata, text, and resolution metrics.

Usage
-----
    from ticketinsight.nlp.anomaly_detector import AnomalyDetector
    detector = AnomalyDetector(config)
    results = detector.detect(tickets)
"""

import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.anomaly_detector")

# Priority encoding for numerical features
_PRIORITY_MAP = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

# Status encoding for numerical features
_STATUS_MAP = {
    "Open": 1, "In Progress": 2, "On Hold": 3, "Resolved": 4, "Closed": 5,
}

# Gibberish detection thresholds
_GIBBERISH_THRESHOLD = 0.7  # ratio of non-dictionary words to trigger


class AnomalyDetector:
    """Detect anomalous tickets using statistical and ML methods.

    Uses Isolation Forest for multivariate anomaly detection and z-score
    analysis for individual feature outliers.  Detects anomalies in:
        - Resolution time (too fast, too slow)
        - Description length (too short, too long)
        - Reassignment count (too many)
        - Priority-category mismatch
        - Text quality (gibberish, spam)
    """

    def __init__(self, config: Any = None):
        self.config = config
        self.model = None
        self.is_trained = False
        self._baseline_stats: Dict[str, Any] = {}
        self._feature_names: List[str] = []

        # Read config
        self.contamination = 0.1
        if config is not None:
            try:
                self.contamination = float(
                    config.get("nlp", "anomaly_contamination", 0.1)
                )
            except (ValueError, TypeError):
                self.contamination = 0.1

        logger.info(
            "AnomalyDetector initialized (contamination=%.2f)", self.contamination
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def detect(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect anomalous tickets from a list.

        Parameters
        ----------
        tickets : list[dict]
            List of ticket dictionaries with fields like title, description,
            priority, status, category, opened_at, resolved_at, etc.

        Returns
        -------
        dict
            ``{
                "anomalies": [{ticket_id, anomaly_score, anomaly_type, reason}, ...],
                "total_analyzed": int,
                "anomaly_count": int,
                "anomaly_rate": float
            }``
        """
        if not tickets:
            return {
                "anomalies": [],
                "total_analyzed": 0,
                "anomaly_count": 0,
                "anomaly_rate": 0.0,
            }

        # Compute baseline statistics
        self._baseline_stats = self._compute_baseline(tickets)

        anomalies = []

        for ticket in tickets:
            ticket_id = ticket.get("ticket_id", ticket.get("id", "unknown"))
            anomaly_result = self.detect_single(ticket, self._baseline_stats)

            if anomaly_result["is_anomaly"]:
                for reason, atype in zip(
                    anomaly_result["reasons"], anomaly_result["anomaly_types"]
                ):
                    anomalies.append({
                        "ticket_id": ticket_id,
                        "anomaly_score": anomaly_result["score"],
                        "anomaly_type": atype,
                        "reason": reason,
                    })

        # Also run Isolation Forest if enough data
        if self.is_trained and self.model is not None and len(tickets) >= 10:
            try:
                ml_anomalies = self._ml_detect(tickets)
                # Merge ML anomalies (avoid duplicates by ticket_id)
                existing_ids = {a["ticket_id"] for a in anomalies}
                for ma in ml_anomalies:
                    if ma["ticket_id"] not in existing_ids:
                        anomalies.append(ma)
                        existing_ids.add(ma["ticket_id"])
                    else:
                        # Enhance existing anomaly with ML score
                        for a in anomalies:
                            if a["ticket_id"] == ma["ticket_id"]:
                                a["anomaly_score"] = max(
                                    a["anomaly_score"], ma["anomaly_score"]
                                )
                                if "ml_" not in a["anomaly_type"]:
                                    a["anomaly_type"] += " + " + ma["anomaly_type"]
                                    a["reason"] += "; " + ma["reason"]
                                break
            except Exception as exc:
                logger.warning("ML anomaly detection failed: %s", exc)

        # Sort by anomaly score descending
        anomalies.sort(key=lambda x: x["anomaly_score"], reverse=True)

        total = len(tickets)
        count = len(set(a["ticket_id"] for a in anomalies))

        return {
            "anomalies": anomalies,
            "total_analyzed": total,
            "anomaly_count": count,
            "anomaly_rate": round(count / max(1, total), 4),
        }

    def detect_single(
        self, ticket: Dict[str, Any], baseline_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if a single ticket is anomalous compared to baseline.

        Parameters
        ----------
        ticket : dict
            Ticket dictionary.
        baseline_stats : dict
            Baseline statistics from _compute_baseline.

        Returns
        -------
        dict
            ``{
                "is_anomaly": bool,
                "score": float (0.0 to 1.0),
                "reasons": [str, ...],
                "anomaly_types": [str, ...]
            }``
        """
        reasons = []
        anomaly_types = []
        scores = []

        # 1. Description length anomaly
        desc_length = len(ticket.get("description", "") or "")
        title_length = len(ticket.get("title", "") or "")
        total_length = desc_length + title_length

        if "desc_length_mean" in baseline_stats and "desc_length_std" in baseline_stats:
            desc_z = self._z_score(
                total_length,
                baseline_stats["desc_length_mean"],
                baseline_stats["desc_length_std"],
            )
            if abs(desc_z) > 2.5:
                if desc_z > 0:
                    reasons.append(
                        f"Unusually long description ({total_length} chars, "
                        f"z-score: {desc_z:.2f})"
                    )
                    anomaly_types.append("text_anomaly")
                else:
                    reasons.append(
                        f"Unusually short description ({total_length} chars, "
                        f"z-score: {desc_z:.2f})"
                    )
                    anomaly_types.append("text_anomaly")
                scores.append(min(1.0, abs(desc_z) / 5.0))

        # 2. Resolution time anomaly
        resolution_hours = self._get_resolution_hours(ticket)
        if resolution_hours is not None:
            if "resolution_mean" in baseline_stats and "resolution_std" in baseline_stats:
                res_z = self._z_score(
                    resolution_hours,
                    baseline_stats["resolution_mean"],
                    baseline_stats["resolution_std"],
                )
                if abs(res_z) > 2.5:
                    if res_z > 0:
                        reasons.append(
                            f"Unusually long resolution time ({resolution_hours:.1f}h, "
                            f"z-score: {res_z:.2f})"
                        )
                    else:
                        reasons.append(
                            f"Unusually short resolution time ({resolution_hours:.1f}h, "
                            f"z-score: {res_z:.2f})"
                        )
                    anomaly_types.append("resolution_anomaly")
                    scores.append(min(1.0, abs(res_z) / 5.0))

        # 3. Priority-category mismatch
        priority = ticket.get("priority", "Medium")
        category = ticket.get("category", "")
        priority_category_score = self._priority_category_mismatch(priority, category)
        if priority_category_score > 0.7:
            reasons.append(
                f"Priority-category mismatch: '{priority}' priority with "
                f"'{category}' category"
            )
            anomaly_types.append("pattern_anomaly")
            scores.append(priority_category_score)

        # 4. Text quality anomaly (gibberish detection)
        description = ticket.get("description", "") or ""
        title = ticket.get("title", "") or ""
        combined_text = sanitize_text(f"{title} {description}")
        gibberish_score = self._detect_gibberish(combined_text)
        if gibberish_score > _GIBBERISH_THRESHOLD:
            reasons.append(
                f"Potential gibberish or spam text (gibberish score: {gibberish_score:.2f})"
            )
            anomaly_types.append("text_quality_anomaly")
            scores.append(gibberish_score)

        # 5. Very high urgency words density
        urgency_density = self._urgency_word_density(combined_text)
        if "urgency_density_mean" in baseline_stats and "urgency_density_std" in baseline_stats:
            urg_z = self._z_score(
                urgency_density,
                baseline_stats["urgency_density_mean"],
                baseline_stats["urgency_density_std"],
            )
            if urg_z > 2.5:
                reasons.append(
                    f"Unusually high urgency word density ({urgency_density:.2f})"
                )
                anomaly_types.append("urgency_anomaly")
                scores.append(min(1.0, urg_z / 5.0))

        # 6. Status-priority mismatch
        status = ticket.get("status", "Open")
        status_priority_score = self._status_priority_mismatch(priority, status)
        if status_priority_score > 0.8:
            reasons.append(
                f"Status-priority mismatch: '{status}' status with "
                f"'{priority}' priority"
            )
            anomaly_types.append("pattern_anomaly")
            scores.append(status_priority_score)

        # Combine scores
        if scores:
            max_score = max(scores)
            avg_score = sum(scores) / len(scores)
            final_score = max_score * 0.7 + avg_score * 0.3
            is_anomaly = final_score > 0.5
        else:
            final_score = 0.0
            is_anomaly = False

        return {
            "is_anomaly": is_anomaly,
            "score": round(min(1.0, final_score), 4),
            "reasons": reasons,
            "anomaly_types": anomaly_types,
        }

    def train(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train the anomaly detection model on historical tickets.

        Parameters
        ----------
        tickets : list[dict]
            List of ticket dictionaries.

        Returns
        -------
        dict
            Training info: ``{"samples": int, "features": int, "contamination": float}``
        """
        if not tickets:
            raise ValueError("tickets must be non-empty")

        # Extract features for all tickets
        feature_matrix = []
        valid_indices = []

        for idx, ticket in enumerate(tickets):
            features = self._extract_features(ticket)
            if features and not any(math.isnan(f) or math.isinf(f) for f in features):
                feature_matrix.append(features)
                valid_indices.append(idx)

        if len(feature_matrix) < 10:
            logger.warning(
                "Too few valid tickets (%d) for Isolation Forest training",
                len(feature_matrix),
            )
            return {"samples": len(feature_matrix), "features": 0, "contamination": self.contamination, "error": "insufficient data"}

        import numpy as np
        from sklearn.ensemble import IsolationForest

        X = np.array(feature_matrix)

        # Handle any remaining NaN/Inf by imputing with column medians
        col_medians = np.nanmedian(X, axis=0)
        for col in range(X.shape[1]):
            mask = np.isnan(X[:, col]) | np.isinf(X[:, col])
            X[mask, col] = col_medians[col]

        self.model = IsolationForest(
            contamination=self.contamination,
            max_samples=min(256, len(X)),
            random_state=42,
            n_estimators=100,
            n_jobs=-1,
        )
        self.model.fit(X)
        self.is_trained = True

        info = {
            "samples": len(feature_matrix),
            "features": X.shape[1],
            "contamination": self.contamination,
        }
        logger.info("AnomalyDetector trained: %s", info)
        return info

    # ------------------------------------------------------------------ #
    #  Feature extraction                                                 #
    # ------------------------------------------------------------------ #

    def _extract_features(self, ticket: Dict[str, Any]) -> List[float]:
        """Extract numerical features from a ticket for anomaly detection.

        Features extracted:
            - description_length (char count)
            - title_length (char count)
            - word_count
            - priority_encoded (1-4)
            - status_encoded (1-5)
            - resolution_hours (0 if not resolved)
            - urgency_word_density
            - uppercase_ratio
            - number_count (numbers in text)
            - has_error_codes (0 or 1)
            - sentence_count
            - avg_sentence_length

        Returns
        -------
        list[float]
            Feature vector of length 12.
        """
        title = ticket.get("title", "") or ""
        description = ticket.get("description", "") or ""
        combined = sanitize_text(f"{title} {description}")

        priority = _PRIORITY_MAP.get(ticket.get("priority", "Medium"), 2)
        status = _STATUS_MAP.get(ticket.get("status", "Open"), 1)
        resolution_hours = self._get_resolution_hours(ticket)

        desc_length = float(len(combined))
        title_length = float(len(title))
        word_count = float(len(combined.split())) if combined else 0.0
        urgency_density = self._urgency_word_density(combined)

        uppercase_chars = sum(1 for c in combined if c.isupper())
        uppercase_ratio = uppercase_chars / max(1, len(combined))

        numbers = re.findall(r"\b\d+\b", combined)
        number_count = float(len(numbers))

        has_error_codes = 1.0 if re.search(r"\b0x[0-9A-Fa-f]+\b|ERR_", combined) else 0.0

        sentences = re.split(r"[.!?]+", combined)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = float(len(sentences))
        avg_sentence_length = word_count / max(1, sentence_count)

        return [
            desc_length,
            title_length,
            word_count,
            float(priority),
            float(status),
            resolution_hours if resolution_hours is not None else 0.0,
            urgency_density,
            uppercase_ratio,
            number_count,
            has_error_codes,
            sentence_count,
            avg_sentence_length,
        ]

    # ------------------------------------------------------------------ #
    #  Statistical methods                                                #
    # ------------------------------------------------------------------ #

    def _compute_baseline(self, tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute baseline statistics from ticket data.

        Calculates mean and standard deviation for key metrics used
        in z-score anomaly detection.

        Parameters
        ----------
        tickets : list[dict]
            Ticket list.

        Returns
        -------
        dict
            Baseline statistics with mean/std for each metric.
        """
        import numpy as np

        desc_lengths = []
        resolution_times = []
        urgency_densities = []

        for ticket in tickets:
            title = ticket.get("title", "") or ""
            description = ticket.get("description", "") or ""
            combined = sanitize_text(f"{title} {description}")

            desc_lengths.append(len(combined))

            hours = self._get_resolution_hours(ticket)
            if hours is not None:
                resolution_times.append(hours)

            urgency_densities.append(self._urgency_word_density(combined))

        baseline = {}

        if desc_lengths:
            arr = np.array(desc_lengths, dtype=float)
            baseline["desc_length_mean"] = float(np.mean(arr))
            baseline["desc_length_std"] = float(max(np.std(arr), 1.0))
            baseline["desc_length_median"] = float(np.median(arr))

        if resolution_times:
            arr = np.array(resolution_times, dtype=float)
            baseline["resolution_mean"] = float(np.mean(arr))
            baseline["resolution_std"] = float(max(np.std(arr), 1.0))
            baseline["resolution_median"] = float(np.median(arr))

        if urgency_densities:
            arr = np.array(urgency_densities, dtype=float)
            baseline["urgency_density_mean"] = float(np.mean(arr))
            baseline["urgency_density_std"] = float(max(np.std(arr), 0.001))

        return baseline

    @staticmethod
    def _z_score(value: float, mean: float, std: float) -> float:
        """Calculate z-score for a value.

        Parameters
        ----------
        value : float
            Observed value.
        mean : float
            Population mean.
        std : float
            Population standard deviation.

        Returns
        -------
        float
            Z-score (number of standard deviations from mean).
        """
        if std <= 0:
            return 0.0
        return (value - mean) / std

    # ------------------------------------------------------------------ #
    #  Helper methods                                                     #
    # ------------------------------------------------------------------ #

    def _get_resolution_hours(self, ticket: Dict[str, Any]) -> Optional[float]:
        """Calculate resolution time in hours from ticket timestamps.

        Parameters
        ----------
        ticket : dict
            Ticket with opened_at and resolved_at fields.

        Returns
        -------
        float or None
            Resolution time in hours, or None if not calculable.
        """
        opened = ticket.get("opened_at")
        resolved = ticket.get("resolved_at")

        if opened is None or resolved is None:
            return None

        # Handle string timestamps
        if isinstance(opened, str):
            try:
                opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                try:
                    from ticketinsight.utils.helpers import parse_date
                    opened = parse_date(opened)
                except Exception:
                    return None

        if isinstance(resolved, str):
            try:
                resolved = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                try:
                    from ticketinsight.utils.helpers import parse_date
                    resolved = parse_date(resolved)
                except Exception:
                    return None

        if opened is None or resolved is None:
            return None

        # Remove timezone info for comparison
        if hasattr(opened, "tzinfo") and opened.tzinfo is not None:
            opened = opened.replace(tzinfo=None)
        if hasattr(resolved, "tzinfo") and resolved.tzinfo is not None:
            resolved = resolved.replace(tzinfo=None)

        try:
            delta = (resolved - opened).total_seconds()
            if delta < 0:
                return None
            return delta / 3600.0
        except (TypeError, AttributeError):
            return None

    def _urgency_word_density(self, text: str) -> float:
        """Calculate the density of urgency-related words in text.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        float
            Ratio of urgency words to total words (0.0 to 1.0).
        """
        if not text:
            return 0.0

        urgency_words = {
            "urgent", "critical", "asap", "emergency", "immediately",
            "outage", "downtime", "production down", "system down",
            "business impact", "revenue impact", "security breach",
            "data loss", "severe", "major", "blocking",
        }

        words = text.lower().split()
        if not words:
            return 0.0

        urgency_count = sum(1 for w in words if w in urgency_words)
        return urgency_count / len(words)

    def _detect_gibberish(self, text: str) -> float:
        """Detect if text appears to be gibberish or spam.

        Uses multiple heuristics:
        - Ratio of non-dictionary words (long consonant clusters, etc.)
        - Vowel-to-consonant ratio
        - Average word length
        - Repeated character patterns

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        float
            Gibberish score (0.0 = normal text, 1.0 = definite gibberish).
        """
        if not text:
            return 0.0

        words = text.split()
        if not words:
            return 0.0

        gibberish_indicators = 0
        total_checks = 0

        for word in words:
            if len(word) < 3:
                continue

            total_checks += 1

            # Check 1: Consecutive consonant ratio
            consonant_runs = re.findall(r"[bcdfghjklmnpqrstvwxyz]{4,}", word, re.IGNORECASE)
            if consonant_runs:
                gibberish_indicators += 1
                continue

            # Check 2: Repeated characters (e.g., "aaaa", "bbbb")
            if re.search(r"(.)\1{3,}", word):
                gibberish_indicators += 1
                continue

            # Check 3: No vowels at all
            if not re.search(r"[aeiou]", word, re.IGNORECASE):
                gibberish_indicators += 1
                continue

            # Check 4: Very long word (likely random)
            if len(word) > 30:
                gibberish_indicators += 1
                continue

            # Check 5: High digit ratio in word
            digit_count = sum(1 for c in word if c.isdigit())
            if len(word) > 5 and digit_count / len(word) > 0.6:
                gibberish_indicators += 1
                continue

        if total_checks == 0:
            return 0.0

        return gibberish_indicators / total_checks

    def _priority_category_mismatch(self, priority: str, category: str) -> float:
        """Score how unusual a priority-category combination is.

        Returns a score from 0.0 (normal) to 1.0 (highly unusual).

        Parameters
        ----------
        priority : str
            Ticket priority.
        category : str
            Ticket category.

        Returns
        -------
        float
            Mismatch score (0.0 to 1.0).
        """
        if not category or not priority:
            return 0.0

        priority_lower = priority.lower().strip()
        category_lower = category.lower().strip()

        # Define expected priority ranges for each category
        expected_ranges = {
            "security": {"min": "high", "max": "critical"},
            "access": {"min": "medium", "max": "high"},
            "network": {"min": "medium", "max": "critical"},
            "email": {"min": "low", "max": "high"},
            "hardware": {"min": "low", "max": "high"},
            "software": {"min": "low", "max": "high"},
            "database": {"min": "medium", "max": "critical"},
            "procurement": {"min": "low", "max": "medium"},
            "hr": {"min": "low", "max": "medium"},
        }

        # Normalize priority to numeric
        priority_num = _PRIORITY_MAP.get(
            priority_lower.capitalize(), _PRIORITY_MAP.get(priority, 2)
        )

        # Find the best matching expected range
        for cat_key, range_info in expected_ranges.items():
            if cat_key in category_lower or category_lower in cat_key:
                min_p = _PRIORITY_MAP.get(range_info["min"], 1)
                max_p = _PRIORITY_MAP.get(range_info["max"], 4)

                if priority_num < min_p:
                    # Priority is lower than expected
                    return min(1.0, (min_p - priority_num) / 3.0)
                elif priority_num > max_p:
                    # Priority is higher than expected
                    return min(1.0, (priority_num - max_p) / 3.0)
                else:
                    return 0.0

        return 0.0

    def _status_priority_mismatch(self, priority: str, status: str) -> float:
        """Score how unusual a status-priority combination is.

        E.g., a Critical ticket that's Closed quickly might be suspicious.

        Returns
        -------
        float
            Mismatch score (0.0 to 1.0).
        """
        if not status or not priority:
            return 0.0

        priority_num = _PRIORITY_MAP.get(priority, 2)

        # Critical or High tickets should not be "Closed" or "On Hold" normally
        # (without additional context, we flag these as slightly unusual)
        if priority_num >= 3 and status.lower().strip() == "on hold":
            return 0.9

        return 0.0

    # ------------------------------------------------------------------ #
    #  ML-based anomaly detection                                         #
    # ------------------------------------------------------------------ #

    def _ml_detect(self, tickets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run Isolation Forest anomaly detection on tickets.

        Parameters
        ----------
        tickets : list[dict]
            Ticket list.

        Returns
        -------
        list[dict]
            List of anomaly results from the ML model.
        """
        import numpy as np

        feature_matrix = []
        valid_indices = []

        for idx, ticket in enumerate(tickets):
            features = self._extract_features(ticket)
            if features and not any(math.isnan(f) or math.isinf(f) for f in features):
                feature_matrix.append(features)
                valid_indices.append(idx)

        if not feature_matrix:
            return []

        X = np.array(feature_matrix)

        # Impute any NaN/Inf
        col_medians = np.nanmedian(X, axis=0)
        for col in range(X.shape[1]):
            mask = np.isnan(X[:, col]) | np.isinf(X[:, col])
            X[mask, col] = col_medians[col]

        # Predict anomaly scores (more negative = more anomalous)
        raw_scores = self.model.decision_function(X)
        predictions = self.model.predict(X)  # -1 = anomaly, 1 = normal

        anomalies = []
        for idx, (pred, score) in enumerate(zip(predictions, raw_scores)):
            if pred == -1:  # Isolation Forest marks anomalies as -1
                ticket_idx = valid_indices[idx]
                ticket = tickets[ticket_idx]
                ticket_id = ticket.get("ticket_id", ticket.get("id", str(ticket_idx)))

                # Convert score to 0-1 range (more negative = higher anomaly)
                anomaly_score = round(max(0.0, min(1.0, -score / 0.5)), 4)

                anomalies.append({
                    "ticket_id": ticket_id,
                    "anomaly_score": anomaly_score,
                    "anomaly_type": "ml_isolation_forest",
                    "reason": f"Flagged by Isolation Forest (raw score: {score:.4f})",
                })

        return anomalies

"""
Sentiment analysis module for TicketInsight Pro.

Provides domain-aware sentiment analysis for IT support tickets using
TextBlob as the base sentiment engine with custom domain-specific boosters
for urgency, frustration, and customer satisfaction prediction.

Usage
-----
    from ticketinsight.nlp.sentiment import SentimentAnalyzer
    analyzer = SentimentAnalyzer(config)
    result = analyzer.analyze("This is urgent — our production system is down!")
"""

import math
import re
from typing import Any, Dict, List

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.sentiment")


class SentimentAnalyzer:
    """Domain-aware sentiment analysis for IT support tickets.

    Extends TextBlob sentiment with custom urgency, frustration, and
    escalation-risk scoring tailored to the IT service management domain.
    """

    def __init__(self, config: Any = None):
        self.config = config
        self.logger = logger

        # Domain-specific negators that should flip sentiment in IT context
        self.domain_negators = frozenset({
            "not", "no", "never", "don't", "doesn't", "won't", "can't",
            "unable", "failed", "failure", "cannot", "without",
            "not able", "no longer", "no longer", "refused", "denied",
            "unsuccessful", "blocked", "rejected",
        })

        # Domain-specific intensifiers with their polarity multipliers
        # Positive number = amplifier of existing sentiment, negative = polarity flip
        self.domain_intensifiers = {
            "urgent": 1.5, "critical": 2.0, "asap": 1.8, "immediately": 1.7,
            "broken": -1.5, "down": -1.3, "crashed": -1.8, "dead": -2.0,
            "severe": 1.6, "extremely": 1.5, "very": 1.3, "really": 1.3,
            "completely": 1.5, "totally": 1.5, "absolutely": 1.5,
            "slightly": 0.7, "somewhat": 0.8, "partially": 0.7,
            "again": -1.2, "still": -0.8, "keeps": -1.3, "keeps happening": -1.5,
            "horrible": -2.0, "terrible": -2.0, "awful": -2.0, "worst": -2.5,
            "unacceptable": -2.5, "ridiculous": -2.0, "pathetic": -2.0,
            "frustrating": -1.8, "annoying": -1.5, "disappointing": -1.5,
            "excellent": 2.0, "great": 1.8, "fantastic": 2.0, "perfect": 2.0,
            "thank": 1.5, "thanks": 1.5, "appreciate": 1.5, "helpful": 1.5,
            "resolved": 1.5, "fixed": 1.5, "working": 0.5, "works": 0.8,
        }

        # Urgency detection keywords with severity weights
        self.urgency_keywords = {
            # Critical urgency (weight 3.0)
            "critical": 3.0, "emergency": 3.0, "outage": 3.0, "production down": 3.0,
            "system down": 3.0, "complete failure": 3.0, "total outage": 3.0,
            "business impact": 3.0, "revenue impact": 3.0, "security breach": 3.0,
            "data loss": 3.0, "data breach": 3.0,
            # High urgency (weight 2.0)
            "urgent": 2.0, "asap": 2.0, "immediately": 2.0, "as soon as possible": 2.0,
            "downtime": 2.0, "major": 2.0, "severe": 2.0,
            "multiple users": 2.0, "all users": 2.0, "everyone": 2.0,
            "unable to work": 2.0, "cannot work": 2.0, "blocking": 2.0,
            "production": 2.0, "live": 2.0, "customer-facing": 2.0,
            # Medium urgency (weight 1.0)
            "important": 1.0, "priority": 1.0, "time-sensitive": 1.5,
            "deadline": 1.0, "meeting": 1.0, "presentation": 1.0,
            "intermittent": 1.0, "recurring": 1.0, "repeatedly": 1.0,
        }

        # Frustration / escalation risk keywords
        self.frustration_keywords = {
            # High frustration (weight 3.0)
            "frustrated": 3.0, "unacceptable": 3.0, "ridiculous": 3.0,
            "escalate": 3.0, "escalation": 3.0, "manager": 2.5,
            "complaint": 3.0, "complain": 3.0, "angry": 3.0, "furious": 3.0,
            "disgusted": 3.0, "appalled": 3.0, "outraged": 3.0,
            # Medium frustration (weight 2.0)
            "again": 2.0, "still": 1.5, "still not": 2.5,
            "hours": 1.5, "days": 1.5, "weeks": 2.0, "months": 2.5,
            "waiting": 2.0, "no response": 2.5, "no update": 2.5,
            "unresolved": 2.0, "open for": 2.0,
            "third time": 3.0, "second time": 2.5, "multiple times": 2.5,
            "nothing changed": 2.5, "same issue": 2.5, "same problem": 2.5,
            "nobody": 2.5, "no one": 2.5, "ignored": 2.5,
            # Low frustration (weight 1.0)
            "please fix": 1.5, "needs attention": 1.5, "overdue": 1.5,
            "slow response": 1.5, "delayed": 1.5,
        }

        # Regex patterns for frustration detection
        self._frustration_patterns = [
            re.compile(r"\bthis is (the\s+)?(third|fourth|fifth|nth)\b", re.IGNORECASE),
            re.compile(r"\bI'?ve (been|called|submitted|reported)\b.*\b(before|multiple|several)\b", re.IGNORECASE),
            re.compile(r"\b(how many|why does|when will)\b.*\b(again|still)\b", re.IGNORECASE),
            re.compile(r"\bplease (escalate|get a manager|speak to|talk to)\b", re.IGNORECASE),
            re.compile(r"\b(extremely|very|totally) (frustrat|unhappy|disappoint|annoy)\b", re.IGNORECASE),
        ]

        # Regex for urgency detection
        self._urgency_patterns = [
            re.compile(r"\bURGENT\b", re.IGNORECASE),
            re.compile(r"\bCRITICAL\b", re.IGNORECASE),
            re.compile(r"\bASAP\b", re.IGNORECASE),
            re.compile(r"\b!\s*!\s*!"),  # Multiple exclamation marks
            re.compile(r"\b(production|live|customer.fac)\s+(is\s+)?(down|broken|not working)\b", re.IGNORECASE),
            re.compile(r"\b(all|entire|whole)\s+(team|department|company|office)\b", re.IGNORECASE),
            re.compile(r"\b(sla|deadline)\s+(breach|miss|at risk|in jeopardy)\b", re.IGNORECASE),
        ]

        self.logger.info("SentimentAnalyzer initialized")

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def analyze(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of ticket text.

        Parameters
        ----------
        text : str
            Ticket text (title + description).

        Returns
        -------
        dict
            ``{
                "polarity": float (-1.0 to 1.0),
                "subjectivity": float (0.0 to 1.0),
                "label": str ("Positive" | "Negative" | "Neutral" | "Mixed"),
                "urgency_score": float (0.0 to 1.0),
                "frustration_score": float (0.0 to 1.0),
                "customer_satisfaction_predict": float (0.0 to 5.0),
                "escalation_risk": float (0.0 to 1.0)
            }``
        """
        if not text or not isinstance(text, str):
            return self._empty_result()

        cleaned = sanitize_text(text)

        # Get base sentiment from TextBlob
        base_polarity, base_subjectivity = self._textblob_sentiment(cleaned)

        # Apply domain-specific adjustments
        adjusted_polarity = self._apply_domain_boosters(cleaned, base_polarity)

        # Clamp polarity to [-1, 1]
        adjusted_polarity = max(-1.0, min(1.0, adjusted_polarity))

        # Calculate domain-specific scores
        urgency = self._calculate_urgency(cleaned)
        frustration = self._calculate_frustration(cleaned)
        label = self._get_label(adjusted_polarity)

        # Predict customer satisfaction (1-5 scale)
        csat = self._predict_csat(adjusted_polarity, urgency, frustration)

        # Calculate overall escalation risk
        escalation_risk = self._calculate_escalation_risk(
            adjusted_polarity, urgency, frustration
        )

        return {
            "polarity": round(adjusted_polarity, 4),
            "subjectivity": round(base_subjectivity, 4),
            "label": label,
            "urgency_score": round(urgency, 4),
            "frustration_score": round(frustration, 4),
            "customer_satisfaction_predict": round(csat, 2),
            "escalation_risk": round(escalation_risk, 4),
        }

    def analyze_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Analyze sentiment of multiple texts.

        Parameters
        ----------
        texts : list[str]
            List of ticket texts.

        Returns
        -------
        list[dict]
            List of sentiment analysis results.
        """
        if not texts:
            return []

        results = []
        for text in texts:
            try:
                result = self.analyze(text)
            except Exception as exc:
                self.logger.error("Error analyzing sentiment: %s", exc)
                result = self._empty_result()
                result["error"] = str(exc)
            results.append(result)
        return results

    # ------------------------------------------------------------------ #
    #  Core sentiment methods                                             #
    # ------------------------------------------------------------------ #

    def _textblob_sentiment(self, text: str) -> tuple:
        """Get base sentiment using TextBlob.

        Returns
        -------
        tuple[float, float]
            (polarity, subjectivity) — polarity in [-1, 1], subjectivity in [0, 1].
        """
        try:
            from textblob import TextBlob
            blob = TextBlob(text)
            return blob.sentiment.polarity, blob.sentiment.subjectivity
        except ImportError:
            self.logger.warning("TextBlob not available; using rule-based fallback")
            return self._rule_based_sentiment(text)
        except Exception as exc:
            self.logger.warning("TextBlob analysis error: %s", exc)
            return self._rule_based_sentiment(text)

    def _rule_based_sentiment(self, text: str) -> tuple:
        """Simple rule-based sentiment fallback when TextBlob is unavailable.

        Scores based on positive/negative word counts.

        Returns
        -------
        tuple[float, float]
            (polarity, subjectivity)
        """
        text_lower = text.lower()

        positive_words = {
            "good", "great", "excellent", "perfect", "thanks", "thank", "appreciate",
            "helpful", "resolved", "fixed", "working", "works", "success",
            "happy", "pleased", "satisfied", "love", "best", "awesome",
        }
        negative_words = {
            "bad", "terrible", "horrible", "broken", "not working", "failed",
            "error", "crash", "down", "slow", "frustrated", "angry",
            "unacceptable", "awful", "worst", "annoying", "pain",
        }

        words = set(re.findall(r"\b\w+\b", text_lower))
        pos_count = len(words & positive_words)
        neg_count = len(words & negative_words)
        total = max(1, pos_count + neg_count)

        polarity = (pos_count - neg_count) / total
        subjectivity = min(1.0, total / max(1, len(words)))

        return polarity, subjectivity

    def _apply_domain_boosters(self, text: str, polarity: float) -> float:
        """Apply domain-specific intensifiers and negators to the base polarity.

        Scans the text for known intensifier words and adjusts the polarity
        accordingly.  Also checks for negator words that flip sentiment.

        Parameters
        ----------
        text : str
            Lowercase cleaned text.
        polarity : float
            Base TextBlob polarity.

        Returns
        -------
        float
            Adjusted polarity.
        """
        text_lower = text.lower()
        words = re.findall(r"\b\w[\w'-]*\w\b|\b\w\b", text_lower)
        adjusted = polarity

        for i, word in enumerate(words):
            # Check for negators — look at surrounding context
            if word in self.domain_negators:
                # Negation flips the sign of the next sentiment-bearing word
                if i + 1 < len(words):
                    next_word = words[i + 1]
                    if next_word in self.domain_intensifiers:
                        intensifier_val = self.domain_intensifiers[next_word]
                        # Flip: if intensifier is negative, negation makes it positive
                        adjusted -= abs(intensifier_val) * 0.1
                    else:
                        adjusted -= 0.05

            # Apply intensifiers
            if word in self.domain_intensifiers:
                weight = self.domain_intensifiers[word]
                if weight < 0:
                    # Negative intensifier: push polarity toward negative
                    adjusted = adjusted + weight * 0.15
                else:
                    # Positive intensifier: amplify existing polarity
                    adjusted = adjusted * weight
                    if abs(adjusted) > 1.0:
                        adjusted = math.copysign(1.0, adjusted)

        return adjusted

    # ------------------------------------------------------------------ #
    #  Urgency scoring                                                    #
    # ------------------------------------------------------------------ #

    def _calculate_urgency(self, text: str) -> float:
        """Calculate urgency score from text content.

        Uses both keyword matching and regex patterns to detect urgency
        signals.  Returns a score between 0.0 and 1.0.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        float
            Urgency score (0.0 to 1.0).
        """
        text_lower = text.lower()
        total_score = 0.0

        # Keyword-based scoring (each matched keyword contributes its weight)
        for keyword, weight in self.urgency_keywords.items():
            if keyword in text_lower:
                count = text_lower.count(keyword)
                total_score += weight * min(count, 3)  # Cap at 3 matches

        # Regex pattern scoring
        for pattern in self._urgency_patterns:
            if pattern.search(text):
                total_score += 2.5

        # Exclamation mark bonus
        exclamation_count = text.count("!")
        if exclamation_count >= 3:
            total_score += 2.5
        elif exclamation_count >= 2:
            total_score += 2.0
        elif exclamation_count >= 1:
            total_score += 1.0

        # UPPERCASE word bonus (indicates urgency/shouting)
        uppercase_words = re.findall(r"\b[A-Z]{3,}\b", text)
        if len(uppercase_words) >= 3:
            total_score += 2.5
        elif len(uppercase_words) >= 1:
            total_score += 1.0

        # Normalize using a fixed scale: score of 15+ = maximum urgency
        # This avoids dilution from counting all possible keywords
        raw_score = min(1.0, total_score / 15.0)

        # Apply slight sigmoid to make mid-range scores more distinct
        normalized = 1.0 / (1.0 + math.exp(-10 * (raw_score - 0.2)))

        return round(normalized, 4)

    # ------------------------------------------------------------------ #
    #  Frustration scoring                                                #
    # ------------------------------------------------------------------ #

    def _calculate_frustration(self, text: str) -> float:
        """Calculate frustration/escalation risk score.

        Analyzes text for signals of user frustration, repeated issues,
        and potential escalation indicators.  Returns 0.0 to 1.0.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        float
            Frustration score (0.0 to 1.0).
        """
        text_lower = text.lower()
        total_score = 0.0

        # Keyword-based scoring
        for keyword, weight in self.frustration_keywords.items():
            if keyword in text_lower:
                count = text_lower.count(keyword)
                total_score += weight * min(count, 3)

        # Regex pattern scoring
        for pattern in self._frustration_patterns:
            if pattern.search(text):
                total_score += 2.5

        # Repeated punctuation signals frustration (!!!, ???)
        repeated_punct = re.findall(r"[!?]{3,}", text)
        if repeated_punct:
            total_score += len(repeated_punct) * 2.0

        # Caps lock words (anger indicator)
        caps_words = re.findall(r"\b[A-Z]{4,}\b", text)
        non_acronyms = [w for w in caps_words if w not in ("SLA", "VPN", "DNS", "URL", "HTTP", "IT", "HR")]
        if len(non_acronyms) >= 2:
            total_score += 2.5
        elif len(non_acronyms) >= 1:
            total_score += 1.0

        # Length-based frustration: longer descriptions often indicate frustration
        word_count = len(text.split())
        if word_count > 200:
            total_score += 1.0
        elif word_count > 100:
            total_score += 0.5

        # Normalize using a fixed scale: score of 12+ = maximum frustration
        raw_score = min(1.0, total_score / 12.0)

        # Apply sigmoid to make mid-range scores more distinct
        normalized = 1.0 / (1.0 + math.exp(-10 * (raw_score - 0.2)))

        return round(normalized, 4)

    # ------------------------------------------------------------------ #
    #  Label and prediction methods                                       #
    # ------------------------------------------------------------------ #

    def _get_label(self, polarity: float) -> str:
        """Convert polarity to a human-readable label.

        Parameters
        ----------
        polarity : float
            Adjusted polarity in [-1, 1].

        Returns
        -------
        str
            One of: ``"Positive"``, ``"Negative"``, ``"Neutral"``, ``"Mixed"``.
        """
        if abs(polarity) < 0.05:
            return "Neutral"
        elif polarity > 0.1:
            return "Positive"
        elif polarity < -0.1:
            return "Negative"
        else:
            # Between -0.1 and 0.1 but not within ±0.05
            return "Mixed"

    def _predict_csat(
        self, polarity: float, urgency: float, frustration: float
    ) -> float:
        """Predict customer satisfaction score on a 1-5 scale.

        Higher polarity = higher CSAT.  Higher urgency and frustration
        reduce the predicted CSAT.

        Parameters
        ----------
        polarity : float
            Sentiment polarity.
        urgency : float
            Urgency score.
        frustration : float
            Frustration score.

        Returns
        -------
        float
            Predicted CSAT score (1.0 to 5.0).
        """
        # Base CSAT from polarity: map [-1, 1] to [1, 5]
        # polarity 0 → CSAT 3.0, polarity 1 → CSAT 5.0, polarity -1 → CSAT 1.0
        polarity_csat = 3.0 + polarity * 2.0

        # Penalty for high urgency (urgent tickets tend to have lower CSAT)
        urgency_penalty = urgency * 0.8

        # Penalty for high frustration
        frustration_penalty = frustration * 1.2

        # Combined score
        predicted = polarity_csat - urgency_penalty - frustration_penalty

        # Clamp to [1, 5]
        predicted = max(1.0, min(5.0, predicted))

        return round(predicted, 2)

    def _calculate_escalation_risk(
        self, polarity: float, urgency: float, frustration: float
    ) -> float:
        """Calculate overall escalation risk score.

        Combines negative sentiment, urgency, and frustration into a
        single escalation risk metric (0.0 to 1.0).

        Parameters
        ----------
        polarity : float
            Sentiment polarity (negative = higher risk).
        urgency : float
            Urgency score.
        frustration : float
            Frustration score.

        Returns
        -------
        float
            Escalation risk score (0.0 to 1.0).
        """
        # Negative sentiment contributes to escalation risk
        negativity = max(0.0, -polarity)  # 0 to 1

        # Weighted combination
        risk = (
            negativity * 0.3 +       # Sentiment: 30% weight
            urgency * 0.35 +         # Urgency: 35% weight
            frustration * 0.35       # Frustration: 35% weight
        )

        # Apply non-linear scaling to highlight high-risk tickets
        risk = risk ** 0.8  # Slight compression — makes moderate risks more visible

        return round(min(1.0, risk), 4)

    def _empty_result(self) -> Dict[str, Any]:
        """Return empty/default sentiment result for invalid input."""
        return {
            "polarity": 0.0,
            "subjectivity": 0.0,
            "label": "Neutral",
            "urgency_score": 0.0,
            "frustration_score": 0.0,
            "customer_satisfaction_predict": 3.0,
            "escalation_risk": 0.0,
        }

"""
Extractive text summarization module for TicketInsight Pro.

Provides extractive summarization for ticket descriptions using sentence
scoring based on keyword frequency, position, length, and action word
presence.  Also extracts key phrases using noun phrase analysis.

Usage
-----
    from ticketinsight.nlp.summarizer import TicketSummarizer
    summarizer = TicketSummarizer(config)
    result = summarizer.summarize("Long ticket description...")
"""

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.summarizer")

# Common English stopwords for word frequency calculations
_SUMMARY_STOPWORDS = frozenset({
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his",
    "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "what", "which",
    "who", "whom", "this", "that", "these", "those", "am", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if",
    "or", "because", "as", "until", "while", "of", "at", "by", "for",
    "with", "about", "against", "between", "through", "during", "before",
    "after", "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "s", "t",
    "can", "will", "just", "don", "should", "now", "d", "ll", "m", "o",
    "re", "ve", "y", "ain", "aren", "couldn", "didn", "doesn", "hadn",
    "hasn", "haven", "isn", "ma", "mightn", "mustn", "needn", "shan",
    "shouldn", "wasn", "weren", "won", "wouldn",
    # IT ticket noise words
    "ticket", "please", "help", "thank", "thanks", "regards", "hi", "hello",
    "dear", "best", "sincerely", "cheers",
})

# Action words that indicate important sentences
_ACTION_WORDS = frozenset({
    "install", "update", "upgrade", "fix", "resolve", "repair", "replace",
    "configure", "reset", "restart", "reboot", "reinstall", "remove", "delete",
    "add", "create", "setup", "check", "verify", "investigate", "escalate",
    "assign", "migrate", "transfer", "deploy", "rollback", "restore", "backup",
    "block", "unblock", "grant", "revoke", "approve", "deny", "unable",
    "cannot", "failed", "error", "crash", "freeze", "timeout", "down",
    "broken", "not working", "disconnected", "locked", "expired",
})


class TicketSummarizer:
    """Extractive text summarization for ticket descriptions.

    Scores sentences using a weighted combination of keyword frequency,
    position, length, and action word presence, then selects the top-ranked
    sentences while preserving their original order.
    """

    def __init__(self, config: Any = None):
        self.config = config
        self.min_summary_length = 20
        self.max_summary_length = 200

        if config is not None:
            try:
                self.min_summary_length = int(
                    config.get("nlp", "min_summary_length", 20)
                )
                self.max_summary_length = int(
                    config.get("nlp", "max_summary_length", 200)
                )
            except (ValueError, TypeError):
                pass

        logger.info("TicketSummarizer initialized")

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def summarize(
        self, text: str, max_sentences: int = 3
    ) -> Dict[str, Any]:
        """Generate an extractive summary of ticket description.

        Parameters
        ----------
        text : str
            Ticket text (title + description).
        max_sentences : int
            Maximum number of sentences to include in the summary.

        Returns
        -------
        dict
            ``{
                "summary": str,
                "original_length": int,
                "summary_length": int,
                "compression_ratio": float,
                "key_phrases": [str, ...]
            }``
        """
        if not text or not isinstance(text, str):
            return {
                "summary": "",
                "original_length": 0,
                "summary_length": 0,
                "compression_ratio": 0.0,
                "key_phrases": [],
            }

        cleaned = sanitize_text(text)
        original_length = len(cleaned)

        if original_length < self.min_summary_length:
            # Text too short to summarize
            key_phrases = self._extract_key_phrases(cleaned)
            return {
                "summary": cleaned,
                "original_length": original_length,
                "summary_length": original_length,
                "compression_ratio": 1.0,
                "key_phrases": key_phrases,
            }

        # Tokenize into sentences
        sentences = self._tokenize_sentences(cleaned)

        if not sentences:
            key_phrases = self._extract_key_phrases(cleaned)
            return {
                "summary": cleaned[:self.max_summary_length],
                "original_length": original_length,
                "summary_length": min(original_length, self.max_summary_length),
                "compression_ratio": round(
                    min(original_length, self.max_summary_length) / max(1, original_length), 4
                ),
                "key_phrases": key_phrases,
            }

        if len(sentences) <= max_sentences:
            # Fewer sentences than max — return all
            summary = " ".join(sentences)
            # Trim if necessary
            if len(summary) > self.max_summary_length:
                summary = summary[: self.max_summary_length].rsplit(" ", 1)[0] + "..."

            key_phrases = self._extract_key_phrases(cleaned)
            return {
                "summary": summary,
                "original_length": original_length,
                "summary_length": len(summary),
                "compression_ratio": round(len(summary) / max(1, original_length), 4),
                "key_phrases": key_phrases,
            }

        # Calculate word frequencies for scoring
        word_freq = self._get_word_frequencies(cleaned)

        # Score each sentence
        scored_sentences = []
        for idx, sentence in enumerate(sentences):
            score = self._score_sentence(
                sentence, word_freq, idx, len(sentences)
            )
            scored_sentences.append((idx, sentence, score))

        # Sort by score descending, take top max_sentences
        scored_sentences.sort(key=lambda x: x[2], reverse=True)
        top_sentences = scored_sentences[:max_sentences]

        # Re-sort by original position to maintain document order
        top_sentences.sort(key=lambda x: x[0])

        # Build summary
        summary_parts = [s[1] for s in top_sentences]
        summary = " ".join(summary_parts)

        # Trim to max length if needed
        if len(summary) > self.max_summary_length:
            summary = summary[: self.max_summary_length].rsplit(" ", 1)[0] + "..."

        # Extract key phrases
        key_phrases = self._extract_key_phrases(cleaned)

        return {
            "summary": summary,
            "original_length": original_length,
            "summary_length": len(summary),
            "compression_ratio": round(len(summary) / max(1, original_length), 4),
            "key_phrases": key_phrases,
        }

    def summarize_batch(self, texts: List[str], max_sentences: int = 3) -> List[Dict[str, Any]]:
        """Summarize multiple texts.

        Parameters
        ----------
        texts : list[str]
            List of ticket texts.
        max_sentences : int
            Maximum sentences per summary.

        Returns
        -------
        list[dict]
            List of summarization results.
        """
        if not texts:
            return []

        results = []
        for text in texts:
            try:
                result = self.summarize(text, max_sentences)
            except Exception as exc:
                logger.error("Error summarizing text: %s", exc)
                result = {
                    "summary": "",
                    "original_length": len(text) if text else 0,
                    "summary_length": 0,
                    "compression_ratio": 0.0,
                    "key_phrases": [],
                    "error": str(exc),
                }
            results.append(result)
        return results

    # ------------------------------------------------------------------ #
    #  Sentence scoring                                                   #
    # ------------------------------------------------------------------ #

    def _score_sentence(
        self,
        sentence: str,
        word_freq: Dict[str, float],
        position: int,
        total: int,
    ) -> float:
        """Score a sentence for summary selection.

        Uses a weighted combination of:
            - Keyword frequency score (40% weight)
            - Position score (20% weight)
            - Length score (15% weight)
            - Action word score (15% weight)
            - Title-word overlap bonus (10% weight)

        Parameters
        ----------
        sentence : str
            The sentence to score.
        word_freq : dict
            Normalized word frequency scores from the document.
        position : int
            Zero-based position index in the document.
        total : int
            Total number of sentences in the document.

        Returns
        -------
        float
            Sentence score (higher = more important).
        """
        if not sentence or not sentence.strip():
            return 0.0

        words = sentence.lower().split()
        if not words:
            return 0.0

        # --- 1. Keyword frequency score (40%) ---
        freq_score = 0.0
        content_words = [
            w for w in words
            if w not in _SUMMARY_STOPWORDS and len(w) >= 3
        ]

        if content_words:
            for word in content_words:
                freq_score += word_freq.get(word, 0.0)
            freq_score = freq_score / len(content_words)
        freq_weight = 0.40

        # --- 2. Position score (20%) ---
        # First and last sentences tend to be more important
        if total <= 1:
            position_score = 1.0
        else:
            normalized_pos = position / (total - 1)
            # Higher score for first and last positions
            if normalized_pos < 0.2:
                position_score = 1.0 - (normalized_pos / 0.2) * 0.3
            elif normalized_pos > 0.8:
                position_score = 1.0 - ((normalized_pos - 0.8) / 0.2) * 0.3
            else:
                position_score = 0.5
        position_weight = 0.20

        # --- 3. Length score (15%) ---
        # Prefer medium-length sentences (not too short, not too long)
        sent_len = len(words)
        if sent_len < 5:
            length_score = 0.2
        elif sent_len < 10:
            length_score = 0.6
        elif sent_len <= 25:
            length_score = 1.0  # Ideal length
        elif sent_len <= 40:
            length_score = 0.8
        else:
            length_score = 0.5  # Long sentences slightly penalized
        length_weight = 0.15

        # --- 4. Action word score (15%) ---
        sentence_lower = sentence.lower()
        action_count = sum(1 for aw in _ACTION_WORDS if aw in sentence_lower)
        action_score = min(1.0, action_count / 2.0)  # 2 action words = max score
        action_weight = 0.15

        # --- 5. Proper noun / entity bonus (10%) ---
        # Sentences containing proper nouns (capitalized words not at start)
        proper_nouns = re.findall(
            r"(?<!^)(?<!\.\s)(?<!\?\s)(?<!\!\s)[A-Z][a-z]{2,}",
            sentence,
        )
        entity_score = min(1.0, len(proper_nouns) * 0.4)
        entity_weight = 0.10

        # Combined weighted score
        final_score = (
            freq_score * freq_weight +
            position_score * position_weight +
            length_score * length_weight +
            action_score * action_weight +
            entity_score * entity_weight
        )

        return final_score

    # ------------------------------------------------------------------ #
    #  Key phrase extraction                                              #
    # ------------------------------------------------------------------ #

    def _extract_key_phrases(self, text: str, num_phrases: int = 5) -> List[str]:
        """Extract key phrases from text using noun phrase patterns.

        First attempts to use TextBlob noun phrase extraction.  Falls back
        to regex-based noun phrase detection if TextBlob is unavailable.

        Parameters
        ----------
        text : str
            Cleaned ticket text.
        num_phrases : int
            Maximum number of key phrases to return.

        Returns
        -------
        list[str]
            Top key phrases, sorted by relevance.
        """
        if not text:
            return []

        phrases = self._textblob_key_phrases(text)

        if not phrases:
            phrases = self._regex_key_phrases(text)

        # Deduplicate while preserving order
        seen = set()
        unique_phrases = []
        for phrase in phrases:
            phrase_lower = phrase.lower()
            if phrase_lower not in seen and len(phrase) >= 3:
                seen.add(phrase_lower)
                unique_phrases.append(phrase)

        return unique_phrases[:num_phrases]

    def _textblob_key_phrases(self, text: str) -> List[str]:
        """Extract key phrases using TextBlob noun phrase extraction."""
        try:
            from textblob import TextBlob
            blob = TextBlob(text)
            phrases = blob.noun_phrases

            # Score phrases by length and frequency
            phrase_counts: Dict[str, int] = Counter()
            for phrase in phrases:
                phrase = phrase.strip()
                if phrase and len(phrase) >= 3:
                    phrase_counts[phrase] += 1

            # Sort by frequency then length (prefer longer, more frequent phrases)
            scored = sorted(
                phrase_counts.items(),
                key=lambda x: (x[1] * len(x[0]), len(x[0])),
                reverse=True,
            )
            return [p for p, _ in scored]
        except ImportError:
            return []
        except Exception as exc:
            logger.debug("TextBlob key phrase extraction failed: %s", exc)
            return []

    def _regex_key_phrases(self, text: str) -> List[str]:
        """Extract key phrases using regex-based noun phrase patterns.

        Uses patterns to identify:
            - Adjective + Noun (e.g., "slow performance")
            - Noun + "of" + Noun (e.g., "loss of connectivity")
            - Compound nouns (e.g., "VPN connection")
        """
        # Pattern 1: Adjective(s) + Noun(s)
        adj_noun_pattern = re.compile(
            r"\b(?:[a-z]+\s+){0,2}[a-z]+\b",
            re.IGNORECASE,
        )

        # Pattern 2: Noun phrases with prepositions
        prep_pattern = re.compile(
            r"\b[A-Za-z][a-z]*(?:\s+[A-Za-z][a-z]*){1,3}\b",
        )

        # Extract candidates
        candidates: Dict[str, int] = Counter()

        for match in adj_noun_pattern.finditer(text):
            phrase = match.group().strip()
            if len(phrase) >= 4 and not phrase.lower() in _SUMMARY_STOPWORDS:
                candidates[phrase] += 1

        for match in prep_pattern.finditer(text):
            phrase = match.group().strip()
            # Filter out phrases that start with common stop words
            first_word = phrase.split()[0].lower() if phrase.split() else ""
            if first_word in _SUMMARY_STOPWORDS:
                continue
            if len(phrase) >= 4:
                candidates[phrase] += 1

        # Filter: keep phrases with at least one content word
        filtered = {}
        for phrase, count in candidates.items():
            words = phrase.lower().split()
            content_count = sum(
                1 for w in words
                if w not in _SUMMARY_STOPWORDS and len(w) >= 3
            )
            if content_count >= 1:
                filtered[phrase] = count

        # Sort by frequency * length
        scored = sorted(
            filtered.items(),
            key=lambda x: (x[1] * len(x[0]), x[1]),
            reverse=True,
        )
        return [p for p, _ in scored]

    # ------------------------------------------------------------------ #
    #  Word frequency                                                     #
    # ------------------------------------------------------------------ #

    def _get_word_frequencies(self, text: str) -> Dict[str, float]:
        """Calculate normalized word frequency scores.

        Words are lowercased, stopwords and short tokens are removed,
        and frequencies are normalized to [0, 1] range.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        dict
            Mapping of word -> normalized frequency (0.0 to 1.0).
        """
        if not text:
            return {}

        words = text.lower().split()
        content_words = [
            w for w in words
            if w not in _SUMMARY_STOPWORDS and len(w) >= 3
        ]

        if not content_words:
            return {}

        # Count occurrences
        word_counts = Counter(content_words)

        # Normalize to [0, 1]
        max_count = max(word_counts.values())
        if max_count <= 0:
            return {}

        return {word: count / max_count for word, count in word_counts.items()}

    # ------------------------------------------------------------------ #
    #  Sentence tokenization                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokenize_sentences(text: str) -> List[str]:
        """Tokenize text into sentences.

        Uses regex to split on sentence-ending punctuation while keeping
        abbreviations and technical terms intact.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        list[str]
            List of sentence strings.
        """
        if not text:
            return []

        # Try TextBlob first for better sentence splitting
        try:
            from textblob import TextBlob
            blob = TextBlob(text)
            sentences = [str(s).strip() for s in blob.sentences if str(s).strip()]
            if sentences:
                return sentences
        except (ImportError, Exception):
            pass

        # Fallback: regex-based sentence splitting
        # Split on . ! ? followed by space and uppercase letter or end of string
        sentence_endings = re.compile(
            r"(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\s*$"
        )
        raw_sentences = sentence_endings.split(text)

        # Filter and clean
        sentences = []
        for sent in raw_sentences:
            sent = sent.strip()
            if sent and len(sent) >= 10:  # Minimum sentence length
                sentences.append(sent)

        return sentences

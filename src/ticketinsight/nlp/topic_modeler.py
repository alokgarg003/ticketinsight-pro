"""
Topic modeling module for TicketInsight Pro.

Provides topic extraction using Gensim LDA with keyword-based fallback
for when no trained model is available.  Supports both single-document
and batch topic analysis.

Usage
-----
    from ticketinsight.nlp.topic_modeler import TopicModeler
    modeler = TopicModeler(config)
    result = modeler.extract_topics("VPN keeps disconnecting every 20 minutes")
"""

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.topic_modeler")

# Common English stopwords used for text preprocessing
_DEFAULT_STOPWORDS = frozenset({
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your",
    "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she",
    "her", "hers", "herself", "it", "its", "itself", "they", "them", "their",
    "theirs", "themselves", "what", "which", "who", "whom", "this", "that",
    "these", "those", "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an",
    "the", "and", "but", "if", "or", "because", "as", "until", "while", "of",
    "at", "by", "for", "with", "about", "against", "between", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "s", "t",
    "can", "will", "just", "don", "should", "now", "d", "ll", "m", "o",
    "re", "ve", "y", "ain", "aren", "couldn", "didn", "doesn", "hadn",
    "hasn", "haven", "isn", "ma", "mightn", "mustn", "needn", "shan",
    "shouldn", "wasn", "weren", "won", "wouldn",
    # IT-ticket-specific noise words
    "ticket", "please", "help", "issue", "problem", "work", "working",
    "need", "get", "got", "getting", "would", "could", "also", "still",
    "even", "much", "many", "like", "since", "already", "back", "new",
    "last", "first", "one", "two", "three", "etc", "via", "per", "us",
    "im", "ive", "thats", "dont", "cant", "wont", "doesnt", "didnt",
    "isnt", "arent", "wasnt", "werent", "hasnt", "hadnt", "havent",
    "shouldnt", "wouldnt", "couldnt", "mightnt", "mustnt", "neednt",
})

# Topic label mapping heuristic keywords
_TOPIC_LABEL_MAP = {
    "network_connectivity": ["network", "wifi", "vpn", "connection", "internet", "dns"],
    "hardware_issues": ["laptop", "printer", "monitor", "screen", "keyboard", "mouse", "hardware"],
    "access_authentication": ["password", "login", "access", "account", "permission", "locked", "mfa"],
    "email_communication": ["email", "outlook", "mailbox", "calendar", "inbox", "meeting"],
    "software_installation": ["install", "update", "software", "application", "upgrade", "crash", "error"],
    "security_incidents": ["security", "malware", "virus", "phishing", "breach", "suspicious"],
    "onboarding_hr": ["onboarding", "new hire", "employee", "contractor", "badge", "offboarding"],
    "procurement_requests": ["purchase", "license", "order", "renewal", "procurement", "vendor", "invoice"],
    "database_operations": ["database", "query", "sql", "timeout", "backup", "server"],
    "performance_issues": ["slow", "performance", "speed", "lag", "freeze", "response time", "latency"],
    "cloud_infrastructure": ["aws", "azure", "cloud", "instance", "vm", "ec2", "container"],
    "printer_scanner": ["printer", "print", "scanner", "toner", "paper jam", "cartridge"],
}

# Action words useful for scoring sentences in summarization
_ACTION_WORDS = frozenset({
    "install", "update", "upgrade", "fix", "resolve", "repair", "replace",
    "configure", "reset", "restart", "reboot", "reinstall", "remove", "delete",
    "add", "create", "setup", "set up", "check", "verify", "investigate",
    "troubleshoot", "trouble-shoot", "diagnose", "escalate", "assign",
    "migrate", "transfer", "deploy", "rollback", "restore", "backup",
    "block", "unblock", "grant", "revoke", "approve", "deny",
})


class TopicModeler:
    """Topic modeling using Gensim LDA for ticket clustering.

    When no trained LDA model is available, falls back to keyword-frequency
    extraction with category-aware label assignment.
    """

    def __init__(self, config: Any = None):
        self.config = config
        self.dictionary = None
        self.lda_model = None
        self.num_topics = 8
        self.is_trained = False
        self._stopwords = _DEFAULT_STOPWORDS

        # Regex for tokenization
        self._token_re = re.compile(r"[a-z][a-z0-9']{1,25}")

        # Read config
        if config is not None:
            try:
                self.num_topics = int(config.get("nlp", "topic_num_topics", 8))
            except (ValueError, TypeError):
                self.num_topics = 8

        logger.info(
            "TopicModeler initialized (num_topics=%d, trained=%s)",
            self.num_topics,
            self.is_trained,
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def extract_topics(self, text: str, num_keywords: int = 5) -> Dict[str, Any]:
        """Extract the dominant topic for a single document.

        Parameters
        ----------
        text : str
            Ticket text (title + description).
        num_keywords : int
            Number of top keywords to return.

        Returns
        -------
        dict
            ``{
                "topic_id": int,
                "topic_label": str,
                "keywords": [str, ...],
                "probability": float,
                "method": "lda" | "keyword"
            }``
        """
        if not text or not isinstance(text, str):
            return {
                "topic_id": -1,
                "topic_label": "N/A",
                "keywords": [],
                "probability": 0.0,
                "method": "keyword",
            }

        cleaned = sanitize_text(text)

        if self.is_trained and self.lda_model is not None and self.dictionary is not None:
            try:
                return self._lda_extract(cleaned, num_keywords)
            except Exception as exc:
                logger.warning("LDA extraction failed, using fallback: %s", exc)

        return self._keyword_extraction_with_label(cleaned, num_keywords)

    def extract_topics_batch(
        self, texts: List[str], num_keywords: int = 5
    ) -> Dict[str, Any]:
        """Extract topics for a batch of documents.

        Parameters
        ----------
        texts : list[str]
            List of ticket texts.
        num_keywords : int
            Number of keywords per topic.

        Returns
        -------
        dict
            ``{
                "topics": [{id, label, keywords, doc_count}, ...],
                "document_topics": [{doc_idx, topic_id, prob}, ...],
                "method": str
            }``
        """
        if not texts:
            return {
                "topics": [],
                "document_topics": [],
                "method": "keyword",
            }

        cleaned_texts = [sanitize_text(t) for t in texts]

        if self.is_trained and self.lda_model is not None and self.dictionary is not None:
            try:
                return self._lda_batch_extract(cleaned_texts, num_keywords)
            except Exception as exc:
                logger.warning("LDA batch extraction failed, using fallback: %s", exc)

        return self._keyword_batch_extract(cleaned_texts, num_keywords)

    def train(self, texts: List[str], num_topics: int = None) -> Dict[str, Any]:
        """Train LDA model on a document corpus.

        Parameters
        ----------
        texts : list[str]
            Training documents (ticket titles + descriptions).
        num_topics : int, optional
            Number of topics.  Defaults to instance setting.

        Returns
        -------
        dict
            Training info: ``{"num_topics": int, "num_docs": int,
            "vocabulary_size": int}``
        """
        if not texts:
            raise ValueError("texts must be non-empty")

        num_topics = num_topics or self.num_topics

        # Preprocess all documents
        tokenized_docs = []
        for text in texts:
            cleaned = sanitize_text(text)
            tokens = self._preprocess(cleaned)
            if tokens:
                tokenized_docs.append(tokens)

        if len(tokenized_docs) < num_topics:
            logger.warning(
                "Too few documents (%d) for %d topics; reducing topics",
                len(tokenized_docs),
                num_topics,
            )
            num_topics = max(2, len(tokenized_docs) // 3)

        try:
            from gensim.corpora import Dictionary as GensimDict
            from gensim.models import LdaModel
        except ImportError:
            logger.error("Gensim not installed; cannot train LDA model")
            return {"error": "gensim not installed", "num_topics": 0, "num_docs": 0, "vocabulary_size": 0}

        # Create dictionary
        self.dictionary = GensimDict(tokenized_docs)

        # Filter extremes: remove very rare and very common words
        self.dictionary.filter_extremes(
            no_below=2,
            no_above=0.8,
            keep_n=10000,
        )

        # Create bag-of-words corpus
        bow_corpus = [self.dictionary.doc2bow(doc) for doc in tokenized_docs]

        # Filter empty docs
        valid_bows = [(i, bow) for i, bow in enumerate(bow_corpus) if bow]
        if len(valid_bows) < num_topics:
            logger.warning(
                "Too few valid documents (%d) for LDA training",
                len(valid_bows),
            )
            return {"error": "insufficient valid documents", "num_topics": 0, "num_docs": 0, "vocabulary_size": 0}

        # Train LDA model
        self.lda_model = LdaModel(
            corpus=[bow for _, bow in valid_bows],
            id2word=self.dictionary,
            num_topics=num_topics,
            passes=10,
            iterations=200,
            alpha="auto",
            eta="auto",
            random_state=42,
            minimum_probability=0.0,
            chunksize=min(100, len(valid_bows)),
        )

        self.num_topics = num_topics
        self.is_trained = True

        info = {
            "num_topics": num_topics,
            "num_docs": len(tokenized_docs),
            "vocabulary_size": len(self.dictionary),
            "coherence": self._compute_coherence(tokenized_docs),
        }
        logger.info("TopicModeler trained: %s", info)
        return info

    # ------------------------------------------------------------------ #
    #  LDA-based extraction methods                                       #
    # ------------------------------------------------------------------ #

    def _lda_extract(self, text: str, num_keywords: int) -> Dict[str, Any]:
        """Extract topic using the trained LDA model for a single document."""
        tokens = self._preprocess(text)
        if not tokens:
            return {
                "topic_id": -1,
                "topic_label": "N/A",
                "keywords": [],
                "probability": 0.0,
                "method": "lda",
            }

        bow = self.dictionary.doc2bow(tokens)
        if not bow:
            return {
                "topic_id": -1,
                "topic_label": "N/A",
                "keywords": [],
                "probability": 0.0,
                "method": "lda",
            }

        topic_distribution = self.lda_model.get_document_topics(bow, minimum_probability=0.0)

        if not topic_distribution:
            return {
                "topic_id": -1,
                "topic_label": "N/A",
                "keywords": [],
                "probability": 0.0,
                "method": "lda",
            }

        # Sort by probability descending
        topic_distribution.sort(key=lambda x: x[1], reverse=True)
        best_topic_id, best_prob = topic_distribution[0]

        # Get keywords for the best topic
        topic_terms = self.lda_model.show_topic(best_topic_id, topn=num_keywords)
        keywords = [term for term, _ in topic_terms]

        return {
            "topic_id": int(best_topic_id),
            "topic_label": self._get_topic_label(best_topic_id, keywords),
            "keywords": keywords,
            "probability": round(float(best_prob), 4),
            "all_topics": [
                {"topic_id": int(tid), "probability": round(float(prob), 4)}
                for tid, prob in topic_distribution
            ],
            "method": "lda",
        }

    def _lda_batch_extract(
        self, texts: List[str], num_keywords: int
    ) -> Dict[str, Any]:
        """Extract topics using LDA for a batch of documents."""
        document_topics = []
        topic_doc_counts: Dict[int, int] = {}

        for idx, text in enumerate(texts):
            tokens = self._preprocess(text)
            if not tokens:
                continue

            bow = self.dictionary.doc2bow(tokens)
            if not bow:
                continue

            topic_dist = self.lda_model.get_document_topics(bow, minimum_probability=0.0)
            if not topic_dist:
                continue

            topic_dist.sort(key=lambda x: x[1], reverse=True)
            best_topic_id, best_prob = topic_dist[0]

            document_topics.append({
                "doc_idx": idx,
                "topic_id": int(best_topic_id),
                "probability": round(float(best_prob), 4),
            })

            topic_doc_counts[best_topic_id] = topic_doc_counts.get(best_topic_id, 0) + 1

        # Build topic summaries
        topics = []
        for topic_id in range(self.num_topics):
            topic_terms = self.lda_model.show_topic(topic_id, topn=num_keywords)
            keywords = [term for term, _ in topic_terms]

            topics.append({
                "id": topic_id,
                "label": self._get_topic_label(topic_id, keywords),
                "keywords": keywords,
                "doc_count": topic_doc_counts.get(topic_id, 0),
                "percentage": round(
                    topic_doc_counts.get(topic_id, 0) / max(1, len(texts)) * 100, 1
                ),
            })

        # Sort topics by document count descending
        topics.sort(key=lambda t: t["doc_count"], reverse=True)

        return {
            "topics": topics,
            "document_topics": document_topics,
            "method": "lda",
        }

    # ------------------------------------------------------------------ #
    #  Keyword-based fallback extraction                                 #
    # ------------------------------------------------------------------ #

    def _keyword_extraction_with_label(
        self, text: str, num_keywords: int
    ) -> Dict[str, Any]:
        """Extract keywords and assign a topic label using frequency + category matching."""
        keywords = self._keyword_extraction(text, num_keywords)
        label = self._assign_topic_label(keywords)

        return {
            "topic_id": -1,
            "topic_label": label,
            "keywords": keywords,
            "probability": round(self._estimate_keyword_confidence(keywords), 4),
            "method": "keyword",
        }

    def _keyword_extraction(self, text: str, num_keywords: int = 5) -> List[str]:
        """Extract top keywords from text using TF-based frequency analysis.

        Scores words by their normalized frequency, penalizing short words
        and stopwords.  Returns the highest-scoring unique keywords.

        Parameters
        ----------
        text : str
            Cleaned text.
        num_keywords : int
            Number of keywords to return.

        Returns
        -------
        list[str]
            Top keywords sorted by score descending.
        """
        words = self._token_re.findall(text.lower())

        # Remove stopwords and short tokens
        content_words = [
            w for w in words
            if w not in self._stopwords and len(w) >= 3
        ]

        if not content_words:
            return []

        # Calculate word frequencies
        word_counts = Counter(content_words)
        total_words = len(content_words)

        # Score each word: normalized frequency * length bonus
        word_scores: Dict[str, float] = {}
        for word, count in word_counts.items():
            # TF component: count / total
            tf = count / total_words

            # Length bonus: longer words tend to be more informative
            length_bonus = min(1.0, len(word) / 10.0)

            # Position bonus: words appearing in first 20% of text
            first_portion = text.lower()[: max(1, len(text) // 5)]
            position_bonus = 1.2 if word in first_portion else 1.0

            # Combined score
            word_scores[word] = tf * (1.0 + length_bonus) * position_bonus

        # Sort by score descending
        sorted_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:num_keywords]]

    def _keyword_batch_extract(
        self, texts: List[str], num_keywords: int
    ) -> Dict[str, Any]:
        """Keyword-based topic extraction for a batch of documents."""
        # Aggregate all keyword counts across documents
        all_keywords: Counter = Counter()
        doc_keywords: List[List[str]] = []

        for text in texts:
            keywords = self._keyword_extraction(text, num_keywords)
            doc_keywords.append(keywords)
            all_keywords.update(keywords)

        # Determine dominant topic clusters from aggregated keywords
        top_keywords = [kw for kw, _ in all_keywords.most_common(num_keywords * 3)]
        global_label = self._assign_topic_label(top_keywords)

        # Build topic clusters by grouping documents that share keywords
        doc_groups: Dict[str, List[int]] = {}
        for idx, keywords in enumerate(doc_keywords):
            if not keywords:
                label = "Other"
            else:
                label = self._assign_topic_label(keywords)
            if label not in doc_groups:
                doc_groups[label] = []
            doc_groups[label].append(idx)

        topics = []
        for label, doc_indices in sorted(
            doc_groups.items(), key=lambda x: len(x[1]), reverse=True
        ):
            # Aggregate keywords for documents in this group
            group_keywords: Counter = Counter()
            for i in doc_indices:
                group_keywords.update(doc_keywords[i])

            topics.append({
                "id": len(topics),
                "label": label,
                "keywords": [kw for kw, _ in group_keywords.most_common(num_keywords)],
                "doc_count": len(doc_indices),
                "percentage": round(len(doc_indices) / max(1, len(texts)) * 100, 1),
            })

        document_topics = [
            {"doc_idx": idx, "topic_label": self._assign_topic_label(kws) if kws else "Other"}
            for idx, kws in enumerate(doc_keywords)
        ]

        return {
            "topics": topics,
            "document_topics": document_topics,
            "method": "keyword",
        }

    # ------------------------------------------------------------------ #
    #  Helper methods                                                     #
    # ------------------------------------------------------------------ #

    def _preprocess(self, text: str) -> List[str]:
        """Tokenize and preprocess text for topic modeling.

        Performs: lowercasing, stopword removal, short-token filtering,
        and basic lemmatization using word endings.

        Parameters
        ----------
        text : str
            Raw or cleaned text.

        Returns
        -------
        list[str]
            List of preprocessed tokens.
        """
        if not text:
            return []

        text_lower = text.lower()
        tokens = self._token_re.findall(text_lower)

        # Remove stopwords and short tokens
        filtered = [t for t in tokens if t not in self._stopwords and len(t) >= 3]

        # Basic suffix-stripping lemmatization (no NLTK dependency)
        lemmatized = [self._simple_lemmatize(t) for t in filtered]
        return [t for t in lemmatized if t and len(t) >= 3]

    @staticmethod
    def _simple_lemmatize(word: str) -> str:
        """Basic morphological reduction using common English suffixes.

        Handles: -ing, -ed, -tion, -ment, -ness, -ly, -er, -est, -s, -es
        """
        if len(word) <= 4:
            return word

        # Handle -ing forms
        if word.endswith("ing"):
            base = word[:-3]
            if len(base) >= 3:
                # Handle doubling: running -> run, getting -> get
                if len(base) >= 2 and base[-1] == base[-2]:
                    return base[:-1]
                return base
            return word

        # Handle -tion -> remove just -ion for common words
        if word.endswith("ation"):
            base = word[:-5]
            if len(base) >= 3:
                if base.endswith("ic"):
                    return base
                return base + "ate" if len(base) >= 3 else base
            return word

        if word.endswith("tion"):
            base = word[:-4]
            if len(base) >= 3:
                return base
            return word

        if word.endswith("sion"):
            base = word[:-4]
            if len(base) >= 3:
                return base
            return word

        # Handle -ment
        if word.endswith("ment") and len(word) > 5:
            return word[:-4]

        # Handle -ness
        if word.endswith("ness") and len(word) > 5:
            base = word[:-4]
            return base

        # Handle -ly
        if word.endswith("ly") and len(word) > 4:
            base = word[:-2]
            if base.endswith("ab") or base.endswith("ib"):
                return base[:-1] + "le"
            return base

        # Handle -er (comparative and agent)
        if word.endswith("er") and len(word) > 4:
            base = word[:-2]
            if len(base) >= 2 and base[-1] == base[-2]:
                return base[:-1]
            return base

        # Handle -est
        if word.endswith("est") and len(word) > 5:
            base = word[:-3]
            if len(base) >= 2 and base[-1] == base[-2]:
                return base[:-1]
            return base

        # Handle -ed
        if word.endswith("ed") and len(word) > 4:
            base = word[:-2]
            if len(base) >= 2 and base[-1] == base[-2]:
                return base[:-1]
            return base

        # Handle -es
        if word.endswith("es") and len(word) > 4:
            base = word[:-2]
            if base.endswith("s") or base.endswith("z") or base.endswith("h"):
                return base
            if base.endswith("i"):
                return base[:-1] + "y"
            return base

        # Handle -s (plural)
        if word.endswith("s") and not word.endswith("ss") and len(word) > 4:
            base = word[:-1]
            if base.endswith("i"):
                return base[:-1] + "y"
            return base

        return word

    def _get_topic_label(self, topic_id: int, keywords: List[str]) -> str:
        """Generate a human-readable label for a topic from its keywords.

        Matches topic keywords against known label categories and picks
        the best match.  Falls back to joining top keywords.

        Parameters
        ----------
        topic_id : int
            LDA topic index.
        keywords : list[str]
            Top keywords for this topic.

        Returns
        -------
        str
            Human-readable topic label.
        """
        if not keywords:
            return f"Topic {topic_id}"

        keywords_lower = [kw.lower() for kw in keywords]

        # Score each label candidate by overlap with topic keywords
        best_label = "General"
        best_score = 0.0

        for label, label_keywords in _TOPIC_LABEL_MAP.items():
            overlap = set(keywords_lower) & set(label_keywords)
            if overlap:
                score = len(overlap) / len(label_keywords)
                if score > best_score:
                    best_score = score
                    # Convert snake_case to Title Case
                    best_label = label.replace("_", " ").title()

        if best_score < 0.15:
            # Not enough overlap — use keywords as label
            best_label = ", ".join(keywords[:3])

        return best_label

    def _assign_topic_label(self, keywords: List[str]) -> str:
        """Assign a topic label based on extracted keywords.

        Similar to _get_topic_label but without a topic_id parameter,
        used for keyword-based fallback analysis.
        """
        if not keywords:
            return "Other"

        return self._get_topic_label(0, keywords)

    def _estimate_keyword_confidence(self, keywords: List[str]) -> float:
        """Estimate confidence for keyword-based extraction.

        Higher confidence when keywords match known topic patterns well.
        """
        if not keywords:
            return 0.0

        keywords_set = set(kw.lower() for kw in keywords)

        # Check overlap with all topic label maps
        max_overlap = 0
        total_patterns = 0

        for label_keywords in _TOPIC_LABEL_MAP.values():
            total_patterns += len(label_keywords)
            overlap = len(keywords_set & set(label_keywords))
            if overlap > max_overlap:
                max_overlap = overlap

        if total_patterns == 0:
            return 0.3

        # Base confidence: 0.3 to 0.9 depending on keyword quality
        base = 0.3 + (max_overlap / max(1, len(keywords))) * 0.5
        # Bonus for having more keywords
        quantity_bonus = min(0.1, len(keywords) * 0.02)

        return min(0.95, base + quantity_bonus)

    def _compute_coherence(self, tokenized_docs: List[List[str]]) -> float:
        """Compute a simple coherence score for the trained topics."""
        try:
            from gensim.models import CoherenceModel
            coherence_model = CoherenceModel(
                model=self.lda_model,
                texts=tokenized_docs,
                dictionary=self.dictionary,
                coherence="c_v",
            )
            return round(float(coherence_model.get_coherence()), 4)
        except Exception as exc:
            logger.debug("Could not compute coherence: %s", exc)
            return 0.0

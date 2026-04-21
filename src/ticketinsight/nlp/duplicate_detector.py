"""
Duplicate detection module for TicketInsight Pro.

Detects duplicate or near-duplicate tickets using TF-IDF vectorization
and cosine similarity.  Supports both batch comparison and single-ticket
checking against existing ticket pools.

Usage
-----
    from ticketinsight.nlp.duplicate_detector import DuplicateDetector
    detector = DuplicateDetector(config)
    dupes = detector.find_duplicates(texts, ticket_ids)
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.duplicate_detector")


class DuplicateDetector:
    """Detect duplicate tickets using text similarity analysis.

    Combines TF-IDF vectorization with cosine similarity to identify
    tickets that describe the same or very similar issues.  Includes
    text preprocessing that removes noise (ticket IDs, dates, error codes)
    to focus on semantic content.
    """

    def __init__(self, config: Any = None):
        self.config = config
        self.vectorizer = None
        self.similarity_matrix = None
        self.tfidf_matrix = None
        self.threshold = 0.85

        # Read config
        if config is not None:
            try:
                self.threshold = float(config.get("nlp", "duplicate_threshold", 0.85))
            except (ValueError, TypeError):
                self.threshold = 0.85

        # Pre-compile regex patterns for text cleaning
        self._ticket_id_re = re.compile(
            r"\b(?:INC|REQ|TKT|CHG|TASK|PRB|RFQ|RITM|SCTASK)"
            r"\d{6,}\b",
            re.IGNORECASE,
        )
        self._ip_address_re = re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        )
        self._date_re = re.compile(
            r"\b\d{4}[-/]\d{2}[-/]\d{2}\b"
            r"|\b\d{2}[-/]\d{2}[-/]\d{2,4}\b"
            r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}\b",
            re.IGNORECASE,
        )
        self._error_code_re = re.compile(
            r"\b0x[0-9A-Fa-f]{4,16}\b"
            r"|\bERR_[A-Z_]+\b"
            r"|\b(?:HTTP|HTTP/)\d{3}\b"
            r"|\b(?:win|nt|dns|kerberos|ldap|rpc)_error_[0-9a-fx]+\b",
            re.IGNORECASE,
        )
        self._hex_code_re = re.compile(
            r"\b[0-9A-Fa-f]{8,}\b"
        )
        self._email_re = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        )
        self._url_re = re.compile(
            r"https?://\S+|www\.\S+\.\S+"
        )
        self._guid_re = re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        )
        self._file_path_re = re.compile(
            r"(?:[A-Z]:\\|/)(?:[\w\s.-]+\\?)+",
            re.IGNORECASE,
        )
        self._unc_path_re = re.compile(
            r"\\\\[\w.-]+(?:\\[\w\s.-]+)+"
        )

        logger.info("DuplicateDetector initialized (threshold=%.2f)", self.threshold)

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def find_duplicates(
        self,
        texts: List[str],
        ticket_ids: Optional[List[str]] = None,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Find duplicate tickets in a list.

        Computes pairwise cosine similarity between all ticket texts and
        returns pairs whose similarity exceeds the threshold.

        Parameters
        ----------
        texts : list[str]
            List of ticket texts (title + description).
        ticket_ids : list[str], optional
            Corresponding ticket IDs.  If None, indices are used.
        threshold : float, optional
            Similarity threshold.  Defaults to instance setting.

        Returns
        -------
        list[dict]
            List of duplicate pairs sorted by similarity descending:
            ``[{ticket_id, duplicate_id, similarity_score, matched_fields}, ...]``
        """
        if not texts or len(texts) < 2:
            return []

        threshold = threshold if threshold is not None else self.threshold

        # Preprocess texts for comparison
        processed = [self._preprocess_for_comparison(t) for t in texts]

        # Filter out empty texts
        valid_indices = [i for i, p in enumerate(processed) if p and len(p) > 10]
        if len(valid_indices) < 2:
            return []

        valid_texts = [processed[i] for i in valid_indices]

        # Vectorize using TF-IDF
        tfidf_matrix = self._vectorize(valid_texts)
        if tfidf_matrix is None:
            return []

        # Compute cosine similarity matrix
        similarity_matrix = self._cosine_similarity_matrix(tfidf_matrix)

        # Find pairs above threshold
        duplicates = []
        n = len(valid_indices)

        for i in range(n):
            for j in range(i + 1, n):
                score = similarity_matrix[i][j]
                if score >= threshold:
                    orig_i = valid_indices[i]
                    orig_j = valid_indices[j]

                    ticket_id_i = ticket_ids[orig_i] if ticket_ids and orig_i < len(ticket_ids) else str(orig_i)
                    ticket_id_j = ticket_ids[orig_j] if ticket_ids and orig_j < len(ticket_ids) else str(orig_j)

                    # Identify which text fields contributed to the match
                    matched = self._identify_matched_fields(
                        texts[orig_i], texts[orig_j]
                    )

                    duplicates.append({
                        "ticket_id": ticket_id_i,
                        "duplicate_id": ticket_id_j,
                        "similarity_score": round(float(score), 4),
                        "matched_fields": matched,
                    })

        # Sort by similarity score descending
        duplicates.sort(key=lambda x: x["similarity_score"], reverse=True)

        logger.info(
            "Found %d duplicate pairs among %d tickets (threshold=%.2f)",
            len(duplicates),
            len(texts),
            threshold,
        )
        return duplicates

    def check_duplicate(
        self,
        new_text: str,
        existing_texts: List[str],
        existing_ids: Optional[List[str]] = None,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Check if a new ticket is a duplicate of existing ones.

        Compares a single new ticket against all existing tickets and
        returns the best match if any exceed the similarity threshold.

        Parameters
        ----------
        new_text : str
            New ticket text.
        existing_texts : list[str]
            Existing ticket texts to compare against.
        existing_ids : list[str], optional
            IDs of existing tickets.
        threshold : float, optional
            Similarity threshold.

        Returns
        -------
        dict
            ``{
                "is_duplicate": bool,
                "best_match_id": str,
                "best_match_score": float,
                "top_matches": [{id, score}, ...]
            }``
        """
        if not new_text or not existing_texts:
            return {
                "is_duplicate": False,
                "best_match_id": None,
                "best_match_score": 0.0,
                "top_matches": [],
            }

        threshold = threshold if threshold is not None else self.threshold

        new_processed = self._preprocess_for_comparison(new_text)
        if not new_processed or len(new_processed) < 10:
            return {
                "is_duplicate": False,
                "best_match_id": None,
                "best_match_score": 0.0,
                "top_matches": [],
            }

        existing_processed = [
            self._preprocess_for_comparison(t) for t in existing_texts
        ]

        # Filter empty existing texts
        valid_indices = [i for i, p in enumerate(existing_processed) if p and len(p) > 10]
        if not valid_indices:
            return {
                "is_duplicate": False,
                "best_match_id": None,
                "best_match_score": 0.0,
                "top_matches": [],
            }

        valid_existing = [existing_processed[i] for i in valid_indices]

        # Vectorize all texts together
        all_texts = [new_processed] + valid_existing
        tfidf_matrix = self._vectorize(all_texts)
        if tfidf_matrix is None:
            return {
                "is_duplicate": False,
                "best_match_id": None,
                "best_match_score": 0.0,
                "top_matches": [],
            }

        # Compute similarity between new text (index 0) and all existing
        from sklearn.metrics.pairwise import cosine_similarity
        new_vector = tfidf_matrix[0:1]
        existing_vectors = tfidf_matrix[1:]
        similarities = cosine_similarity(new_vector, existing_vectors)[0]

        # Build top matches
        top_matches = []
        for idx, score in enumerate(similarities):
            orig_idx = valid_indices[idx]
            ticket_id = (
                existing_ids[orig_idx]
                if existing_ids and orig_idx < len(existing_ids)
                else str(orig_idx)
            )
            top_matches.append({
                "id": ticket_id,
                "score": round(float(score), 4),
            })

        # Sort by score descending
        top_matches.sort(key=lambda x: x["score"], reverse=True)

        # Filter to threshold
        above_threshold = [m for m in top_matches if m["score"] >= threshold]

        is_duplicate = len(above_threshold) > 0
        best_match = above_threshold[0] if above_threshold else None

        result = {
            "is_duplicate": is_duplicate,
            "best_match_id": best_match["id"] if best_match else None,
            "best_match_score": best_match["score"] if best_match else 0.0,
            "top_matches": top_matches[:10],  # Return top 10
        }

        logger.info(
            "Duplicate check: is_duplicate=%s, best_score=%.4f, checked=%d",
            result["is_duplicate"],
            result["best_match_score"],
            len(existing_texts),
        )
        return result

    # ------------------------------------------------------------------ #
    #  Text preprocessing                                                 #
    # ------------------------------------------------------------------ #

    def _preprocess_for_comparison(self, text: str) -> str:
        """Preprocess text specifically for duplicate detection.

        Removes noise that doesn't contribute to semantic similarity:
        ticket IDs, error codes, dates, IP addresses, email addresses,
        URLs, file paths, and GUIDs.  Keeps the core issue description.

        Parameters
        ----------
        text : str
            Raw ticket text.

        Returns
        -------
        str
            Cleaned text suitable for TF-IDF comparison.
        """
        if not text or not isinstance(text, str):
            return ""

        cleaned = sanitize_text(text)

        # Remove ticket reference IDs (but keep the word "ticket")
        cleaned = self._ticket_id_re.sub(" ", cleaned)

        # Remove IP addresses
        cleaned = self._ip_address_re.sub(" ", cleaned)

        # Remove dates
        cleaned = self._date_re.sub(" ", cleaned)

        # Remove error codes
        cleaned = self._error_code_re.sub(" ", cleaned)

        # Remove long hex codes
        cleaned = self._hex_code_re.sub(" ", cleaned)

        # Remove email addresses (keep domain for context)
        cleaned = self._email_re.sub(" ", cleaned)

        # Remove URLs
        cleaned = self._url_re.sub(" ", cleaned)

        # Remove GUIDs
        cleaned = self._guid_re.sub(" ", cleaned)

        # Remove file paths
        cleaned = self._file_path_re.sub(" ", cleaned)
        cleaned = self._unc_path_re.sub(" ", cleaned)

        # Remove usernames (pattern: first.last or first_lastname)
        cleaned = re.sub(r"\b[a-z]+\.[a-z_]+\b", " ", cleaned, flags=re.IGNORECASE)

        # Remove extra whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    def _identify_matched_fields(
        self, text1: str, text2: str
    ) -> Dict[str, float]:
        """Identify which aspects of two texts contributed to the similarity.

        Compares title-like portions and description-like portions separately
        to give insight into what parts matched.

        Parameters
        ----------
        text1 : str
            First ticket text.
        text2 : str
            Second ticket text.

        Returns
        -------
        dict
            Similarity breakdown: ``{"title_similarity": float, "description_similarity": float}``
        """
        # Split into title (first line/sentence) and description (rest)
        title1, desc1 = self._split_title_description(text1)
        title2, desc2 = self._split_title_description(text2)

        result = {}

        # Compare titles
        if title1 and title2:
            result["title_similarity"] = round(self._quick_similarity(title1, title2), 4)
        else:
            result["title_similarity"] = 0.0

        # Compare descriptions
        if desc1 and desc2:
            result["description_similarity"] = round(self._quick_similarity(desc1, desc2), 4)
        else:
            result["description_similarity"] = 0.0

        return result

    @staticmethod
    def _split_title_description(text: str) -> Tuple[str, str]:
        """Split text into title (first sentence) and description (rest)."""
        if not text:
            return "", ""

        # Split on first newline, period followed by space, or first 100 chars
        parts = re.split(r"\n|\.\s+|!\s+|\?\s+", text, maxsplit=1)

        title = parts[0].strip() if parts else ""
        description = parts[1].strip() if len(parts) > 1 else ""

        return title, description

    def _quick_similarity(self, text1: str, text2: str) -> float:
        """Quick cosine similarity between two short texts using TF-IDF."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity as cs

            vectorizer = TfidfVectorizer(
                max_features=500,
                ngram_range=(1, 2),
                stop_words="english",
            )
            tfidf = vectorizer.fit_transform([text1, text2])
            return float(cs(tfidf[0:1], tfidf[1:2])[0][0])
        except Exception:
            # Fallback: Jaccard similarity on word sets
            words1 = set(text1.lower().split())
            words2 = set(text2.lower().split())
            if not words1 or not words2:
                return 0.0
            intersection = words1 & words2
            union = words1 | words2
            return len(intersection) / len(union)

    # ------------------------------------------------------------------ #
    #  Vectorization and similarity                                       #
    # ------------------------------------------------------------------ #

    def _vectorize(self, texts: List[str]):
        """Vectorize a list of texts using TF-IDF.

        Returns a sparse TF-IDF matrix, or None on failure.
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            if self.vectorizer is None:
                self.vectorizer = TfidfVectorizer(
                    max_features=5000,
                    ngram_range=(1, 2),
                    stop_words="english",
                    sublinear_tf=True,
                    min_df=1,
                    max_df=0.95,
                    analyzer="word",
                )
                self.tfidf_matrix = self.vectorizer.fit_transform(texts)
            else:
                self.tfidf_matrix = self.vectorizer.transform(texts)

            return self.tfidf_matrix
        except Exception as exc:
            logger.error("TF-IDF vectorization failed: %s", exc)
            return None

    def _cosine_similarity_matrix(self, tfidf_matrix) -> List[List[float]]:
        """Compute full pairwise cosine similarity matrix.

        Parameters
        ----------
        tfidf_matrix
            SciPy sparse TF-IDF matrix.

        Returns
        -------
        list[list[float]]
            Dense similarity matrix.
        """
        from sklearn.metrics.pairwise import cosine_similarity

        sim_matrix = cosine_similarity(tfidf_matrix, dense_output=False)
        # Convert to dense numpy array then to list of lists
        dense_matrix = sim_matrix.toarray()
        return dense_matrix.tolist()

"""
Named Entity Recognition module for TicketInsight Pro.

Extracts named entities from IT ticket text using spaCy for standard
entities (PERSON, ORG, GPE, DATE, etc.) plus comprehensive regex-based
patterns for IT-specific entities (IP addresses, error codes, URLs,
file paths, software/hardware names).

Usage
-----
    from ticketinsight.nlp.ner_extractor import NERExtractor
    extractor = NERExtractor(config)
    result = extractor.extract("User john.doe at 192.168.1.1 got error 0x80070005")
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.ner_extractor")


class NERExtractor:
    """Named Entity Recognition for IT ticket entities.

    Combines spaCy's built-in NER pipeline with custom regex patterns
    for IT-specific entity types not covered by standard NER models.
    """

    def __init__(self, config: Any = None):
        self.config = config
        self.nlp = None
        self.model_name = "en_core_web_sm"
        self._model_loaded = False

        if config is not None:
            try:
                self.model_name = config.get("nlp", "model", "en_core_web_sm")
            except Exception:
                pass

        # Pre-compile all regex patterns for IT-specific entities
        self._ip_pattern = re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        )

        self._email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        )

        self._error_code_pattern = re.compile(
            r"\b0x[0-9A-Fa-f]{4,16}\b"
            r"|\bERR_[A-Z_0-9]+\b"
            r"|\b(?:HTTP|HTTP/)\d{3}\b"
            r"|\bNTSTATUS\s+0x[0-9A-Fa-f]+\b"
            r"|\bWIN\d+\b"
            r"|\b(?:win|nt|dns|kerberos|ldap|rpc|dhcp|tcp|ip)_error_[0-9a-fx]+\b"
            r"|\bE[A-Z]{3,5}\d{3,6}\b"
            r"|\bORA-\d{5}\b"
            r"|\b(?:MySQL|PostgreSQL|SQL|Oracle|DB2) error \d+\b",
            re.IGNORECASE,
        )

        self._url_pattern = re.compile(
            r"https?://[^\s<>\"')\]]+"
            r"|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}[^\s<>\"')\]]*"
        )

        self._file_path_pattern = re.compile(
            r"(?:[A-Z]:\\[^\s:<>\"|?*]+)"
            r"|(?:/[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*)"
            r"|(?:\\\\[A-Za-z0-9.-]+(?:\\[A-Za-z0-9_.\s-]+)*)",
        )

        self._mac_address_pattern = re.compile(
            r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"
        )

        self._serial_number_pattern = re.compile(
            r"\b(?:SN|S/N|Serial)[\s:]?\s*[A-Z0-9-]{6,20}\b",
            re.IGNORECASE,
        )

        self._phone_pattern = re.compile(
            r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
        )

        self._version_pattern = re.compile(
            r"\b(?:v|version|ver)[\s.]?\s?\d+(?:\.\d+){1,4}\b",
            re.IGNORECASE,
        )

        # Build software/hardware dictionaries
        self._software_dict = self._get_software_dict()
        self._hardware_dict = self._get_hardware_dict()

        logger.info("NERExtractor initialized (model=%s)", self.model_name)

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def load_model(self) -> bool:
        """Load the spaCy NER model, downloading it if not available.

        Returns
        -------
        bool
            True if model loaded successfully.
        """
        if self._model_loaded and self.nlp is not None:
            return True

        try:
            import spacy
            self.nlp = spacy.load(self.model_name)
            self._model_loaded = True
            logger.info("spaCy model '%s' loaded successfully", self.model_name)
            return True
        except OSError:
            logger.info(
                "spaCy model '%s' not found, attempting download...",
                self.model_name,
            )
            try:
                import subprocess
                import sys
                subprocess.run(
                    [sys.executable, "-m", "spacy", "download", self.model_name],
                    capture_output=True,
                    timeout=300,
                    check=True,
                )
                import spacy
                self.nlp = spacy.load(self.model_name)
                self._model_loaded = True
                logger.info("spaCy model '%s' downloaded and loaded", self.model_name)
                return True
            except Exception as download_exc:
                logger.error(
                    "Failed to download spaCy model '%s': %s",
                    self.model_name,
                    download_exc,
                )
                self._model_loaded = False
                return False
        except ImportError:
            logger.error("spaCy not installed; NER will use regex patterns only")
            self._model_loaded = False
            return False

    def extract(self, text: str) -> Dict[str, Any]:
        """Extract named entities from ticket text.

        Uses spaCy for standard entities and regex for IT-specific ones.

        Parameters
        ----------
        text : str
            Ticket text.

        Returns
        -------
        dict
            ``{
                "entities": [{text, label, start, end}, ...],
                "it_specific": {
                    "ip_addresses": [], "email_addresses": [],
                    "error_codes": [], "urls": [], "file_paths": [],
                    "software_names": [], "hardware_names": [],
                    "mac_addresses": [], "version_numbers": [],
                    "serial_numbers": [], "phone_numbers": []
                },
                "entity_summary": str
            }``
        """
        if not text or not isinstance(text, str):
            return {
                "entities": [],
                "it_specific": {
                    "ip_addresses": [],
                    "email_addresses": [],
                    "error_codes": [],
                    "urls": [],
                    "file_paths": [],
                    "software_names": [],
                    "hardware_names": [],
                    "mac_addresses": [],
                    "version_numbers": [],
                    "serial_numbers": [],
                    "phone_numbers": [],
                },
                "entity_summary": "",
            }

        cleaned = sanitize_text(text)

        # Extract spaCy entities
        spacy_entities = self._extract_spacy_entities(cleaned)

        # Extract IT-specific entities
        it_entities = self._extract_it_entities(cleaned)

        # Generate entity summary
        summary = self._generate_entity_summary(spacy_entities, it_entities)

        return {
            "entities": spacy_entities,
            "it_specific": it_entities,
            "entity_summary": summary,
        }

    def extract_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Extract entities from multiple texts.

        Parameters
        ----------
        texts : list[str]
            List of ticket texts.

        Returns
        -------
        list[dict]
            List of entity extraction results.
        """
        if not texts:
            return []

        # Try batch processing with spaCy
        if self.nlp is not None and self._model_loaded:
            try:
                return self._batch_spacy_extract(texts)
            except Exception as exc:
                logger.warning("Batch spaCy extraction failed, falling back to individual: %s", exc)

        results = []
        for text in texts:
            try:
                result = self.extract(text)
            except Exception as exc:
                logger.error("Error extracting entities: %s", exc)
                result = {
                    "entities": [],
                    "it_specific": {
                        "ip_addresses": [],
                        "email_addresses": [],
                        "error_codes": [],
                        "urls": [],
                        "file_paths": [],
                        "software_names": [],
                        "hardware_names": [],
                        "mac_addresses": [],
                        "version_numbers": [],
                        "serial_numbers": [],
                        "phone_numbers": [],
                    },
                    "entity_summary": "",
                    "error": str(exc),
                }
            results.append(result)
        return results

    # ------------------------------------------------------------------ #
    #  spaCy entity extraction                                            #
    # ------------------------------------------------------------------ #

    def _extract_spacy_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract standard named entities using spaCy.

        Returns entities of types: PERSON, ORG, GPE, DATE, TIME, MONEY,
        PERCENT, PRODUCT, EVENT, WORK_OF_ART, FAC, NORP, LOC, LAW, LANGUAGE.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        list[dict]
            List of entities: ``[{text, label, start, end}, ...]``
        """
        if not self._model_loaded or self.nlp is None:
            self.load_model()

        if not self._model_loaded or self.nlp is None:
            return []

        try:
            doc = self.nlp(text)
            entities = []
            for ent in doc.ents:
                entities.append({
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                })
            return entities
        except Exception as exc:
            logger.warning("spaCy entity extraction failed: %s", exc)
            return []

    def _batch_spacy_extract(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Extract entities using spaCy's batch processing for efficiency."""
        cleaned_texts = [sanitize_text(t) for t in texts]

        try:
            docs = list(self.nlp.pipe(cleaned_texts, disable=["parser", "tagger"]))

            results = []
            for doc, original_text in zip(docs, texts):
                spacy_entities = []
                for ent in doc.ents:
                    spacy_entities.append({
                        "text": ent.text,
                        "label": ent.label_,
                        "start": ent.start_char,
                        "end": ent.end_char,
                    })

                it_entities = self._extract_it_entities(
                    sanitize_text(original_text)
                )
                summary = self._generate_entity_summary(spacy_entities, it_entities)

                results.append({
                    "entities": spacy_entities,
                    "it_specific": it_entities,
                    "entity_summary": summary,
                })

            return results
        except Exception as exc:
            logger.error("Batch spaCy extraction error: %s", exc)
            raise

    # ------------------------------------------------------------------ #
    #  IT-specific entity extraction                                      #
    # ------------------------------------------------------------------ #

    def _extract_it_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract IT-specific entities using regex patterns.

        Extracts: IP addresses, email addresses, error codes, URLs,
        file paths, software names, hardware names, MAC addresses,
        version numbers, serial numbers, and phone numbers.

        Parameters
        ----------
        text : str
            Cleaned text.

        Returns
        -------
        dict
            Entity type -> list of extracted strings.
        """
        result = {
            "ip_addresses": self._find_unique(self._ip_pattern, text),
            "email_addresses": self._find_unique(self._email_pattern, text),
            "error_codes": self._find_unique(self._error_code_pattern, text),
            "urls": self._find_unique(self._url_pattern, text),
            "file_paths": self._find_unique(self._file_path_pattern, text),
            "software_names": self._find_software_names(text),
            "hardware_names": self._find_hardware_names(text),
            "mac_addresses": self._find_unique(self._mac_address_pattern, text),
            "version_numbers": self._find_unique(self._version_pattern, text),
            "serial_numbers": self._find_unique(self._serial_number_pattern, text),
            "phone_numbers": self._find_unique(self._phone_pattern, text),
        }
        return result

    @staticmethod
    def _find_unique(pattern: re.Pattern, text: str) -> List[str]:
        """Find all unique matches of a regex pattern in text."""
        matches = pattern.findall(text)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            match_str = match.strip()
            if match_str and match_str not in seen:
                seen.add(match_str)
                unique.append(match_str)
        return unique

    def _find_software_names(self, text: str) -> List[str]:
        """Find known software names in text."""
        text_lower = text.lower()
        found = []
        seen = set()

        for software in self._software_dict:
            sw_lower = software.lower()
            if sw_lower in text_lower and sw_lower not in seen:
                # Ensure we match whole words or well-known product names
                # Check for word boundary match
                pattern = re.compile(r"\b" + re.escape(sw_lower) + r"\b", re.IGNORECASE)
                if pattern.search(text):
                    seen.add(sw_lower)
                    found.append(software)

        return found

    def _find_hardware_names(self, text: str) -> List[str]:
        """Find known hardware names in text."""
        text_lower = text.lower()
        found = []
        seen = set()

        for hardware in self._hardware_dict:
            hw_lower = hardware.lower()
            if hw_lower in text_lower and hw_lower not in seen:
                pattern = re.compile(r"\b" + re.escape(hw_lower) + r"\b", re.IGNORECASE)
                if pattern.search(text):
                    seen.add(hw_lower)
                    found.append(hardware)

        return found

    # ------------------------------------------------------------------ #
    #  Entity summary generation                                          #
    # ------------------------------------------------------------------ #

    def _generate_entity_summary(
        self,
        spacy_entities: List[Dict[str, Any]],
        it_entities: Dict[str, List[str]],
    ) -> str:
        """Generate a human-readable summary of extracted entities.

        Parameters
        ----------
        spacy_entities : list[dict]
            spaCy-extracted entities.
        it_entities : dict
            IT-specific entities.

        Returns
        -------
        str
            Natural language summary of key entities found.
        """
        parts = []

        # Summarize people
        people = [e["text"] for e in spacy_entities if e["label"] == "PERSON"]
        if people:
            unique_people = list(dict.fromkeys(people))[:5]
            if len(unique_people) == 1:
                parts.append(f"Mentions person: {unique_people[0]}")
            else:
                parts.append(f"Mentions {len(unique_people)} people: {', '.join(unique_people[:5])}")

        # Summarize organizations
        orgs = [e["text"] for e in spacy_entities if e["label"] == "ORG"]
        if orgs:
            unique_orgs = list(dict.fromkeys(orgs))[:5]
            parts.append(f"Organizations: {', '.join(unique_orgs)}")

        # Summarize dates
        dates = [e["text"] for e in spacy_entities if e["label"] == "DATE"]
        if dates:
            unique_dates = list(dict.fromkeys(dates))[:3]
            parts.append(f"Dates mentioned: {', '.join(unique_dates)}")

        # Summarize IT entities
        if it_entities.get("ip_addresses"):
            parts.append(f"IP addresses: {', '.join(it_entities['ip_addresses'][:3])}")

        if it_entities.get("error_codes"):
            parts.append(f"Error codes: {', '.join(it_entities['error_codes'][:3])}")

        if it_entities.get("software_names"):
            parts.append(f"Software: {', '.join(it_entities['software_names'][:5])}")

        if it_entities.get("hardware_names"):
            parts.append(f"Hardware: {', '.join(it_entities['hardware_names'][:5])}")

        if it_entities.get("file_paths"):
            parts.append(f"File paths referenced: {len(it_entities['file_paths'])}")

        if not parts:
            return "No significant entities extracted."

        return ". ".join(parts) + "."

    # ------------------------------------------------------------------ #
    #  Dictionaries                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_software_dict() -> Set[str]:
        """Return set of known software/application names.

        Covers ~60 common enterprise software products.
        """
        return {
            # Operating Systems
            "Windows", "Windows 10", "Windows 11", "macOS", "Linux",
            "Ubuntu", "CentOS", "Red Hat", "Debian", "Fedora",
            # Office / Productivity
            "Microsoft Office", "Office 365", "Microsoft 365",
            "Outlook", "Excel", "Word", "PowerPoint", "Access",
            "SharePoint", "OneDrive", "Teams",
            "Google Workspace", "Gmail", "Google Drive",
            "Docs", "Sheets", "Slides",
            # Communication
            "Slack", "Zoom", "Webex", "Skype", "Microsoft Teams",
            "Discord", "Cisco Jabber",
            # Development
            "Python", "Java", "JavaScript", "Node.js", "Docker",
            "Git", "GitHub", "GitLab", "Bitbucket",
            "Visual Studio", "VS Code", "IntelliJ", "Eclipse",
            "Jira", "Confluence", "Terraform", "Ansible",
            # Databases
            "SQL Server", "MySQL", "PostgreSQL", "Oracle",
            "MongoDB", "Redis", "SQLite", "DynamoDB",
            # Security
            "CrowdStrike", "Symantec", "McAfee", "Norton",
            "Kaspersky", "SentinelOne", "Carbon Black",
            "LastPass", "Okta", "Duo",
            # Enterprise Apps
            "Salesforce", "SAP", "ServiceNow", "Zendesk",
            "Workday", "BambooHR", "Oracle EBS",
            "Adobe Creative Suite", "Photoshop", "Illustrator",
            # Browsers
            "Chrome", "Firefox", "Edge", "Safari", "Internet Explorer",
            # VPN
            "Cisco AnyConnect", "GlobalProtect", "OpenVPN",
            "WireGuard", "FortiClient",
            # Cloud Platforms
            "AWS", "Azure", "Google Cloud", "GCP",
            "EC2", "S3", "Lambda",
            # Virtualization
            "VMware", "VirtualBox", "Hyper-V", "Parallels",
        }

    @staticmethod
    def _get_hardware_dict() -> Set[str]:
        """Return set of known hardware names.

        Covers ~35 common hardware items.
        """
        return {
            # Devices
            "laptop", "desktop", "workstation", "tablet", "smartphone",
            "server", "mainframe", "thin client",
            # Peripherals
            "monitor", "keyboard", "mouse", "trackpad", "touchpad",
            "webcam", "headset", "headphone", "speaker", "microphone",
            "scanner", "projector",
            # Networking
            "router", "switch", "firewall", "access point",
            "modem", "hub", "bridge", "repeater",
            "ethernet cable", "network cable",
            # Printing
            "printer", "scanner", "copier", "fax machine", "plotter",
            # Storage
            "hard drive", "SSD", "HDD", "USB drive", "flash drive",
            "external drive", "NAS",
            # Components
            "RAM", "CPU", "GPU", "motherboard", "power supply",
            "battery", "fan", "heatsink", "SSD",
            # docks
            "docking station", "dock", "port replicator", "USB hub",
            # Phones
            "landline", "desk phone", "VoIP phone", "polycom",
            # Other
            "badge reader", "smart card reader",
        }

"""
Ticket classification module for TicketInsight Pro.

Provides multi-label ticket categorization using TF-IDF + SVM with a
comprehensive keyword-based fallback classifier.  Supports both supervised
training on labeled data and zero-shot rule-based classification.

Usage
-----
    from ticketinsight.nlp.classifier import TicketClassifier
    classifier = TicketClassifier(config)
    result = classifier.classify("My laptop screen is flickering")
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ticketinsight.utils.logger import get_logger
from ticketinsight.utils.helpers import sanitize_text

logger = get_logger("nlp.classifier")


class TicketClassifier:
    """Multi-label ticket classification using TF-IDF + SVM/Naive Bayes.

    Falls back to a comprehensive keyword-based classifier when no trained
    model is available, ensuring the system works out-of-the-box without
    any training data.
    """

    # ------------------------------------------------------------------ #
    #  Category definitions with comprehensive keyword dictionaries       #
    # ------------------------------------------------------------------ #
    _KEYWORD_DICTS: Dict[str, List[Tuple[str, float]]] = {
        "Hardware": [
            # Primary hardware terms
            ("laptop", 2.0), ("desktop", 2.0), ("monitor", 2.0), ("printer", 2.0),
            ("keyboard", 2.0), ("mouse", 2.0), ("screen", 1.5), ("display", 1.5),
            ("battery", 2.0), ("ram", 2.0), ("hard drive", 2.0), ("ssd", 2.0),
            ("hdd", 2.0), ("motherboard", 2.5), ("cpu", 2.0), ("processor", 2.0),
            ("gpu", 2.0), ("graphics card", 2.5), ("memory", 1.0), ("disk", 1.5),
            ("usb", 1.0), ("docking station", 2.5), ("docking", 1.5), ("dock", 1.5),
            ("webcam", 2.0), ("camera", 1.0), ("speaker", 1.5), ("headset", 2.0),
            ("headphone", 2.0), ("microphone", 2.0), ("charger", 2.0), ("power cord", 2.5),
            ("adapter", 1.5), ("cable", 1.0), ("hdmi", 2.0), ("vga", 2.0),
            ("displayport", 2.5), ("dvi", 2.0), ("ethernet", 1.5), ("dongle", 2.0),
            # Specific hardware brands/types
            ("dell", 1.5), ("lenovo", 1.5), ("hp ", 1.0), ("thinkpad", 1.5),
            ("latitude", 1.5), ("precision", 1.5), ("optiplex", 1.5),
            ("macbook", 2.0), ("imac", 2.0), ("mac pro", 2.0),
            ("laserjet", 2.5), ("deskjet", 2.5), ("brother", 1.5),
            ("polycom", 2.5), ("logitech", 1.5),
            # Hardware problems
            ("flickering", 2.0), ("broken screen", 3.0), ("dead pixel", 3.0),
            ("overheating", 2.5), ("fan noise", 2.5), ("fan", 1.0),
            ("jammed", 2.0), ("paper jam", 3.0), ("toner", 2.0),
            ("ink", 2.0), ("cartridge", 2.0), ("drum", 2.0),
            ("not powering on", 3.0), ("won't turn on", 3.0), ("won't boot", 3.0),
            ("boot up", 2.0), ("bios", 2.0), ("firmware update", 2.0),
            ("hardware", 2.0), ("device", 1.0), ("workstation", 1.5),
            ("server", 1.0), ("physical", 1.0), ("peripheral", 2.0),
            ("smartphone", 2.0), ("tablet", 2.0), ("phone", 1.0),
            ("replacement", 1.5), ("repair", 1.5), ("swap", 1.5),
            ("dual monitor", 3.0), ("second monitor", 3.0), ("external monitor", 3.0),
            ("resolution", 1.5), ("brightness", 2.0), ("touchpad", 2.5),
            ("trackpad", 2.5), ("click", 1.0), ("scroll", 1.0),
        ],
        "Software": [
            # General software terms
            ("software", 2.0), ("application", 2.0), ("app", 1.0), ("program", 1.5),
            ("install", 2.0), ("uninstall", 2.0), ("installation", 2.0),
            ("update", 1.5), ("upgrade", 1.5), ("patch", 2.0), ("hotfix", 2.5),
            ("version", 1.5), ("compatibility", 2.0), ("incompatible", 2.5),
            ("crash", 2.5), ("freeze", 2.5), ("freezing", 2.5), ("frozen", 2.0),
            ("hang", 2.0), ("hanging", 2.0), ("not responding", 3.0),
            ("error message", 2.5), ("error", 1.0), ("exception", 2.5),
            ("bug", 2.5), ("glitch", 2.5), ("defect", 2.0), ("fault", 2.0),
            ("launch", 1.5), ("startup", 1.5), ("reinstall", 2.0),
            ("roll back", 3.0), ("rollback", 3.0), ("revert", 2.0),
            ("license", 1.0), ("activation", 2.0), ("serial number", 2.5),
            ("plugin", 2.0), ("extension", 1.5), ("add-on", 2.0), ("addon", 2.0),
            ("feature", 1.0), ("setting", 1.0), ("configuration", 1.0),
            ("auto-update", 3.0), ("windows update", 3.0), ("update caused", 3.0),
            ("downtime", 1.5), ("feature request", 2.5), ("enhancement", 2.0),
            ("microsoft", 1.5), ("office", 1.5), ("365", 1.5),
            ("python", 1.5), ("pip install", 3.0), ("package", 1.0),
            ("dependency", 2.0), ("library", 1.5), ("framework", 1.5),
            ("java", 1.5), ("runtime", 2.0), ("environment", 1.0),
            ("executable", 2.0), ("exe", 2.0), ("msi", 2.0),
            ("registry", 2.0), ("dll", 2.5), ("corrupted", 2.0),
            ("corrupt", 2.0), ("reinstalling", 2.0), ("deploy", 1.5),
            ("release", 1.5), ("build", 1.0), ("compile", 1.5),
            ("workspace", 1.5), ("ide", 2.0), ("editor", 1.0),
            ("docker", 1.5), ("container", 1.5), ("kubernetes", 1.5),
        ],
        "Network": [
            # Core network terms
            ("network", 2.0), ("networking", 2.0), ("wifi", 2.5), ("wi-fi", 2.5),
            ("wlan", 2.5), ("wireless", 2.5), ("wired", 2.0),
            ("vpn", 3.0), ("connection", 1.5), ("connectivity", 2.5),
            ("internet", 2.0), ("intranet", 2.5), ("extranet", 2.5),
            ("bandwidth", 2.5), ("throughput", 2.5), ("latency", 2.5),
            ("slow", 1.0), ("speed", 1.0), ("ping", 2.0),
            ("firewall", 2.5), ("router", 2.5), ("switch", 2.0),
            ("access point", 3.0), ("wap", 3.0), ("ap-", 1.5),
            ("dns", 2.5), ("dhcp", 2.5), ("ip address", 2.0), ("ip ", 1.0),
            ("subnet", 2.5), ("gateway", 2.5), ("proxy", 2.0),
            ("port", 1.0), ("vlan", 2.5), ("lan", 2.0), ("wan", 2.0),
            ("packet", 2.0), ("packet loss", 3.0),
            ("disconnect", 2.5), ("disconnection", 2.5), ("dropped", 2.0),
            ("timeout", 2.0), ("intermittent", 2.0), ("unstable", 2.0),
            ("coverage", 2.5), ("signal", 2.0), ("signal strength", 3.0),
            ("ethernet cable", 3.0), ("cat5", 2.0), ("cat6", 2.0),
            ("fiber", 2.0), ("fiber optic", 2.5),
            ("tracert", 2.5), ("traceroute", 2.5), ("nslookup", 2.5),
            ("network drive", 3.0), ("file share", 3.0), ("file sharing", 3.0),
            ("map drive", 2.5), ("mapped drive", 2.5), ("unc path", 3.0),
            ("load balancer", 3.0), ("cdn", 2.5),
            ("conference room", 1.5), ("meeting room", 1.5),
            ("barcode scanner", 2.5), ("warehouse", 1.0),
        ],
        "Access/Permissions": [
            # Authentication & authorization terms
            ("password", 2.5), ("login", 2.5), ("log in", 2.5), ("logon", 2.5),
            ("log on", 2.5), ("sign in", 2.5), ("sign-in", 2.5),
            ("credential", 2.5), ("credentials", 2.5),
            ("authentication", 3.0), ("auth", 1.5), ("mfa", 3.0),
            ("multi-factor", 3.0), ("two-factor", 3.0), ("2fa", 3.0),
            ("sso", 3.0), ("single sign-on", 3.0), ("single sign on", 3.0),
            ("ldap", 3.0), ("active directory", 3.0), ("ad ", 1.5), ("azure ad", 3.0),
            ("account", 1.5), ("locked", 2.5), ("locked out", 3.0), ("lockout", 3.0),
            ("access", 2.0), ("permission", 2.5), ("permissions", 2.5),
            ("denied", 2.5), ("unauthorized", 3.0), ("unauthorised", 3.0),
            ("forbidden", 3.0), ("restricted", 2.5), ("no access", 3.0),
            ("role", 2.0), ("group", 1.5), ("membership", 2.5),
            ("provision", 2.5), ("provisioning", 2.5), ("deprovision", 3.0),
            ("entitlement", 3.0), ("privilege", 3.0), ("rights", 2.0),
            ("security group", 3.0), ("distribution group", 3.0),
            ("reset password", 3.0), ("password reset", 3.0), ("change password", 2.5),
            ("expired", 2.0), ("expire", 2.0), ("expiring", 2.0),
            ("onboarding", 3.0), ("offboarding", 3.0), ("new hire", 3.0),
            ("account setup", 3.0), ("create account", 3.0), ("account creation", 3.0),
            ("badge", 2.5), ("access card", 3.0), ("keycard", 3.0),
            ("sharepoint", 2.5), ("slack", 2.0), ("teams", 1.5),
            ("manager approval", 3.0), ("read-only", 2.5),
            ("identity", 2.0), ("identity verification", 3.0),
        ],
        "Email": [
            # Email-specific terms
            ("email", 2.5), ("e-mail", 2.5), ("mail", 1.5),
            ("outlook", 3.0), ("exchange", 3.0), ("gmail", 3.0),
            ("mailbox", 3.0), ("inbox", 2.5), ("outbox", 2.5),
            ("sent items", 3.0), ("deleted items", 2.5), ("trash", 1.5),
            ("folder", 1.5), ("subfolder", 2.0),
            ("calendar", 2.5), ("meeting", 1.5), ("appointment", 2.0),
            ("attachment", 2.5), ("attachments", 2.5), ("attached", 2.0),
            ("spam", 2.5), ("junk", 2.5), ("junk mail", 3.0),
            ("phishing", 2.5), ("spoof", 2.5), ("spoofed", 2.5),
            ("quota", 3.0), ("storage limit", 3.0), ("mailbox full", 3.0),
            ("over quota", 3.0), ("mailbox size", 3.0),
            ("delegate", 3.0), ("shared mailbox", 3.0), ("shared calendar", 3.0),
            ("distribution list", 3.0), ("mailing list", 3.0),
            ("autoreply", 3.0), ("auto-reply", 3.0), ("out of office", 3.0),
            ("oof", 3.0), ("rules", 2.0), ("email rule", 3.0),
            ("signature", 2.5), ("disclaimer", 2.5),
            ("activesync", 3.0), ("imap", 3.0), ("pop3", 3.0), ("smtp", 3.0),
            ("syncing", 2.5), ("sync", 1.5), ("not syncing", 3.0),
            ("mobile", 1.5), ("iphone", 2.0), ("android", 2.0),
            ("delivery failure", 3.0), ("ndr", 3.0), ("bounce", 2.5),
            ("recipient", 2.0), ("cc", 1.0), ("bcc", 2.0),
            ("encryption", 2.5), ("s/mime", 3.0),
            ("contact", 1.5), ("address book", 3.0), ("contacts", 2.0),
            ("email client", 3.0), ("webmail", 3.0), ("owa", 3.0),
            ("compose", 2.0), ("reply", 1.5), ("forward", 1.5),
        ],
        "Security": [
            # Security-specific terms
            ("security", 2.5), ("malware", 3.0), ("virus", 3.0),
            ("trojan", 3.0), ("ransomware", 3.0), ("spyware", 3.0),
            ("adware", 3.0), ("worm", 3.0), ("rootkit", 3.0),
            ("breach", 3.0), ("data breach", 3.5), ("compromised", 3.0),
            ("vulnerability", 3.0), ("vulnerable", 3.0), ("cve", 3.0),
            ("exploit", 3.0), ("threat", 2.5), ("threats", 2.5),
            ("phishing", 2.5), ("social engineering", 3.0),
            ("suspicious", 2.5), ("suspicious activity", 3.5),
            ("suspicious login", 3.5), ("suspicious email", 3.5),
            ("endpoint", 2.5), ("endpoint protection", 3.5),
            ("antivirus", 3.0), ("anti-virus", 3.0), ("anti-malware", 3.0),
            ("firewall", 1.5), ("ids", 3.0), ("ips", 3.0),
            ("intrusion", 3.0), ("detection", 2.0),
            ("compliance", 2.5), ("audit", 2.0), ("policy", 2.0),
            ("encryption", 2.0), ("decrypt", 2.5), ("ssl", 2.5),
            ("tls", 2.5), ("certificate", 2.5), ("pk", 1.0),
            ("quarantine", 3.0), ("blocked", 2.0), ("whitelist", 2.5),
            ("blacklist", 2.5), ("penetration", 3.0), ("pentest", 3.0),
            ("siem", 3.0), ("log", 1.0), ("security log", 3.0),
            ("incident", 1.5), ("security incident", 3.5),
            ("foreign ip", 3.5), ("failed login", 3.0),
            ("brute force", 3.5), ("credential stuffing", 3.5),
            ("zero-day", 3.5), ("patch management", 3.0),
            ("security alert", 3.5), ("flagged", 2.0),
            ("soc", 3.0), ("forensic", 3.0), ("investigation", 2.0),
            ("gdpr", 3.0), ("hipaa", 3.0), ("pci", 2.5), ("soc2", 3.0),
            ("two-step", 2.5), ("verification code", 2.5),
        ],
        "Database": [
            # Database-specific terms
            ("database", 2.5), ("db ", 1.5), ("sql", 3.0),
            ("query", 2.5), ("queries", 2.5),
            ("table", 1.5), ("tables", 1.5),
            ("timeout", 1.5), ("deadlock", 3.0), ("lock", 1.0),
            ("backup", 2.5), ("restore", 2.5), ("recovery", 2.5),
            ("transaction", 2.5), ("transactions", 2.5),
            ("connection pool", 3.0), ("connection string", 3.0),
            ("performance", 2.0), ("slow query", 3.0), ("query timeout", 3.0),
            ("index", 2.0), ("indexing", 2.0), ("constraint", 2.5),
            ("stored procedure", 3.0), ("trigger", 2.0), ("view", 1.5),
            ("schema", 2.5), ("migration", 2.5), ("schema migration", 3.0),
            ("replication", 3.0), ("cluster", 1.5), ("failover", 3.0),
            ("primary key", 3.0), ("foreign key", 3.0),
            ("insert", 2.0), ("update", 1.0), ("delete", 1.0), ("select", 1.5),
            ("join", 2.0), ("oracle", 3.0), ("mysql", 3.0),
            ("postgresql", 3.0), ("postgres", 3.0), ("sql server", 3.0),
            ("mssql", 3.0), ("mongodb", 3.0), ("redis", 2.5),
            ("sqlite", 3.0), ("dynamo", 3.0), ("cassandra", 3.0),
            ("db admin", 3.0), ("dba", 3.0), ("database administrator", 3.0),
            ("data integrity", 3.0), ("data loss", 3.0), ("corruption", 2.5),
            ("optimization", 2.5), ("tuning", 2.5),
            ("orm", 3.0), ("entity framework", 3.0), ("hibernate", 3.0),
            ("crm", 2.5), ("erp", 2.5),
            ("bloat", 3.0), ("vacuum", 2.5), ("sharding", 3.0),
            ("data warehouse", 3.0), ("etl", 3.0), ("data pipeline", 3.0),
        ],
        "Cloud/Infrastructure": [
            # Cloud and infrastructure terms
            ("cloud", 2.5), ("aws", 3.0), ("amazon web", 3.0),
            ("azure", 3.0), ("gcp", 3.0), ("google cloud", 3.0),
            ("instance", 2.0), ("ec2", 3.0), ("s3", 3.0),
            ("lambda", 2.5), ("cloud function", 3.0),
            ("virtual machine", 3.0), ("vm ", 2.0), ("vmware", 3.0),
            ("hyper-v", 3.0), ("hypervisor", 3.0), ("virtualization", 3.0),
            ("virtual", 1.5), ("vps", 3.0),
            ("container", 1.5), ("kubernetes", 2.0), ("k8s", 3.0),
            ("terraform", 3.0), ("ansible", 3.0), ("puppet", 3.0), ("chef", 2.5),
            ("infrastructure", 2.5), ("iaas", 3.0), ("paas", 3.0), ("saas", 3.0),
            ("load balancer", 3.0), ("elastic load", 3.0), ("alb", 3.0), ("nlb", 3.0),
            ("auto-scaling", 3.0), ("autoscaling", 3.0), ("scaling", 2.0),
            ("bucket", 2.0), ("blob", 2.0), ("blob storage", 3.0),
            ("cdn", 2.5), ("cloudfront", 3.0), ("cloudflare", 3.0),
            ("azure ad", 2.5), ("active directory", 1.5),
            ("office 365", 3.0), ("microsoft 365", 3.0),
            ("subscription", 2.5), ("tenant", 3.0),
            ("resource group", 3.0), ("resource", 1.5),
            ("deployment", 2.0), ("devops", 2.5), ("ci/cd", 3.0),
            ("pipeline", 1.5), ("build pipeline", 3.0),
            ("serverless", 3.0), ("microservice", 3.0), ("microservices", 3.0),
            ("api gateway", 3.0), ("service mesh", 3.0), ("istio", 3.0),
            ("monitoring", 2.0), ("cloudwatch", 3.0), ("datadog", 3.0),
            ("prometheus", 3.0), ("grafana", 3.0),
            ("iam", 3.0), ("identity and access", 3.0),
            ("snapshot", 2.5), ("ami", 3.0), ("image", 1.5),
        ],
        "HR/Onboarding": [
            # HR and onboarding terms
            ("onboarding", 3.0), ("offboarding", 3.0),
            ("new hire", 3.0), ("new employee", 3.0), ("new starter", 3.0),
            ("employee", 2.0), ("contractor", 2.5), ("freelancer", 2.5),
            ("intern", 2.5), ("temp", 1.5), ("temporary", 1.5),
            ("department", 1.5), ("manager", 1.0), ("supervisor", 1.5),
            ("start date", 3.0), ("end date", 2.5), ("last day", 3.0),
            ("exit interview", 3.0), ("separation", 3.0), ("termination", 3.0),
            ("resignation", 3.0), ("transfer", 2.0), ("relocation", 2.5),
            ("badge", 2.5), ("access card", 2.5), ("keycard", 2.5), ("id badge", 3.0),
            ("building access", 3.0), ("door access", 3.0), ("prox card", 3.0),
            ("hr", 2.0), ("human resources", 3.0), ("personnel", 2.5),
            ("payroll", 2.5), ("timesheet", 2.5), ("time tracking", 2.5),
            ("pto", 2.5), ("leave", 1.5), ("vacation", 2.0), ("sick leave", 2.5),
            ("benefits", 2.0), ("enrollment", 2.5), ("open enrollment", 3.0),
            ("training", 2.0), ("orientation", 3.0), ("welcome kit", 3.0),
            ("equipment request", 3.0), ("welcome", 1.5),
            ("seat", 1.5), ("workstation setup", 3.0),
            ("telecommute", 2.5), ("remote work", 2.5), ("hybrid", 2.0),
            ("home office", 2.5), ("work from home", 3.0), ("wfh", 3.0),
            ("org chart", 3.0), ("reporting to", 2.0), ("reporting line", 2.5),
        ],
        "Procurement": [
            # Procurement and purchasing terms
            ("purchase", 2.5), ("purchasing", 2.5), ("procurement", 3.0),
            ("order", 1.5), ("purchase order", 3.0), ("po ", 2.0),
            ("vendor", 2.5), ("supplier", 2.5), ("supplier", 2.5),
            ("license", 2.0), ("licensing", 2.5), ("license renewal", 3.5),
            ("subscription", 2.0), ("renewal", 3.0), ("renew", 2.0),
            ("expire", 1.5), ("expiration", 2.5), ("expiring", 2.5),
            ("invoice", 2.5), ("billing", 2.5), ("payment", 2.0),
            ("quote", 2.0), ("quotation", 2.0), ("rfq", 3.0), ("rfp", 3.0),
            ("contract", 2.5), ("sla", 2.5), ("agreement", 2.0),
            ("budget", 2.0), ("cost", 1.5), ("pricing", 2.5), ("quote", 2.0),
            ("approval", 2.0), ("approved", 2.0), ("approval process", 3.0),
            ("request for", 2.0), ("equipment request", 3.0),
            ("hardware request", 3.0), ("software request", 3.0),
            ("asset", 2.0), ("asset management", 3.0), ("inventory", 2.0),
            ("serial number", 2.0), ("asset tag", 3.0),
            ("warranty", 2.5), ("support contract", 3.0), ("maintenance contract", 3.0),
            ("upgrade request", 3.0), ("replacement request", 3.0),
            ("bulk order", 3.0), ("bulk purchase", 3.0),
            ("adobe", 2.0), ("microsoft", 2.0), ("creative suite", 3.0),
            ("seats", 2.5), ("concurrent", 2.0), ("per user", 2.5),
            ("po number", 3.0), ("purchase requisition", 3.0),
            ("sourcing", 2.5), ("procurement team", 3.0),
            ("it procurement", 3.5), ("approval workflow", 3.0),
        ],
        "Other": [
            # Miscellaneous / fallback terms
            ("question", 1.0), ("how do i", 1.5), ("how to", 1.5),
            ("help", 1.0), ("support", 1.0), ("assist", 1.5),
            ("information", 1.0), ("inquiry", 1.5), ("enquiry", 1.5),
            ("request", 1.0), ("general", 1.5), ("miscellaneous", 3.0),
            ("feedback", 2.0), ("suggestion", 2.0), ("complaint", 2.5),
            ("compliment", 2.5), ("thank", 1.0), ("thanks", 1.0),
            ("training", 1.5), ("documentation", 2.0), ("knowledge base", 2.5),
            ("faq", 2.5), ("guide", 1.5), ("tutorial", 1.5),
            ("policy", 1.5), ("procedure", 2.0), ("process", 1.0),
            ("unknown", 1.5), ("other", 1.5), ("uncategorized", 3.0),
            ("none of the above", 3.0), ("doesn't fit", 2.5),
        ],
    }

    CATEGORIES = list(_KEYWORD_DICTS.keys())

    def __init__(self, config: Any = None):
        self.config = config
        self.model = None
        self.vectorizer = None
        self.label_encoder = None
        self.is_trained = False

        # Pre-compile regex for lowercasing and keyword matching
        self._word_re = re.compile(r"[a-z][a-z0-9_-]*")

        # Build fast-lookup structures from keyword dicts
        self._category_keywords: Dict[str, Dict[str, float]] = {}
        self._category_total_weight: Dict[str, float] = {}
        for category, kw_list in self._KEYWORD_DICTS.items():
            kw_dict = {}
            total_weight = 0.0
            for keyword, weight in kw_list:
                kw_lower = keyword.lower().strip()
                if kw_lower:
                    # Use partial word matching key: just the key words
                    kw_dict[kw_lower] = weight
                    total_weight += weight
            self._category_keywords[category] = kw_dict
            self._category_total_weight[category] = total_weight

        # Read config values if available
        if config is not None:
            try:
                _model_type = config.get("nlp", "classification_model", "svm")
                _max_features = config.get("nlp", "max_features", 10000)
            except Exception:
                _model_type = "svm"
                _max_features = 10000
        else:
            _model_type = "svm"
            _max_features = 10000

        self._model_type = _model_type
        self._max_features = _max_features

        logger.info(
            "TicketClassifier initialized (model_type=%s, trained=%s)",
            self._model_type,
            self.is_trained,
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def classify(self, text: str) -> Dict[str, Any]:
        """Classify a single ticket text.

        Parameters
        ----------
        text : str
            Ticket title + description text.

        Returns
        -------
        dict
            ``{
                "category": str,
                "confidence": float (0-1),
                "all_scores": {category: score, ...},
                "method": "keyword" | "model"
            }``
        """
        if not text or not isinstance(text, str):
            return {
                "category": "Other",
                "confidence": 0.0,
                "all_scores": {cat: 0.0 for cat in self.CATEGORIES},
                "method": "keyword",
            }

        cleaned = sanitize_text(text)

        if self.is_trained and self.model is not None and self.vectorizer is not None:
            try:
                return self._model_classify(cleaned)
            except Exception as exc:
                logger.warning(
                    "Model classification failed, falling back to keyword: %s", exc
                )

        return self._keyword_classify(cleaned)

    def classify_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Classify multiple texts.

        Parameters
        ----------
        texts : list[str]
            List of ticket texts.

        Returns
        -------
        list[dict]
            List of classification results, one per input text.
        """
        if not texts:
            return []

        results = []
        for text in texts:
            try:
                result = self.classify(text)
            except Exception as exc:
                logger.error("Error classifying text: %s", exc)
                result = {
                    "category": "Other",
                    "confidence": 0.0,
                    "all_scores": {cat: 0.0 for cat in self.CATEGORIES},
                    "method": "keyword",
                    "error": str(exc),
                }
            results.append(result)
        return results

    def train(self, texts: List[str], labels: List[str]) -> Dict[str, Any]:
        """Train the classifier on labeled data.

        Parameters
        ----------
        texts : list[str]
            Training text samples.
        labels : list[str]
            Corresponding category labels.

        Returns
        -------
        dict
            Training metrics: ``{"accuracy": float, "samples": int, "classes": int}``
        """
        if not texts or not labels or len(texts) != len(labels):
            raise ValueError("texts and labels must be non-empty and of equal length")

        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import LabelEncoder
        from sklearn.model_selection import cross_val_score
        from sklearn.svm import LinearSVC
        from sklearn.pipeline import Pipeline

        cleaned_texts = [sanitize_text(t) for t in texts]

        self.vectorizer = TfidfVectorizer(
            max_features=self._max_features,
            ngram_range=(1, 2),
            stop_words="english",
            sublinear_tf=True,
            min_df=2,
            max_df=0.95,
        )

        self.label_encoder = LabelEncoder()
        encoded_labels = self.label_encoder.fit_transform(labels)

        X = self.vectorizer.fit_transform(cleaned_texts)

        if self._model_type == "svm":
            self.model = LinearSVC(C=1.0, max_iter=10000, class_weight="balanced")
        else:
            from sklearn.linear_model import SGDClassifier
            self.model = SGDClassifier(
                loss="modified_huber",
                max_iter=1000,
                tol=1e-3,
                class_weight="balanced",
                random_state=42,
            )

        # Cross-validation for accuracy estimate
        try:
            cv_scores = cross_val_score(self.model, X, encoded_labels, cv=min(5, len(texts) // 5) if len(texts) >= 10 else 2)
            accuracy = float(cv_scores.mean())
        except Exception:
            accuracy = 0.0

        # Train on full data
        self.model.fit(X, encoded_labels)
        self.is_trained = True

        metrics = {
            "accuracy": round(accuracy, 4),
            "samples": len(texts),
            "classes": len(self.label_encoder.classes_),
            "model_type": self._model_type,
        }
        logger.info("TicketClassifier trained: %s", metrics)
        return metrics

    # ------------------------------------------------------------------ #
    #  Keyword-based fallback classifier                                  #
    # ------------------------------------------------------------------ #

    def _keyword_classify(self, text: str) -> Dict[str, Any]:
        """Rule-based classification using weighted keyword dictionaries.

        Computes a combined score for each category based on keyword matches,
        their weights, and match frequency.  Returns the category with the
        highest normalised score.

        Parameters
        ----------
        text : str
            Cleaned ticket text.

        Returns
        -------
        dict
            Classification result with category, confidence, and all scores.
        """
        text_lower = text.lower()
        # Extract words from text for fast lookup
        text_words = set(self._word_re.findall(text_lower))

        category_scores: Dict[str, float] = {}

        for category, keyword_weights in self._category_keywords.items():
            score = 0.0
            matched_keywords = []

            for keyword, weight in keyword_weights.items():
                # Check for multi-word phrase match first
                if " " in keyword or "-" in keyword:
                    if keyword in text_lower:
                        score += weight
                        matched_keywords.append(keyword)
                else:
                    # Single-word match
                    if keyword in text_words:
                        score += weight
                        matched_keywords.append(keyword)

            category_scores[category] = score

        # Normalize scores to 0-1 range using softmax-like approach
        max_score = max(category_scores.values()) if category_scores else 0.0

        if max_score <= 0:
            return {
                "category": "Other",
                "confidence": 0.0,
                "all_scores": {cat: 0.0 for cat in self.CATEGORIES},
                "method": "keyword",
            }

        # Apply softmax normalization for confidence distribution
        exp_scores = {}
        for cat, score in category_scores.items():
            exp_scores[cat] = np.exp(score - max_score)  # subtract max for numerical stability

        total_exp = sum(exp_scores.values())
        normalized_scores = {cat: round(exp_scores[cat] / total_exp, 4) for cat in self.CATEGORIES}

        # Select the top category
        top_category = max(category_scores, key=category_scores.get)
        top_confidence = round(normalized_scores[top_category], 4)

        # If the top score is very low (no keywords matched any category well),
        # default to Other
        if category_scores[top_category] < 1.0:
            return {
                "category": "Other",
                "confidence": round(normalized_scores.get("Other", 0.3), 4),
                "all_scores": normalized_scores,
                "method": "keyword",
            }

        return {
            "category": top_category,
            "confidence": top_confidence,
            "all_scores": normalized_scores,
            "method": "keyword",
        }

    # ------------------------------------------------------------------ #
    #  Model-based classification                                         #
    # ------------------------------------------------------------------ #

    def _model_classify(self, text: str) -> Dict[str, Any]:
        """Classify using the trained TF-IDF + SVM/SGD model.

        Parameters
        ----------
        text : str
            Cleaned ticket text.

        Returns
        -------
        dict
            Classification result.
        """
        from sklearn.preprocessing import LabelEncoder

        X = self.vectorizer.transform([text])

        if hasattr(self.model, "decision_function"):
            # LinearSVC — use decision function for confidence
            decision_values = self.model.decision_function(X)[0]
            # Normalize to probability-like scores using softmax
            exp_values = np.exp(decision_values - np.max(decision_values))
            probabilities = exp_values / exp_values.sum()

            all_scores = {}
            for idx, label in enumerate(self.label_encoder.classes_):
                all_scores[label] = round(float(probabilities[idx]), 4)

            predicted_idx = int(self.model.predict(X)[0])
            predicted_label = self.label_encoder.inverse_transform([predicted_idx])[0]
            confidence = round(float(probabilities[predicted_idx]), 4)

        elif hasattr(self.model, "predict_proba"):
            # SGDClassifier with modified_huber loss — has predict_proba
            probas = self.model.predict_proba(X)[0]
            all_scores = {}
            for idx, label in enumerate(self.label_encoder.classes_):
                all_scores[label] = round(float(probas[idx]), 4)

            predicted_idx = int(np.argmax(probas))
            predicted_label = self.label_encoder.inverse_transform([predicted_idx])[0]
            confidence = round(float(probas[predicted_idx]), 4)
        else:
            # Fallback: just use predict
            predicted_idx = int(self.model.predict(X)[0])
            predicted_label = self.label_encoder.inverse_transform([predicted_idx])[0]
            all_scores = {cat: (1.0 if cat == predicted_label else 0.0) for cat in self.CATEGORIES}
            confidence = 1.0

        # Ensure all known categories are present in scores
        for cat in self.CATEGORIES:
            if cat not in all_scores:
                all_scores[cat] = 0.0

        return {
            "category": predicted_label,
            "confidence": confidence,
            "all_scores": all_scores,
            "method": "model",
        }

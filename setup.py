"""
TicketInsight Pro — Open-source, zero-cost ticket analytics platform.

Setup script for building, distributing, and installing the package.
"""

import os
from setuptools import setup, find_packages


def read_file(filepath):
    """Read a file and return its contents."""
    this_dir = os.path.abspath(os.path.dirname(__file__))
    filepath = os.path.join(this_dir, filepath)
    with open(filepath, encoding="utf-8") as f:
        return f.read()


def parse_requirements(filepath="requirements.txt"):
    """Parse requirements.txt, ignoring comments and blank lines."""
    requirements = []
    this_dir = os.path.abspath(os.path.dirname(__file__))
    filepath = os.path.join(this_dir, filepath)
    if not os.path.exists(filepath):
        return requirements
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                requirements.append(line)
    return requirements


setup(
    name="ticketinsight-pro",
    version="1.0.0",
    author="TicketInsight Team",
    author_email="team@ticketinsight.dev",
    description="Open-source, zero-cost ticket analytics platform using Flask, spaCy, and scikit-learn",
    long_description=read_file("README.md") if os.path.exists("README.md") else read_file("LICENSE"),
    long_description_content_type="text/markdown" if os.path.exists("README.md") else "text/plain",
    license="MIT",
    url="https://github.com/ticketinsight/ticketinsight-pro",
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Monitoring",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Framework :: Flask",
    ],
    keywords=["tickets", "analytics", "nlp", "machine-learning", "servicenow", "jira", "flask"],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    package_data={
        "ticketinsight": [
            "templates/**/*.html",
            "static/**/*",
            "config/*.yaml",
            "config/*.yml.example",
        ],
    },
    data_files=[
        ("ticketinsight-config", [".env.example"]),
    ],
    install_requires=parse_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-flask>=1.3.0",
            "black>=23.0.0",
            "flake8>=6.1.0",
            "mypy>=1.7.0",
            "isort>=5.13.0",
            "pre-commit>=3.6.0",
        ],
        "postgres": [
            "psycopg2-binary>=2.9.9",
        ],
        "all": [
            "spacy>=3.7.0",
            "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1.tar.gz",
        ],
    },
    entry_points={
        "console_scripts": [
            "ticketinsight=src.ticketinsight.main:cli",
        ],
    },
    zip_safe=False,
)

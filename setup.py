#!/usr/bin/env python3
"""AURA — Autonomous Engineering Audit Engine (Python setup)"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="aura-audit",
    version="2.1.2",
    author="AURA Engineering",
    author_email="engineering@aura-audit.dev",
    description="Autonomous Engineering Audit Engine — continuous audit-remediate-verify loop",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/aura/aura-audit",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Security",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    packages=find_packages(where="src", include=["*"]),
    package_dir={"": "src"},
    py_modules=["aura_cli"],
    entry_points={
        "console_scripts": [
            "aura=aura_cli:main",
            "aura-audit=aura_cli:main",
        ],
    },
    install_requires=[
        "click>=8.0",
        "pyyaml>=6.0",
        "rich>=13.0",
        "requests>=2.28",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "ruff>=0.1.0",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
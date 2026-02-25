#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ahttp-generator setup configuration for PyPI distribution.
"""

from setuptools import setup, find_packages
import os

# Read the requirements.txt file
with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

# Read the README file for long description
with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="ahttp-generator",
    version="1.0.0",
    author="gunyu1019",
    author_email="gunyu1019@gmail.com",
    description="A high-performance asynchronous OpenAPI SDK generator for the ahttp-client ecosystem",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gunyu1019/ahttp-generator",
    project_urls={
        "Bug Tracker": "https://github.com/gunyu1019/ahttp-generator/issues",
        "Source": "https://github.com/gunyu1019/ahttp-generator",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Internet",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "ahttp-generator=ahttp_generator.main:main",
        ],
    },
    keywords="openapi, sdk, generator, async, http, client, ahttp",
    license="MIT",
    include_package_data=True,
    zip_safe=False,
)

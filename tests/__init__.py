"""Windowsill's cross-platform test package.

Some integration tests intentionally reuse the dependency-free schema validator
from ``tests.test_schema``.  Declaring the directory as a package keeps that
import identical on Windows and Linux runners.
"""

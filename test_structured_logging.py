#!/usr/bin/env python3
"""Test script to verify structured logging implementation."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from claudeswarm.logging_config import setup_logging, get_logger


def test_basic_logging():
    """Test basic logging functionality."""
    print("=" * 60)
    print("TEST 1: Basic logging at INFO level")
    print("=" * 60)

    setup_logging(level="INFO")
    logger = get_logger("test.module")

    logger.debug("This DEBUG message should NOT appear (level=INFO)")
    logger.info("This INFO message SHOULD appear")
    logger.warning("This WARNING message SHOULD appear")
    logger.error("This ERROR message SHOULD appear")

    print("\n")


def test_debug_logging():
    """Test debug level logging."""
    print("=" * 60)
    print("TEST 2: Debug logging at DEBUG level")
    print("=" * 60)

    setup_logging(level="DEBUG")
    logger = get_logger("test.debug")

    logger.debug("This DEBUG message SHOULD appear now")
    logger.info("This INFO message SHOULD appear")

    print("\n")


def test_module_hierarchy():
    """Test module hierarchy in logger names."""
    print("=" * 60)
    print("TEST 3: Module hierarchy")
    print("=" * 60)

    setup_logging(level="INFO")

    logger1 = get_logger("messaging")
    logger2 = get_logger("locking")
    logger3 = get_logger("discovery")

    logger1.info("Message from messaging module")
    logger2.info("Message from locking module")
    logger3.info("Message from discovery module")

    print("\n")


def test_file_logging():
    """Test logging to file."""
    print("=" * 60)
    print("TEST 4: File logging")
    print("=" * 60)

    log_file = "/tmp/claudeswarm_test.log"
    setup_logging(level="INFO", log_file=log_file)
    logger = get_logger("test.file")

    logger.info("This message should go to both stderr and file")
    logger.warning("This warning should also go to both")

    print(f"\nLog file created at: {log_file}")
    print("Contents:")
    with open(log_file, 'r') as f:
        print(f.read())

    # Cleanup
    Path(log_file).unlink(missing_ok=True)
    print("\n")


def test_third_party_suppression():
    """Test that third-party library logs are suppressed."""
    print("=" * 60)
    print("TEST 5: Third-party library log suppression")
    print("=" * 60)

    setup_logging(level="DEBUG")

    # Get third-party loggers
    import logging
    uvicorn_logger = logging.getLogger("uvicorn")
    httpx_logger = logging.getLogger("httpx")

    # These should not appear (suppressed to WARNING level)
    uvicorn_logger.debug("uvicorn DEBUG - should NOT appear")
    uvicorn_logger.info("uvicorn INFO - should NOT appear")
    httpx_logger.debug("httpx DEBUG - should NOT appear")
    httpx_logger.info("httpx INFO - should NOT appear")

    # These should appear (WARNING level and above)
    uvicorn_logger.warning("uvicorn WARNING - SHOULD appear")
    httpx_logger.error("httpx ERROR - SHOULD appear")

    print("\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("STRUCTURED LOGGING TEST SUITE")
    print("=" * 60 + "\n")

    test_basic_logging()
    test_debug_logging()
    test_module_hierarchy()
    test_file_logging()
    test_third_party_suppression()

    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)

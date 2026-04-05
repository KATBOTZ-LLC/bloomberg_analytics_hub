"""
Configuration utilities for Bloomberg to HANA integration
"""

import os
import logging
import logging.handlers
from dotenv import load_dotenv
from pathlib import Path

def setup_logging(log_dir="logs"):
    """
    Set up logging configuration.
    Log file is overwritten per run - only keeps the latest run's logs.

    Args:
        log_dir (str): Directory to store log files

    Returns:
        tuple: (logger, log_file_path)
    """
    # Create logs directory if it doesn't exist
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Configure the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)-8s] [%(name)s:%(lineno)s]: %(message)s')
    console_formatter = logging.Formatter('[%(levelname)-8s] %(message)s')

    # Create and configure file handler (mode='w' overwrites the log file each run)
    log_file = os.path.join(log_dir, "bloomberg_ingestion.log")
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Create and configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger, log_file

def load_config():
    """
    Load configuration from .env file and environment variables.

    Returns:
        dict: Configuration parameters
    """
    # Load environment variables from .env file
    load_dotenv()

    config = {
        # SAP HANA settings
        'hana': {
            'address': os.getenv('HANA_ADDRESS'),
            'port': os.getenv('HANA_PORT', '443'),
            'user': os.getenv('HANA_USER'),
            'password': os.getenv('HANA_PASSWORD'),
            'schema': os.getenv('HANA_SCHEMA', 'BLOOMBERG_DATA'),
            'table': os.getenv('HANA_TABLE', 'FINANCIAL_RATIOS')
        }
    }

    # Validate HANA configuration (required for dashboard)
    missing_hana = []
    if not config['hana']['address']:
        missing_hana.append('HANA_ADDRESS')
    if not config['hana']['port']:
        missing_hana.append('HANA_PORT')
    if not config['hana']['user']:
        missing_hana.append('HANA_USER')
    if not config['hana']['password']:
        missing_hana.append('HANA_PASSWORD')
    if not config['hana']['schema']:
        missing_hana.append('HANA_SCHEMA')

    # Only warn for missing HANA configuration (not required for dashboard-only mode)
    if missing_hana:
        print(f"WARNING: HANA configuration incomplete: {', '.join(missing_hana)}. Dashboard will use CSV data for local testing.")

    return config

#!/usr/bin/env python3
"""
Launch a single IRC bot with the specified environment and bot name.

This script is used by the test harness to start individual bots.
"""
import asyncio
import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bots.irc_bot import IRCBot
from utils.config import load_config

# Ensure logs directory exists
LOGS_DIR = PROJECT_ROOT / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / 'bot_test.log')
    ]
)
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Launch an IRC bot')
    parser.add_argument('--env', required=True, help='Environment name (e.g., cantina)')
    parser.add_argument('--bot', required=True, help='Bot name (without .yml extension)')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode')
    return parser.parse_args()

async def run_bot(config):
    """Run the bot with the given configuration."""
    try:
        bot = IRCBot(config)
        await bot.connect()  # connect() calls _main_loop() internally
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        return 1
    return 0

def main():
    """Main entry point for the bot launcher."""
    args = parse_args()
    
    # Load bot configuration
    config_path = Path(f"environments/{args.env}/{args.bot}.yml")
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        return 1
    
    config = load_config(config_path)
    
    # Set test mode if specified
    if args.test_mode:
        config['test_mode'] = True
        # Use test server settings
        config['server'] = '127.0.0.1'
        config['port'] = 16667
        config['channels'] = ["#test-channel"]
    
    # Create and start the bot
    try:
        asyncio.run(run_bot(config))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

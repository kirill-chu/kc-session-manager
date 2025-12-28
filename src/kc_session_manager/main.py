#!/usr/bin/env python3
"""
Author: kirill-chu <nefka2006@yandex.ru>
"""

import argparse
import asyncio

from kc_session_manager.core.logger_config import LoggerConfig


def get_args():
    """Parsing args"""

    parser = argparse.ArgumentParser(
        description="KC Session Manager"
    )
    parser.add_argument(
        "-d", "--daemon", action="store_true", help="Run as daemon (disable console output)"
    )
    parser.add_argument("-l", "--log", type=str, help="Path to log file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--debug", action="store_true", help="Debug mode (verbose + debug level)")

    return parser.parse_args()

async def async_main():
    from kc_session_manager.core.application import Application

    app = Application()
    return await app.run()

def main():

    args = get_args()

    LoggerConfig.setup_logging(
        debug=args.debug,
        log_file=None if not args.log else args.log,
        interactive=not args.daemon,
        verbose=args.verbose,
    )

    logger = LoggerConfig.get_logger()
    logger.debug("Application started with args: %s", args)

    return asyncio.run(async_main())

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)

"""
This file contains some rule functions.

Author: kirill-chu <nefka2006@yandex.ru>
"""

from kc_session_manager.core.logger_config import LoggerConfig

logger = LoggerConfig.get_logger()


def basic_dpms_screensaver_rule(sensor_states):
    """
    Basic rule: idle set true if DPMS is not on or screensaver is on
    """

    logger.info(f"Raw sensor states: {sensor_states}")

    dpms_state = sensor_states.get("dpms", {}).get("state", "unkown")
    screensaver_state = sensor_states.get("screensaver", {}).get("state", "unkown")
    session_state = sensor_states.get("session_locking", {}).get("state", "unkown")

    if (dpms_state or sensor_states) == "unknown":
        return None

    logger.debug(f"{dpms_state=}")
    logger.debug(f"{screensaver_state=}")

    if dpms_state is None and screensaver_state is None:
        return None

    try:
        should_idle = (
            dpms_state.lower() in ["standby", "suspend", "off"] or
            screensaver_state.lower() == "on"
        )
        if session_state == "locked":
            should_idle = True
        return should_idle

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=e)

def modest_dpms_screensaver_rule(sensor_states):
    """
    Modest rule: idle set true if DPMS is off and screensaver is on
    """

    logger.debug(f"Raw sensor states: {sensor_states}")
    dpms_state = sensor_states.get("dpms", {}).get("state")
    screensaver_state = sensor_states.get("screensaver", {}).get("state")

    logger.debug(f"{dpms_state=}")
    logger.debug(f"{screensaver_state=}")

    if dpms_state is None or screensaver_state is None:
        return None

    try:
        should_idle = (
            dpms_state.lower() in ["standby", "suspend", "off"] and
            screensaver_state.lower() == "on"
        )
        return should_idle

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=e)

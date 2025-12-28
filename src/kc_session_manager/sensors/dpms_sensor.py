"""
Author: kirill-chu <nefka2006@yandex.ru>
"""

import asyncio

import xcffib
import xcffib.dpms

from kc_session_manager.core.logger_config import LoggerConfig
from kc_session_manager.sensors.base_sensor import BaseSensor

logger = LoggerConfig.get_logger()


class DpmsPollingMonitor(BaseSensor):
    """DPMS monitoring"""

    def __init__(self, poll_interval=2):
        super().__init__("dpms")
        self.poll_interval = poll_interval
        self.conn = None
        self.dpms = None
        self.dpms_available = False
        self.last_power_level = None

        self.dpms_modes = {
            0: "On",
            1: "Standby",
            2: "Suspend",
            3: "Off"
        }

    async def initialize(self):
        """Initializing connection to X11"""

        try:
            self.conn = xcffib.connect()
            self.dpms = self.conn(xcffib.dpms.key)
            _ = self.dpms.GetVersion(1, 1).reply()
            self.dpms_available = True
            logger.info("DPMS extension is available")
        except Exception as e:
            logger.error(f"Initialization connection error: {e}", exc_info=e)

    async def get_initial_state(self):
        """Getting current DPMS state"""

        try:
            info_reply = self.dpms.Info().reply()
            power_level = info_reply.power_level
            self.last_power_level = power_level
            self.current_state = self.dpms_modes.get(power_level, "unknown")
            return self.current_state

        except Exception as e:
            logger.info(f"Getting {self.name} current sate error: {e}")
            return "unknown"

    async def start_monitoring(self):
        """Run DPMS monitoring"""

        try:
            self.running = True
            logger.info(f"Sensor {self.name} started (pooling each {self.poll_interval} sec)")

            while self.running:
                await self._check_dpms_state()
                await asyncio.sleep(self.poll_interval)

        except Exception as e:
            logger.error(f"Sensor {self.name} error {e}", exc_info=e)
            await self.stop()

    async def _check_dpms_state(self):
        """Checking sate of DPMS"""

        try:
            info_reply = self.dpms.Info().reply()
            power_level = info_reply.power_level
            logger.debug(f"Raw {info_reply=}")
            if self.last_power_level != power_level:
                self.last_power_level = power_level
                await self.update_state(self.dpms_modes.get(power_level, "unknown"))

        except Exception as e:
            logger.error(f"Getting DPMS state error: {e}", exc_info=e)

    async def stop_monitoring(self):
        """Stop sensor"""

        self.running = False
        if self.conn:
            self.conn.disconnect()
        logger.info(f"Sensor {self.name} stopped")


async def async_main():
    manager = DpmsPollingMonitor()
    try:
        await manager.start()
    finally:
        await manager.stop_monitoring()


def main():
    return asyncio.run(async_main())

if __name__ == "__main__":
    main()

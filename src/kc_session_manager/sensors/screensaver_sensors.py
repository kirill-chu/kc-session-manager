import asyncio

import xcffib
import xcffib.screensaver

from kc_session_manager.core.logger_config import LoggerConfig
from kc_session_manager.sensors.base_sensor import BaseSensor

logger = LoggerConfig.get_logger()


class ScreensaverMonitor(BaseSensor):
    """XCB event monitoring"""
    
    def __init__(self):
        super().__init__("screensaver")
        self.conn = None
        self.root = None
        self.screensaver = None

        self.screensaver_state = {
            0: "off",
            1: "on",
            3: "disabled",
        }

    async def initialize(self):
        """Initializing connection to X11"""

        try:
            self.conn = xcffib.connect()
            setup = self.conn.get_setup()
            self.root = setup.roots[0].root
            self.screensaver = self.conn(xcffib.screensaver.key)
            logger.info(f"Screensaver extension is available")
        except Exception as e:
            logger.error(f"Initialization connection error: ", exc_info=e)
    
    async def get_initial_state(self):
        """Getting screensaver state"""
        try:
            info_reply = self.screensaver.QueryInfo(self.root).reply()
            self.current_state = self.screensaver_state.get(info_reply.state, "unknown")
            logger.debug(info_reply)
            return self.current_state

        except Exception as e:
            logger.info(f"Getting {self.name} current sate error: ", exc_info=e)
            return "unknown"

    
    async def start_monitoring(self):
        """Starting screensaver monitoring"""

        try:
            SCREENSAVER_NOTIFY_MASK = 0x001
            self.screensaver.SelectInput(self.root, SCREENSAVER_NOTIFY_MASK)
            self.conn.flush()
            
            self.running = True
            logger.info(f"Sensor {self.name} started")
            
            await self._event_loop()
            
        except Exception as e:
            logger.error(f"Sensor starting error {self.name}: {e}")
            await self.stop()
    
    async def _event_loop(self):
        """Event loop"""

        while self.running:
            try:
                event = self.conn.poll_for_event()
                if event:
                    if isinstance(event, xcffib.screensaver.NotifyEvent):
                        await self.update_state(self.screensaver_state.get(event.state, "unknown"))
                await asyncio.sleep(0.01)
            except Exception as e:
                if self.running:
                    logger.error(f"Event loop error in {self.name}: {e}")
    
    async def stop_monitoring(self):
        """Stop sensor"""

        self.running = False
        if self.conn:
            self.conn.disconnect()
        logger.info(f"Sensor {self.name} stopped")
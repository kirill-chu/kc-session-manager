"""
Author: kirill-chu <nefka2006@yandex.ru>
"""

import asyncio
import signal

from kc_session_manager.core.event_dispatcher import EventDispatcher
from kc_session_manager.core.idle_manager import IdleManager
from kc_session_manager.core.logger_config import LoggerConfig
from kc_session_manager.core.rules import basic_dpms_screensaver_rule, modest_dpms_screensaver_rule
from kc_session_manager.sensors.dpms_sensor import DpmsPollingMonitor
from kc_session_manager.sensors.lock_session_sensor import SessionLockListener
from kc_session_manager.sensors.screensaver_sensors import ScreensaverMonitor
from kc_session_manager.sensors.vt_sensor import VTSensor

logger = LoggerConfig.get_logger()


class Application:
    """Main application class"""

    def __init__(self):
        self.idle_manager = IdleManager()
        self.dispatcher = EventDispatcher(self.idle_manager)

        self.running = False

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Signal handler or graceful shutdown"""

        logger.info(f"Signal {signum} received, stopping...")
        self.running = False

    async def initialize(self):
        """All components initialization"""

        if not await self.idle_manager.initialize():
            return False

        result, msg = await self.idle_manager.get_our_session()
        if not result:
            logger.error(msg)
            return False

        await self.idle_manager.set_idle(True)
        await self.idle_manager.set_idle(False)

        screensaver_sensor = ScreensaverMonitor()
        self.dispatcher.register_sensor(screensaver_sensor)

        dpms_monitor = DpmsPollingMonitor()
        self.dispatcher.register_sensor(dpms_monitor)

        locking_session = SessionLockListener()
        self.dispatcher.register_sensor(locking_session)

        vt_sensor = VTSensor()
        self.dispatcher.register_sensor(vt_sensor)
        self.idle_manager.add_rule(modest_dpms_screensaver_rule, priority=1)
        self.idle_manager.add_rule(basic_dpms_screensaver_rule, priority=0)

        return True

    async def run(self):
        """Staring the application"""

        if not await self.initialize():
            return 1
        self.running = True

        logger.info("Application is running")
        logger.info("Starting sensors...")
        monitor_tasks = await self.dispatcher.start_all_sensors()

        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Ctrl+C received")
        finally:
            await self.dispatcher.stop_all_sensors()
            for task in monitor_tasks:
                task.cancel()
            await self.idle_manager.cleanup()

        return 0

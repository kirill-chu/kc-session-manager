"""
Author: kirill-chu <nefka2006@yandex.ru>

Active VT (Virtual Terminal) sensor
"""

import asyncio

from kc_session_manager.core.logger_config import LoggerConfig
from kc_session_manager.sensors.base_sensor import BaseSensor

logger = LoggerConfig.get_logger()


class VTSensor(BaseSensor):
    """Отслеживает активный VT"""

    def __init__(self):
        super().__init__("vt")
        self.our_vt: int | None = None   # VT нашего X-сервера (:0)

    async def get_active_vt(self):
        """Получение активного VT через /sys"""

        try:
            with open("/sys/class/tty/tty0/active") as f:
                tty = f.read().strip()
                if tty.startswith("tty"):
                    return int(tty[3:])
        except Exception as e:
            logger.error(f"Error getting active VT: {e}", exc_info=e)
        return None

    async def get_initial_state(self):
        """Получение начального состояния"""
        vt_state = await self.get_active_vt()
        if vt_state:
            self.our_vt = vt_state
            self.current =  "active" if vt_state == 7 else "inactive"
        return self.current if self.current else "unknown"

    async def start_monitoring(self):
        """Мониторинг изменений VT"""

        self.running = True
        logger.info(f"Sensor {self.name} started")

        while self.running:
            new_vt = await self.get_active_vt()
            if new_vt != self.current:
                old_vt = self.current
                self.current = new_vt

                # Определяем состояние на основе VT
                state = "active" if new_vt == self.our_vt else "inactive"
                logger.info(f"VT changed from {old_vt} to {new_vt}, state: {state}")
                await self.update_state(state, "vt_change")

            await asyncio.sleep(2)  # Проверяем каждые 2 секунды

    async def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        logger.info(f"Sensor {self.name} stopped")

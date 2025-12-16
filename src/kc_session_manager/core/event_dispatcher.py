import asyncio

from kc_session_manager.core.idle_manager import IdleManager
from kc_session_manager.sensors.base_sensor import BaseSensor


class EventDispatcher:
    """Events dispantcher"""
    
    def __init__(self, idle_manager: IdleManager):
        self.handlers: dict = {}
        self.sensors: list = []
        self.idle_manager: IdleManager = idle_manager
    
    def register_sensor(self, sensor: BaseSensor):
        """Registering a sensor"""
        self.sensors.append(sensor)
        sensor.set_callback(self._handle_sensor_update)
    
    async def _handle_sensor_update(self, sensor_name: str, event_type: str, state: str):
        """Processing sensor updates"""
        await self.idle_manager.handle_sensor_update(sensor_name, event_type, state)
    
    async def start_all_sensors(self):
        """Starting all sensors"""

        tasks = []
        for sensor in self.sensors:
            task = asyncio.create_task(sensor.start())
            tasks.append(task)
        return tasks
    
    async def stop_all_sensors(self):
        """Stopping all sensors"""
        for sensor in self.sensors:
            await sensor.stop()
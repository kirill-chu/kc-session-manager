import logging
from abc import ABC, abstractmethod
from typing import Any

class BaseSensor(ABC):
    """Abstract class for sensors"""
    
    def __init__(self, name):
        self.name = name
        self.callback = None
        self.running = False
        self.current_state = None
    
    def set_callback(self, callback):
        """Set callback for notifications"""
        self.callback = callback
    
    async def get_initial_state(self):
        """Getting initial sensor state"""

    async def initialize(self):
        """Sensor initialization (Optional)"""

    async def notify(self, event_type, state):
        """Sending the notification via callback"""
        if self.callback:
            await self.callback(self.name, event_type, state)
    
    async def start(self):
        """Start: Initialization, set initials parameters, staring monitoring"""

        await self.initialize()

        initial_state = await self.get_initial_state()
        if initial_state is not None:
            self.current_state = initial_state
            logging.debug(
                f"Initial state for {self.__class__.__name__}, state: {initial_state}"
            )
            await self.notify("initial", initial_state)
        
        await self.start_monitoring()
    
    async def stop(self):
        """Stop monitoring"""
        await self.stop_monitoring()
    
    async def update_state(self, new_state: Any, event_type: str = "change"):
        """Updating state and sending notification"""
        
        if new_state != self.current_state:
            self.current_state = new_state
            logging.debug(
                f"Update. Event: {event_type} for {self.__class__.__name__}, state: {new_state}"
            )
            await self.notify(event_type, new_state)
    
    @abstractmethod
    async def start_monitoring(self):
        """Start monitoring"""
 
    @abstractmethod
    async def stop_monitoring(self):
        """Stop monitoring"""

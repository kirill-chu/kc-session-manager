"""
seat_manager.py - Отслеживание состояния seat0 через D-Bus
"""

import asyncio
from typing import Optional, Callable
from dbus_fast.aio import MessageBus, ProxyInterface
from dbus_fast import BusType

from kc_session_manager.core.logger_config import LoggerConfig


logger = LoggerConfig.get_logger()

class SeatManager:
    """Управление состоянием seat0 через systemd-logind"""
    
    def __init__(self):
        self.bus: Optional[MessageBus] = None
        self.seat_proxy: Optional[ProxyInterface] = None
        self.current_idle_hint = False
        self.idle_hint_listeners = []
        self.session_removed_listeners = []
        self._running = False
        
    async def initialize(self) -> bool:
        """Инициализация подключения к D-Bus"""
        try:
            self.bus = MessageBus(bus_type=BusType.SYSTEM)
            await self.bus.connect()
            
            # Получаем seat0
            manager_introspection = await self.bus.introspect(
                "org.freedesktop.login1",
                "/org/freedesktop/login1"
            )
            
            manager = self.bus.get_proxy_object(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                manager_introspection
            ).get_interface("org.freedesktop.login1.Manager")
            
            # Получаем путь к seat0
            seat_path = await manager.call_get_seat("seat0")
            
            # Получаем интерфейс seat
            seat_introspection = await self.bus.introspect(
                "org.freedesktop.login1",
                seat_path
            )
            
            seat_obj = self.bus.get_proxy_object(
                "org.freedesktop.login1",
                seat_path,
                seat_introspection
            )
            
            self.seat_proxy = seat_obj.get_interface("org.freedesktop.login1.Seat")
            
            # Подписываемся на изменения свойств
            self.seat_proxy.on_properties_changed(self._on_seat_properties_changed)
            
            # Получаем начальное состояние
            props = await self.seat_proxy.call_get_all()
            self.current_idle_hint = props.get("IdleHint", False)
            
            logger.info(f"SeatManager initialized. Current idle: {self.current_idle_hint}")
            return True
            
        except Exception as e:
            logger.error(f"SeatManager initialization error: {e}")
            return False
    
    def add_idle_hint_listener(self, listener: Callable[[bool], None]):
        """Добавление слушателя изменений IdleHint"""
        self.idle_hint_listeners.append(listener)
    
    def add_session_removed_listener(self, listener: Callable[[str], None]):
        """Добавление слушателя удаления сессий"""
        self.session_removed_listeners.append(listener)
    
    def _on_seat_properties_changed(self, interface: str, changed: dict, invalidated: dict):
        """Обработчик изменения свойств seat"""
        if "IdleHint" in changed:
            new_idle = changed["IdleHint"]
            if new_idle != self.current_idle_hint:
                self.current_idle_hint = new_idle
                logger.info(f"Seat IdleHint changed: {new_idle}")
                for listener in self.idle_hint_listeners:
                    asyncio.create_task(listener(new_idle))
    
    async def get_active_sessions_count(self) -> int:
        """Получение количества активных сессий"""
        try:
            sessions = await self.seat_proxy.call_get_sessions()
            active_count = 0
            for session_path in sessions:
                session_introspection = await self.bus.introspect(
                    "org.freedesktop.login1",
                    session_path
                )
                session_obj = self.bus.get_proxy_object(
                    "org.freedesktop.login1",
                    session_path,
                    session_introspection
                )
                session_interface = session_obj.get_interface("org.freedesktop.login1.Session")
                props = await session_interface.call_get_all()
                # Сессия считается активной, если она не idle и не locked
                if not props.get("IdleHint", False):
                    active_count += 1
            return active_count
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return 0
    
    async def cleanup(self):
        """Очистка ресурсов"""
        if self.bus:
            self.bus.disconnect()
""""
Author: kirill-chu <nefka2006@yandex.ru>
"""

import asyncio
import os
import signal
from typing import Callable

from dbus_fast import BusType
from dbus_fast.aio import MessageBus, ProxyInterface, ProxyObject
from dbus_fast.signature import Variant

from kc_session_manager.core.logger_config import LoggerConfig
from kc_session_manager.sensors.base_sensor import BaseSensor

logger = LoggerConfig.get_logger()


class SessionLockListener (BaseSensor):
    """Session lock signal monitoring via DBus"""
    
    def __init__(self):
        super().__init__("session_locking")
        self.bus: MessageBus | None = None
        self.manager_proxy: ProxyInterface| None = None
        
        self.session_path: str | None = None
        self.session_properties: dict = {}
        self.session_properties_interface: ProxyInterface = None
        self.session_interface: ProxyInterface = None
        self.session_obj: ProxyObject | None = None

        self.running: bool = True
        self._is_initialized: bool = False
        self._signal_handlers: list = []

        self._callback_lock: Callable | None = None
        self._callback_unlock: Callable | None = None
        self._callback_change_properties: Callable | None = None
        
    async def initialize(self):
        """D-Bus connection initialization"""

        if self._is_initialized:
            logger.debug("Connection already initialized")
            return True

        try:
            self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            
            manager_intro = await self.bus.introspect(
                "org.freedesktop.login1",
                "/org/freedesktop/login1"
            )
            manager_obj = self.bus.get_proxy_object(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                manager_intro
            )

            self.manager_proxy = manager_obj.get_interface("org.freedesktop.login1.Manager")
            
            self._is_initialize = True
            logger.info(f"Sensor {self.name} initialized")
            return True
            
        except Exception as e:
            logger.error(f"D-Bus initialization error: {e}")
            return False

    def _variant_to_dict(self, data: dict[str, Variant]) -> dict:
        """Convert variant to dict"""

        result = {}
        try:
            for k, v in data.items():
                result[k] = v.value if hasattr(v, "value") else v
        except Exception as e:
            logger.error(f"Variant convert error: ", exc_info=e)
            return result
        return result

    async def get_initial_state(self):
        """Getting session active state"""

        try:
            self.session_path = await self._get_current_session_path(self.manager_proxy)
            if not self.session_path:
                logger.error("Getting current session error")
                return False
            logger.info(f"session_path type: {type(self.session_path)}")

            session_introspection = await self.bus.introspect(
                "org.freedesktop.login1",
                self.session_path
            )
            self.session_obj = self.bus.get_proxy_object(
                "org.freedesktop.login1",
                self.session_path,
                session_introspection
            )
            logger.info(f"session_obj type: {type(self.session_obj)}")

            self.session_properties_interface = self.session_obj.get_interface(
                "org.freedesktop.DBus.Properties"
            )
            props = await self.session_properties_interface.call_get_all(
                "org.freedesktop.login1.Session"
            )
            self.session_properties = self._variant_to_dict(props)
            logger.debug(f"session_properties = {self.session_properties}")
            
            self.session_interface = self.session_obj.get_interface(
                "org.freedesktop.login1.Session"
            )

            await self._subscribe_signals()

            return "unlocked" if self.session_properties["Active"] else "locked"
        except Exception as e:
            logger.error(f"Initial state error: ", exc_info=e)

    async def _get_current_session_path(self, manager_interface):
        """Getting current session path"""

        try:

            session_id = os.getenv("XDG_SESSION_ID")
            if session_id:
                return await self.manager_proxy.call_get_session(session_id)
            else:
                pid = os.getpid()
                return await self.manager_proxy.call_get_session_by_pid(pid)

        except Exception as e:
            logger.error(f"Getting current session error: {e}")
            return None
    
    async def _subscribe_signals(self):
        """Subscribing to D-Bus messages"""
        
        await self._cleanup_signal_handlers()
        
        logger.info(f"session_interface type: {type(self.session_interface)}")
        
        self._callback_lock = self._on_lock
        self._callback_unlock = self._on_unlock

        self.session_interface.on_lock(self._callback_lock)
        self.session_interface.on_unlock(self._callback_unlock)
        await self._subscribe_to_session_properties(self.session_path, self.session_obj)

        self._signal_handlers.append(self._on_lock)
        self._signal_handlers.append(self._on_lock)
        for method in self._signal_handlers:
            logger.info(f"list of _on_loks: {method}")
            logger.info(f"list of _on_loks: {id(method)}")

    def _on_session_properties_changed(
            self,
            session_path: str, 
            changed_properties: dict,
            invalidated: list
        ):
        """Handler of changing session properties"""

        logger.info(
            f"Handler of changing session {session_path} properties: {changed_properties},"
            f"invalidated: {invalidated}"
        )

        changed_properties = self._variant_to_dict(changed_properties)
        for k, v in changed_properties.items():
            self.session_properties[k] = v
            logger.info(f"Session::{session_path} {k}: {v}")
            """
            we should write here something like:
            if k == "Active":
                self.update_state("Active", True == v)
            """
            if k == "Active":
                logger.info(f"Getting Active k={k},v={v}")
                self.update_state("Active", True == v)

        logger.debug(f"session_properties = {self.session_properties}")

    async def _subscribe_to_session_properties(self, session_path: str, session_obj: ProxyObject):
        """Subscribing to chenging session properties"""

        logger.info("Subscribing to chenging session properties")
        try:
            logger.info(
                f"session_properties_interface type: {type(self.session_properties_interface)}"
            )
            
            self._callback_change_properties = self._on_session_properties_changed
            self.session_properties_interface.on_properties_changed(
                self._callback_change_properties
            )

        except Exception as e:
            logger.error(f"Error subscribing to session properties for {session_path}: {e}")

    async def _cleanup_signal_handlers(self):
        """Cleaning all singal handlers"""
        
        try:
            if self._callback_lock:
                self.session_interface.off_lock(self._callback_lock)
                self._callback_lock = None
            
            if self._callback_unlock:
                self.session_interface.off_lock(self._callback_unlock)
                self._callback_unlock = None
            
            if self._callback_change_properties:
                self.session_properties_interface.off_properties_changed(
                    self._callback_change_properties
                )
                self._callback_change_properties = None

            # for unsubscribe in self._signal_handlers:
            #         unsubscribe()
        except Exception as e:
            logger.error(f"Unsubscribing from signal handlers error", exc_info=e)
        finally:
            self._signal_handlers.clear()

    async def _on_lock(self):
        """Lock session handler"""

        logger.info("Lock signal has been received")
        await self.update_state("lock", "set")
    
    async def _on_unlock(self):
        """Unlock session handler"""

        logger.info("Unlock signal has been received")
        await self.update_state("unlock", "set")
 
    async def start_monitoring(self):
        """Run session lock monitoring"""

        logger.info(f"Sensor {self.name} subscribed to {self.session_path}")
        while self.running:
            await asyncio.sleep(1)
   
    async def stop_monitoring(self):
        """Stop monitoring"""

        self.running = False
        if self.bus:
            await  self._cleanup_signal_handlers()
            self.bus.disconnect()
        logger.info(f"Sensor {self.name} stopped")


async def async_main():
    listener = SessionLockListener()
    
    def signal_handler():
        asyncio.create_task(listener.stop_monitoring())
    
    loop = asyncio.get_running_loop()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await listener.start_monitoring()
    except asyncio.CancelledError:
        await listener.stop_monitoring()

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
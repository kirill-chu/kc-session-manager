#!/usr/bin/env python3
"""
kc-idle-manage - The system service to manage idle state of LightDM sessions.
It was made for working with LightdDM.
It is better to run this service from lightdm user instead of root.

The main task of this script is detecting new x11 LightDM session and setting them to the idle.
It subscribes to some signals to fulfill that.
Some methods or functions are exists and to do nothing but they helped me to watch what is going on
when I am testing this solution, they are only logging something.

Author: kirill-chu <nefka2006@yandex.ru>

"""

import asyncio
import logging
import signal
import sys
from logging import FileHandler, StreamHandler
from pathlib import Path
from types import FrameType
from typing import Callable

from dbus_fast import BusType
from dbus_fast.aio import MessageBus, ProxyInterface, ProxyObject
from dbus_fast.signature import Variant

DEBUG = False

unit: str = Path(__file__).stem

log_handlers: list [StreamHandler | FileHandler] = [StreamHandler(sys.stdout)]
if DEBUG:
    log_file_handler = FileHandler(f"/tmp/{unit}.log")
    log_handlers.append(log_file_handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=log_handlers
)
logger = logging.getLogger(unit)

logger.debug(f"unit: {unit}")

class SystemIdleManager:
    """Managing idle state of lightdm sessions"""

    def __init__(self):
        self.bus: MessageBus | None = None
        self.manager_proxy: ProxyInterface | None = None

        self.sessions: dict[str, dict] = {}
        self.lightdm_sessions: dict[str, dict[str, ProxyInterface | Callable]] = {}
        self._new_seesion_props: ProxyInterface | None = None
        
        self._callback_session_new: Callable | None = None
        self._callback_session_removed: Callable | None = None
        self._callback_prepare_for_sleep: Callable | None = None
        

        self.session_timers: dict[str, asyncio.Task] = {}

        self.idle_timeout: int = 300
        self.poll_interval: int = 2

        self.running: bool = True

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum: int, frame: FrameType | None):
        """Signal handler for graceful shutdown"""

        logger.info(f"Signal {signum} received, stopping...")
        self.running = False

    async def initialize(self) -> bool:
        """Initialize D-Bus connection"""

        try:
            self.bus = MessageBus(bus_type=BusType.SYSTEM)
            await self.bus.connect()

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

            await self._setup_signal_handlers()

            logger.info("SystemIdleManager initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Initialization error: {e}", exc_info=True)
            return False

    async def _setup_signal_handlers(self):
        """Setting up event handlers"""
        
        self._callback_session_new = self._on_session_new
        self._callback_session_removed = self._on_session_removed
        self._callback_prepare_for_sleep = self._on_prepare_for_sleep

        self.manager_proxy.on_session_new(self._on_session_new)
        self.manager_proxy.on_session_removed(self._on_session_removed)
        self.manager_proxy.on_prepare_for_sleep(self._on_prepare_for_sleep)

        logger.info("Signal handlers setup complete")

    async def _get_session_proxy(
            self, session_path: str
        ) -> tuple[ProxyInterface, ProxyObject] | None:
        """Getting proxy for session"""

        try:
            session_intro = await self.bus.introspect(
                "org.freedesktop.login1",
                session_path
            )
            session_obj = self.bus.get_proxy_object(
                "org.freedesktop.login1",
                session_path,
                session_intro
            )
            session_proxy = session_obj.get_interface("org.freedesktop.login1.Session")

            return (session_proxy, session_obj)
        except Exception as e:
            logger.debug(f"Error getting session proxy for {session_path}: {e}")
            return None

    async def _subscribe_to_session_properties(self, session_path: str, session_obj: ProxyObject):
        """Subscribing to changing session properties"""

        logger.info("Subscribing to changing session properties")
        try:
            session_props = session_obj.get_interface("org.freedesktop.DBus.Properties")
            self.lightdm_sessions[session_path]["session_props"] = session_props

            self.lightdm_sessions[session_path]["properties_changed"] = (
                self._on_session_properties_changed
            )
            session_props.on_properties_changed(
                self.lightdm_sessions[session_path]["properties_changed"]
            )

        except Exception as e:
            logger.error(f"Error subscribing to session properties for {session_path}: {e}")

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

    async def _on_session_new(self, session_id: str, session_path: str):
        """Handler of new session creation"""

        logger.info(f"New session: {session_id} at {session_path}")

        session_proxy, session_obj = await self._get_session_proxy(session_path)
        if not session_proxy:
            return

        session_props_iface = session_obj.get_interface("org.freedesktop.DBus.Properties")
        try:
            props = await session_props_iface.call_get_all("org.freedesktop.login1.Session")
            props = self._variant_to_dict(props)
            logger.debug(f"props: {props}")

            seat = props.get("Seat", "unknown")[0]
            name = props.get("Name", "unknown")
            if name == "lightdm" and seat == "seat0":
                logger.info(f"New LightDM session created: {session_path}")
                self.lightdm_sessions[session_path]= {"session_proxy": session_proxy}

                await self._subscribe_to_session_properties(session_path, session_obj)

                await self._schedule_lightdm_idle(session_path)

            self.sessions[session_path] = props

        except Exception as e:
            logger.error(f"Error processing new session {session_path}", exc_info=e)

    async def _on_session_removed(self, session_id: str, session_path: str):
        """Handler of session deletation"""

        logger.info(f"Session removed: {session_id}")

        if session_path in self.sessions:
            del self.sessions[session_path]

        if session_path in self.lightdm_sessions:
            del self.lightdm_sessions[session_path]

            if session_path in self.session_timers:
                self.session_timers[session_path].cancel()
                del self.session_timers[session_path]

    def _on_session_properties_changed(
            self, session_path: str, changed_properties: dict, nvalidated_properties: list):
        """Handler of changing session properties"""

        logger.debug(
            f"Handler of changing session {session_path} properties: {changed_properties}"
        )

        if session_path not in self.sessions:
            return

        session_info = self.sessions[session_path]
        changed_properties = self._variant_to_dict(changed_properties)
        for k, v in changed_properties.items():
            session_info[k] = v
            logger.info(f"Session {session_path} {k}: {v}")

        self.sessions[session_path] = session_info
        logger.debug(f"{self.sessions=}")

    async def _on_prepare_for_sleep(self, start: bool):
        """Handler of suspend/resume states"""

        if start:
            logger.info("System going to suspend")

            for timer in self.session_timers.values():
                timer.cancel()
            self.session_timers.clear()
        else:
            logger.info("System resumed from suspend")

            for session_path in self.lightdm_sessions:
                await self._schedule_lightdm_idle(session_path)

    async def _schedule_lightdm_idle(self, session_path: str):
        """Scheduling to set idle for LightDM session"""

        if session_path in self.session_timers:
            self.session_timers[session_path].cancel()

        async def set_lightdm_idle():
            try:
                await asyncio.sleep(self.idle_timeout)

                if session_path not in self.lightdm_sessions:
                    return

                success = await self._set_session_idle(session_path, True)

                if success:
                    logger.info(
                        f"LightDM session {session_path} set to idle after {self.idle_timeout}s"
                    )
                else:
                    logger.warning(f"Failed to set LightDM session {session_path} to idle")

            except Exception as e:
                logger.error(f"Error setting LightDM idle: {e}", exc_info=True)

        self.session_timers[session_path] = asyncio.create_task(set_lightdm_idle())

        logger.info(f"Scheduled LightDM idle for {session_path} in {self.idle_timeout}s")

    async def _set_session_idle(self, session_path: str, idle: bool):
        """Setting idle to session"""

        try:
            session_interface = self.lightdm_sessions.get(session_path).get("session_proxy")
            if not session_interface:
                logger.info(
                    f"Session path {session_path} was not found in the saved "
                    "list of lightdm session"
                )

                session_interface, _ = await self._get_session_proxy(session_path)
                if not session_interface:
                    logger.warning(f"Session proxy not found for {session_path}")
                    return False

            await session_interface.call_set_idle_hint(idle)
            logger.info(f"Set idle hint for {session_path} to {idle}")
            return True

        except Exception as e:
            logger.error(f"Error setting idle hint for {session_path}: {e}")
            return False

    async def _monitor_system_state(self):
        """System state monitoring"""

        while self.running:
            try:
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in system state monitoring: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def cleanup(self):
        """Clean up"""

        try:

            for _, v in self.lightdm_sessions:
                if v:
                    v["session_props"].off_properties_change(v["properies_changed"])

            if self._callback_session_new:
                self.manager_proxy.off_session_new(self._callback_session_new)
                self._callback_session_new = None
            
            if self._callback_session_removed:
                self.manager_proxy.off_session_removed(self._callback_session_removed)
                self._callback_session_removed = None
            
            if self._callback_prepare_for_sleep:
                self.manager_proxy.off_prepare_for_sleep(self._callback_prepare_for_sleep)
                self._callback_prepare_for_sleep = None
        except Exception as e:
            logger.error(f"Unsubscribing from signal handlers error", exc_info=e)
        finally:
            for timer in self.session_timers.values():
                timer.cancel()

            if self.bus:
                self.bus.disconnect()

        logger.info("SystemIdleManager cleaned up")

    async def run(self):
        """Service main loop"""

        if not await self.initialize():
            logger.error("Failed to initialize SystemIdleManager")
            return

        logger.info("SystemIdleManager started")

        try:
            monitor_task = asyncio.create_task(self._monitor_system_state())
            await monitor_task

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            await self.cleanup()
            logger.info("SystemIdleManager stopped")


async def main():
    """Entrypoint"""

    manager = SystemIdleManager()
    await manager.run()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
from asyncio import Task
from operator import itemgetter
from pathlib import Path
from typing import Any, Callable

from dbus_fast.aio import MessageBus, ProxyObject
from dbus_fast import BusType

from kc_session_manager.core.logger_config import LoggerConfig


logger = LoggerConfig.get_logger()


class IdleManager:
    """Manage idle dile status via D-Bus"""
    
    def __init__(self):
        self.bus: MessageBus | None = None
        self.manager_proxy: ProxyObject | None = None
        self.current_idle: bool = False
        self.rules: list [int, Callable] = []
        self.sensor_sates: dict = {}
        self.our_session_path: Any | None = None
        self.our_session_interface: Any | None = None
        self.lock_session_interface: Any | None = None
        self.is_session_locked: bool | None = None
        self.our_vt: bool | None = None
        self.our_x11: bool | None = None
        self.session_locked_mode: bool = False
        self.lock_timer: Task | None = None
    
    async def initialize(self):
        """Connecting to D-Bus"""

        try:
            self.bus = MessageBus(bus_type=BusType.SYSTEM)
            await self.bus.connect()
            
            introspection = await self.bus.introspect(
                "org.freedesktop.login1",
                "/org/freedesktop/login1"
            )
            
            self.manager_proxy = self.bus.get_proxy_object(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                introspection
            ).get_interface("org.freedesktop.login1.Manager")
            
            logger.info("IdleManager was initialized")

            return True
            
        except Exception as e:
            logger.error(f"Initialization error IdleManager: {e}")
            return False
    
    async def get_our_session (self) -> tuple[bool, str]:
        """Getting our session"""

        if not self.manager_proxy:
            return (False, "IdleManagers was not initialized")
        
        self.our_session_path = await self._get_current_session_path(self.manager_proxy)
        
        if self.our_session_path is None:
            return (False, "Our session path was not found")
        try:
            session_introspection = await self.bus.introspect(
                "org.freedesktop.login1",
                self.our_session_path
            )
            session_obj = self.bus.get_proxy_object(
                "org.freedesktop.login1",
                self.our_session_path,
                session_introspection
            )
            self.our_session_interface = session_obj.get_interface(
                "org.freedesktop.login1.Session"
            )
        except Exception as e:
            msg = "Getting our session error"
            logger.error(msg, exc_info=e)
            return (False, msg)
        
        return (True, f"Our session: {self.our_session_path}")
    
    # async def get_lock_session(self):
    #     """Getting lightdm locker session"""

    #     sessions = await self.manager_proxy.call_list_sessions()
    #     for session_id, uid, user, seat, session_path in sessions:
    #         if user == "lightdm" and seat == "seat0":
    #             logger.info(
    #                 f"{session_id=}, {uid=}, {user=}, {seat=}, {session_path=}"
    #             )
    #             # Получаем proxy для этой сессии
    #             session_introspection = await self.bus.introspect(
    #                 "org.freedesktop.login1",
    #                 session_path
    #             )
    #             session_obj = self.bus.get_proxy_object(
    #                 "org.freedesktop.login1",
    #                 session_path,
    #                 session_introspection
    #             )
    #             lightdm_session_interface = session_obj.get_interface(
    #                 "org.freedesktop.login1.Session"
    #             )
                
    #             return (lightdm_session_interface, session_path)
    #     return (None, None)

    async def _get_current_session_path(self, manager_interface):
        """Getting current session path"""

        try:
            session_id = os.getenv("XDG_SESSION_ID")
            if session_id:
                return await manager_interface.call_get_session(session_id)
            else:
                pid = os.getpid()
                return await manager_interface.call_get_session_by_pid(pid)

        except Exception as e:
            logger.error(f"Getting current session path error: {e}")
            return None
    
    def add_rule(self, rule_func: Callable, priority: int = 0) -> None:
        """Adding rules"""
        self.rules.append((priority, rule_func))
        self.rules.sort(key=itemgetter(0))
        
    async def handle_sensor_update(self, sensor_name: str, event_type: str, state: str):
        """Updating a sensor state"""

        logger.info(f"Handle sensor {sensor_name}: {event_type} -> {state}")
        self.sensor_sates[sensor_name] = {
                "event_type": event_type,
                "state": state,
            }
        if event_type == "initial":
            if sensor_name == "vt":
                if state == "active":
                    self.our_vt = True
                    self.our_x11 = self.our_vt
                logger.info(f"{self.our_vt=}, {self.our_x11=}")
            if sensor_name == "session_locking":
                self.is_session_locked = (state == "locked")
            return None

        if sensor_name == "vt":
            self.our_vt = (state == "active")
            self.our_x11 = self.our_vt
            
            if not self.our_vt:
                logger.info("Our VT is not active - X11 events are unreliable")
            else:
                logger.info("Our VT is active - X11 events are reliable")
            return
        
        if sensor_name == "session_locking":
            logger.info(f"{sensor_name=}, {state=}, {event_type=}")
            if state == "locked" and event_type == "set":
                await self._execute_locker("set")
                self.session_locked_mode = True
                await self._start_lock_timer()
            elif state == "unlocked":
                self.session_locked_mode = False
                await self._cancel_lock_timer()
                self.lock_session_interface = None
                await self.set_idle(False)
                self.is_session_locked = False
            elif state == "active" and event_type == "yes":
                await self.set_idle(False)
                logger.info("Idle Canceled, check loginctl.")
            else:
                logger.info(f"state={state}, event_type={event_type}")
            return

        if not self.our_x11:
            logger.debug(f"Ignoring {sensor_name} event - X server is not active")
            return
        
        # Screensaver sensor
        logger.info("Applying rules...")
        await self._apply_rules()
        
        # if (sensor_name == "session_locking") and (event_type == "set"):
        #     if state == "lock":
        #         pass
        #     elif state == "unlock":
        #         pass


        # if (sensor_name == "session_locking") and (event_type == "set") and (state == "locked"):
        #     pass
        #     # if state == "locked":
        #     # await self._execute_locker("set")
        # else:
        #     logger.info("Applying rules...")
        #     # await self._apply_rules()
    
    async def _start_lock_timer(self, seconds: int = 60):
        """Starting timer for blocking session"""

        if self.lock_timer:
            self.lock_timer.cancel()
        
        async def lock_timer_task(seconds: int):
            logger.info("Enter to lock time task...")
            await asyncio.sleep(seconds)  # 5 минут
            logger.info("Waiting time finished")
            if self.session_locked_mode:
                logger.info("Session locked for 5 minutes, setting idle")
                await self.set_idle(True)
        
        self.lock_timer = asyncio.create_task(lock_timer_task(seconds))
    
    async def _cancel_lock_timer(self):
        """Cancelnig timer"""

        if self.lock_timer:
            self.lock_timer.cancel()
            self.lock_timer = None

    async def _execute_locker(self, event_type: str) -> None:
        """Execute lock session command"""

        logger.info(f"{self.sensor_sates["session_locking"]=}")
        if self.sensor_sates["session_locking"]["state"] == "locked":
            logger.info("Session is locked -> Return")
            return None
        logger.info("Locking session...")
        try:
            process = await asyncio.create_subprocess_exec(
                "dm-tool", "lock",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode == 0:
                logger.info("Lock session command was run")
                self.is_session_locked = True
                # self.sensor_sates["session_locking"]["state"] = "locked"
                # self.sensor_sates["session_locking"]["event_type"] = event_type
            else:
                logger.error(f"Runnig lock session command error: {stderr.decode()}")
        except Exception as e:
            logger.error(f"Executing lock session command error: {e}")
    
    async def _apply_rules(self) -> None:
        """Apply all rules"""

        if not self.rules:
            return None
        
        for _, rule_func in self.rules:
            try:
                should_idle = rule_func(self.sensor_sates)
                if should_idle is not None:
                    logger.info(f"Applying the rule {rule_func.__name__} ")
                    logger.info(f"{should_idle=}")
                    # await self._execute_locker("dpms")
                    await self.set_idle(should_idle)
                    break
            except Exception as e:
                logger.error(f"Apply rule '{rule_func.__name__}' error", exc_info=e)
        
    async def set_idle(self, idle: bool):
        """Setting idle status"""

        try:
            if self.current_idle == idle:
                logger.info(
                    f"Current idle status: {self.current_idle}. New idle status: {idle}. "
                    "Idle status will not be changed."
                )
                return True
                
            # session_path = await self.manager_proxy.call_get_session_by_pid(os.getpid())
            # if not session_path:
            #     logger.warning("Session is unavailable")
            #     return False
                
            # logger.info(f"Idle manager will try setting idle for session: {session_path}")
            # session_introspection = await self.bus.introspect(
            #     "org.freedesktop.login1",
            #     session_path
            # )
            
            # session_proxy = self.bus.get_proxy_object(
            #     "org.freedesktop.login1",
            #     session_path,
            #     session_introspection
            # ).get_interface("org.freedesktop.login1.Session")
            
            # await session_proxy.call_set_idle_hint(idle)
            # self.lock_session_interface, _ = await self.get_lock_session()
            logger.info("Setting our session to idle")
            await self.our_session_interface.call_set_idle_hint(idle)
            # if self.lock_session_interface is not None:
            #     logger.info("Setting lock session to idle")
            #     await self.lock_session_interface.call_set_idle_hint(idle)
            self.current_idle = idle
            logger.info(f"Idle status was set to: {idle}")
            return True
            
        except Exception as e:
            logger.error(f"Setting idle error: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup and disconneting"""
        if self.bus:
            self.bus.disconnect()
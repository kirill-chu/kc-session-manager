import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LoggerConfig:
    """Logger configuration"""
    
    service_name = "kc-session-manager"
    
    default_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    verbose_format = "%(asctime)s - %(name)s.%(funcName)s:%(lineno)d - %(levelname)s - %(message)s"
    
    _initialized = False
    
    @classmethod
    def setup_logging(
        cls,
        debug: bool = False,
        log_file: str | None = None,
        service_name: str | None = None,
        interactive: bool | None = None,
        verbose: bool | None = None,
    ) -> None:
        """
        Setting up logging
        """

        if cls._initialized:
            return
            
        service_name = service_name or cls.service_name

        current_format = cls.default_format
        if verbose:
            current_format = cls.verbose_format
        
        if debug:
            formatter = logging.Formatter(
                fmt=current_format,
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            log_level = logging.DEBUG
        else:
            formatter = logging.Formatter(
                fmt=current_format,
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            log_level = logging.INFO

        if interactive is None:
            interactive = sys.stdout.isatty()

        handlers = []
        
        if interactive:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            handlers.append(console_handler)

        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        
        if not handlers or not log_file:
            default_log = Path(
                Path.home(),
                ".local/share",
                cls.service_name,
                f"{cls.service_name}.log"
            )
            default_log.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                filename=default_log,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)



        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        for handler in root_logger.handlers.copy():
            root_logger.removeHandler(handler)
        
        for handler in handlers:
            root_logger.addHandler(handler)
        
        service_logger = logging.getLogger(service_name)
        service_logger.setLevel(log_level)
        
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: str | None = None) -> logging.Logger:
        """
        Getting logger for module
        """
        # if not cls._initialized:
        #     cls.setup_logging()
        
        if name is None:

            import inspect
            frame = inspect.currentframe()
            if frame and frame.f_back:
                module = inspect.getmodule(frame.f_back)
                name = module.__name__ if module else "unknown"
            else:
                name = "unknown"
        
        if name == "__main__":
            name = "main"
        
        module_name = name.split(".")[-1]
        logger_name = f"{cls.service_name}.{module_name}"
        
        return logging.getLogger(logger_name)
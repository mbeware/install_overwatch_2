"""
Logging module with stable message IDs for the workstation rebuild tool.
Log messages have IDs that remain constant across different runs and configurations.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional


class MessageID:
    """Stable message IDs for logging. IDs remain constant for internationalization."""
    
    # General messages (1000-1099)
    STARTUP = "WS1000"
    SHUTDOWN = "WS1001"
    CONFIG_LOADED = "WS1002"
    CONFIG_NOT_FOUND = "WS1003"
    CONFIG_ERROR = "WS1004"
    
    # Package scanning messages (1100-1199)
    SCAN_START = "WS1100"
    SCAN_COMPLETE = "WS1101"
    SCAN_APT_START = "WS1110"
    SCAN_APT_COMPLETE = "WS1111"
    SCAN_APT_ERROR = "WS1112"
    SCAN_PIP_START = "WS1120"
    SCAN_PIP_COMPLETE = "WS1121"
    SCAN_PIP_ERROR = "WS1122"
    SCAN_CARGO_START = "WS1130"
    SCAN_CARGO_COMPLETE = "WS1131"
    SCAN_CARGO_ERROR = "WS1132"
    SCAN_FLATPAK_START = "WS1140"
    SCAN_FLATPAK_COMPLETE = "WS1141"
    SCAN_FLATPAK_ERROR = "WS1142"
    SCAN_SNAP_START = "WS1150"
    SCAN_SNAP_COMPLETE = "WS1151"
    SCAN_SNAP_ERROR = "WS1152"
    
    # Config scanning messages (1200-1299)
    CONFIG_SCAN_START = "WS1200"
    CONFIG_SCAN_COMPLETE = "WS1201"
    CONFIG_FILE_FOUND = "WS1210"
    CONFIG_FILE_SKIPPED = "WS1211"
    CONFIG_FILE_ERROR = "WS1212"
    DCONF_DUMP_START = "WS1220"
    DCONF_DUMP_COMPLETE = "WS1221"
    DCONF_DUMP_ERROR = "WS1222"
    
    # Snapshot messages (1300-1399)
    SNAPSHOT_START = "WS1300"
    SNAPSHOT_COMPLETE = "WS1301"
    SNAPSHOT_WRITE_ERROR = "WS1302"
    SNAPSHOT_READ_ERROR = "WS1303"
    
    # Ansible generation messages (1400-1499)
    ANSIBLE_GEN_START = "WS1400"
    ANSIBLE_GEN_COMPLETE = "WS1401"
    ANSIBLE_GEN_ERROR = "WS1402"
    ANSIBLE_TASK_ADDED = "WS1410"
    
    # File operations (1500-1599)
    FILE_COPY_START = "WS1500"
    FILE_COPY_COMPLETE = "WS1501"
    FILE_COPY_ERROR = "WS1502"
    DIR_CREATE = "WS1510"
    DIR_CREATE_ERROR = "WS1511"


class IDFormatter(logging.Formatter):
    """Custom formatter that includes message IDs."""
    
    def format(self, record: logging.LogRecord) -> str:
        msg_id = getattr(record, 'msg_id', 'WS0000')
        record.msg_id = msg_id
        return super().format(record)


class WorkstationLogger:
    """Logger wrapper that ensures message IDs are included in all log messages."""
    
    def __init__(self, name: str, log_file: Optional[Path] = None, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        if not self.logger.handlers:
            formatter = IDFormatter(
                '%(asctime)s [%(msg_id)s] %(levelname)s - %(message)s',
                datefmt='%Y-%m-%dT%H:%M:%S'
            )
            
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            if log_file:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
    
    def _log(self, level: int, msg_id: str, message: str, *args, **kwargs):
        extra = kwargs.pop('extra', {})
        extra['msg_id'] = msg_id
        self.logger.log(level, message, *args, extra=extra, **kwargs)
    
    def debug(self, msg_id: str, message: str, *args, **kwargs):
        self._log(logging.DEBUG, msg_id, message, *args, **kwargs)
    
    def info(self, msg_id: str, message: str, *args, **kwargs):
        self._log(logging.INFO, msg_id, message, *args, **kwargs)
    
    def warning(self, msg_id: str, message: str, *args, **kwargs):
        self._log(logging.WARNING, msg_id, message, *args, **kwargs)
    
    def error(self, msg_id: str, message: str, *args, **kwargs):
        self._log(logging.ERROR, msg_id, message, *args, **kwargs)
    
    def critical(self, msg_id: str, message: str, *args, **kwargs):
        self._log(logging.CRITICAL, msg_id, message, *args, **kwargs)


def get_default_log_path() -> Path:
    """Get the OS-standard log path for the workstation snapshot tool."""
    if os.name == 'posix':
        log_dir = Path('/var/log')
        if not os.access(log_dir, os.W_OK):
            log_dir = Path.home() / '.local' / 'log'
    else:
        log_dir = Path.home() / '.local' / 'log'
    
    return log_dir / 'workstation_snapshot.log'


def create_logger(name: str = 'workstation_snapshot', 
                  log_file: Optional[Path] = None,
                  level: int = logging.INFO) -> WorkstationLogger:
    """Create a logger instance with the specified configuration."""
    if log_file is None:
        log_file = get_default_log_path()
    return WorkstationLogger(name, log_file, level)

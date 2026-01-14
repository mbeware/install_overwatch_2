"""
Configuration loader and validator for the workstation snapshot tool.
Uses TOML format as required by project standards.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        import tomllib


@dataclass
class SnapshotConfig:
    """Configuration for snapshot output."""
    output_dir: Path = field(default_factory=lambda: Path.home() / '.local' / 'share' / 'workstation-snapshot')
    format: str = "json"


@dataclass
class PackagesConfig:
    """Configuration for package scanning."""
    managers: List[str] = field(default_factory=lambda: ["apt", "pip", "cargo", "flatpak", "snap"])
    apt_exclude: List[str] = field(default_factory=list)
    apt_manual_only: bool = True
    pip_user_only: bool = True
    pip_include_global: bool = False


@dataclass
class ConfigsConfig:
    """Configuration for config file scanning."""
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    max_file_size: int = 1048576
    capture_dconf: bool = True
    dconf_paths: List[str] = field(default_factory=lambda: ["/"])


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    level: str = "INFO"
    file: Optional[Path] = None


@dataclass
class AnsibleConfig:
    """Configuration for Ansible playbook generation."""
    output_path: Path = field(default_factory=lambda: Path("./playbook.yml"))
    include_comments: bool = True
    group_by_manager: bool = True


@dataclass
class Config:
    """Main configuration container."""
    snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)
    packages: PackagesConfig = field(default_factory=PackagesConfig)
    configs: ConfigsConfig = field(default_factory=ConfigsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ansible: AnsibleConfig = field(default_factory=AnsibleConfig)


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in a path string."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load configuration from a TOML file.
    
    Args:
        config_path: Path to the config file. If None, uses default locations.
    
    Returns:
        Config object with loaded settings.
    
    Raises:
        FileNotFoundError: If config file doesn't exist and no defaults available.
        ValueError: If config file is invalid.
    """
    if config_path is None:
        default_locations = [
            Path.home() / '.config' / 'workstation-snapshot' / 'config.toml',
            Path('/etc/workstation-snapshot/config.toml'),
            Path(__file__).parent.parent / 'config' / 'snapshot_config.toml',
        ]
        for loc in default_locations:
            if loc.exists():
                config_path = loc
                break
    
    if config_path is None or not config_path.exists():
        return Config()
    
    with open(config_path, 'rb') as f:
        data = tomllib.load(f)
    
    config = Config()
    
    if 'snapshot' in data:
        snap = data['snapshot']
        if 'output_dir' in snap:
            config.snapshot.output_dir = expand_path(snap['output_dir'])
        if 'format' in snap:
            config.snapshot.format = snap['format']
    
    if 'packages' in data:
        pkg = data['packages']
        if 'managers' in pkg:
            config.packages.managers = pkg['managers']
        if 'apt_exclude' in pkg:
            config.packages.apt_exclude = pkg['apt_exclude']
        if 'apt_manual_only' in pkg:
            config.packages.apt_manual_only = pkg['apt_manual_only']
        if 'pip_user_only' in pkg:
            config.packages.pip_user_only = pkg['pip_user_only']
        if 'pip_include_global' in pkg:
            config.packages.pip_include_global = pkg['pip_include_global']
    
    if 'configs' in data:
        cfg = data['configs']
        if 'include' in cfg:
            config.configs.include = cfg['include']
        if 'exclude' in cfg:
            config.configs.exclude = cfg['exclude']
        if 'max_file_size' in cfg:
            config.configs.max_file_size = cfg['max_file_size']
        if 'capture_dconf' in cfg:
            config.configs.capture_dconf = cfg['capture_dconf']
        if 'dconf_paths' in cfg:
            config.configs.dconf_paths = cfg['dconf_paths']
    
    if 'logging' in data:
        log = data['logging']
        if 'level' in log:
            config.logging.level = log['level']
        if 'file' in log and log['file']:
            config.logging.file = expand_path(log['file'])
    
    if 'ansible' in data:
        ans = data['ansible']
        if 'output_path' in ans:
            config.ansible.output_path = expand_path(ans['output_path'])
        if 'include_comments' in ans:
            config.ansible.include_comments = ans['include_comments']
        if 'group_by_manager' in ans:
            config.ansible.group_by_manager = ans['group_by_manager']
    
    return config


def get_default_config_path() -> Path:
    """Get the path to the default config file shipped with the tool."""
    return Path(__file__).parent.parent / 'config' / 'snapshot_config.toml'

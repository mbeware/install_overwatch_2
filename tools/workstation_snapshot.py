#!/usr/bin/env python3
"""
Workstation Snapshot Tool

Captures the current state of a workstation including:
- Installed packages (apt, pip, cargo, flatpak, snap)
- User configuration files
- Desktop settings (dconf)

Outputs a JSON snapshot that can be used to generate Ansible playbooks
for recreating the workstation state.
"""

import argparse
import base64
import fnmatch
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from lib.config import Config, load_config, get_default_config_path
from lib.logger import MessageID, WorkstationLogger, create_logger, get_default_log_path


@dataclass
class PackageInfo:
    """Information about an installed package."""
    name: str
    version: Optional[str] = None
    manager: str = ""
    source: Optional[str] = None


@dataclass
class ConfigFile:
    """Information about a configuration file."""
    path: str
    content: Optional[str] = None
    is_binary: bool = False
    size: int = 0
    mode: Optional[int] = None


@dataclass
class Snapshot:
    """Complete workstation snapshot."""
    timestamp: str = ""
    hostname: str = ""
    username: str = ""
    packages: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    configs: List[Dict[str, Any]] = field(default_factory=list)
    dconf: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PackageScanner:
    """Scans for installed packages across different package managers."""
    
    def __init__(self, config: Config, logger: WorkstationLogger):
        self.config = config
        self.logger = logger
    
    def scan_all(self) -> Dict[str, List[PackageInfo]]:
        """Scan all configured package managers."""
        results: Dict[str, List[PackageInfo]] = {}
        
        self.logger.info(MessageID.SCAN_START, "Starting package scan")
        
        for manager in self.config.packages.managers:
            scanner_method = getattr(self, f'scan_{manager}', None)
            if scanner_method:
                try:
                    packages = scanner_method()
                    results[manager] = packages
                except Exception as e:
                    self.logger.error(
                        getattr(MessageID, f'SCAN_{manager.upper()}_ERROR', MessageID.SCAN_APT_ERROR),
                        f"Error scanning {manager}: {e}"
                    )
                    results[manager] = []
            else:
                self.logger.warning(MessageID.SCAN_START, f"Unknown package manager: {manager}")
        
        self.logger.info(MessageID.SCAN_COMPLETE, "Package scan complete")
        return results
    
    def scan_apt(self) -> List[PackageInfo]:
        """Scan for installed APT packages."""
        self.logger.info(MessageID.SCAN_APT_START, "Scanning APT packages")
        
        if not shutil.which('apt-mark'):
            self.logger.warning(MessageID.SCAN_APT_ERROR, "apt-mark not found, skipping APT scan")
            return []
        
        packages = []
        
        try:
            if self.config.packages.apt_manual_only:
                result = subprocess.run(
                    ['apt-mark', 'showmanual'],
                    capture_output=True, text=True, check=True
                )
                package_names = result.stdout.strip().split('\n')
            else:
                result = subprocess.run(
                    ['dpkg-query', '-W', '-f=${Package}\n'],
                    capture_output=True, text=True, check=True
                )
                package_names = result.stdout.strip().split('\n')
            
            exclude_patterns = self.config.packages.apt_exclude
            
            for name in package_names:
                name = name.strip()
                if not name:
                    continue
                
                excluded = False
                for pattern in exclude_patterns:
                    if re.match(pattern, name):
                        excluded = True
                        break
                
                if not excluded:
                    version = self._get_apt_version(name)
                    packages.append(PackageInfo(name=name, version=version, manager='apt'))
            
            self.logger.info(MessageID.SCAN_APT_COMPLETE, f"Found {len(packages)} APT packages")
        
        except subprocess.CalledProcessError as e:
            self.logger.error(MessageID.SCAN_APT_ERROR, f"APT scan failed: {e}")
        
        return packages
    
    def _get_apt_version(self, package_name: str) -> Optional[str]:
        """Get the installed version of an APT package."""
        try:
            result = subprocess.run(
                ['dpkg-query', '-W', '-f=${Version}', package_name],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
    
    def scan_pip(self) -> List[PackageInfo]:
        """Scan for installed pip packages."""
        self.logger.info(MessageID.SCAN_PIP_START, "Scanning pip packages")
        
        pip_cmd = 'pip3' if shutil.which('pip3') else 'pip'
        if not shutil.which(pip_cmd):
            self.logger.warning(MessageID.SCAN_PIP_ERROR, "pip not found, skipping pip scan")
            return []
        
        packages = []
        
        try:
            cmd = [pip_cmd, 'list', '--format=json']
            if self.config.packages.pip_user_only and not self.config.packages.pip_include_global:
                cmd.append('--user')
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            pip_packages = json.loads(result.stdout)
            
            for pkg in pip_packages:
                packages.append(PackageInfo(
                    name=pkg['name'],
                    version=pkg.get('version'),
                    manager='pip'
                ))
            
            self.logger.info(MessageID.SCAN_PIP_COMPLETE, f"Found {len(packages)} pip packages")
        
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            self.logger.error(MessageID.SCAN_PIP_ERROR, f"pip scan failed: {e}")
        
        return packages
    
    def scan_cargo(self) -> List[PackageInfo]:
        """Scan for installed Cargo packages."""
        self.logger.info(MessageID.SCAN_CARGO_START, "Scanning Cargo packages")
        
        if not shutil.which('cargo'):
            self.logger.warning(MessageID.SCAN_CARGO_ERROR, "cargo not found, skipping Cargo scan")
            return []
        
        packages = []
        cargo_bin = Path.home() / '.cargo' / 'bin'
        
        if cargo_bin.exists():
            try:
                result = subprocess.run(
                    ['cargo', 'install', '--list'],
                    capture_output=True, text=True, check=True
                )
                
                current_package = None
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    
                    if not line.startswith(' ') and ':' not in line:
                        match = re.match(r'^(\S+)\s+v?([\d.]+)', line)
                        if match:
                            packages.append(PackageInfo(
                                name=match.group(1),
                                version=match.group(2),
                                manager='cargo'
                            ))
                
                self.logger.info(MessageID.SCAN_CARGO_COMPLETE, f"Found {len(packages)} Cargo packages")
            
            except subprocess.CalledProcessError as e:
                self.logger.error(MessageID.SCAN_CARGO_ERROR, f"Cargo scan failed: {e}")
        
        return packages
    
    def scan_flatpak(self) -> List[PackageInfo]:
        """Scan for installed Flatpak applications."""
        self.logger.info(MessageID.SCAN_FLATPAK_START, "Scanning Flatpak packages")
        
        if not shutil.which('flatpak'):
            self.logger.warning(MessageID.SCAN_FLATPAK_ERROR, "flatpak not found, skipping Flatpak scan")
            return []
        
        packages = []
        
        try:
            result = subprocess.run(
                ['flatpak', 'list', '--app', '--columns=application,version,origin'],
                capture_output=True, text=True, check=True
            )
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 1:
                    packages.append(PackageInfo(
                        name=parts[0],
                        version=parts[1] if len(parts) > 1 else None,
                        manager='flatpak',
                        source=parts[2] if len(parts) > 2 else 'flathub'
                    ))
            
            self.logger.info(MessageID.SCAN_FLATPAK_COMPLETE, f"Found {len(packages)} Flatpak packages")
        
        except subprocess.CalledProcessError as e:
            self.logger.error(MessageID.SCAN_FLATPAK_ERROR, f"Flatpak scan failed: {e}")
        
        return packages
    
    def scan_snap(self) -> List[PackageInfo]:
        """Scan for installed Snap packages."""
        self.logger.info(MessageID.SCAN_SNAP_START, "Scanning Snap packages")
        
        if not shutil.which('snap'):
            self.logger.warning(MessageID.SCAN_SNAP_ERROR, "snap not found, skipping Snap scan")
            return []
        
        packages = []
        
        try:
            result = subprocess.run(
                ['snap', 'list'],
                capture_output=True, text=True, check=True
            )
            
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    if parts[0] in ('core', 'core18', 'core20', 'core22', 'snapd'):
                        continue
                    packages.append(PackageInfo(
                        name=parts[0],
                        version=parts[1] if len(parts) > 1 else None,
                        manager='snap'
                    ))
            
            self.logger.info(MessageID.SCAN_SNAP_COMPLETE, f"Found {len(packages)} Snap packages")
        
        except subprocess.CalledProcessError as e:
            self.logger.error(MessageID.SCAN_SNAP_ERROR, f"Snap scan failed: {e}")
        
        return packages


class ConfigScanner:
    """Scans for user configuration files."""
    
    def __init__(self, config: Config, logger: WorkstationLogger):
        self.config = config
        self.logger = logger
        self.home = Path.home()
    
    def scan_all(self) -> List[ConfigFile]:
        """Scan all configured config paths."""
        self.logger.info(MessageID.CONFIG_SCAN_START, "Starting config scan")
        
        configs = []
        
        for include_path in self.config.configs.include:
            full_path = self.home / include_path
            
            if full_path.is_file():
                config_file = self._scan_file(full_path)
                if config_file:
                    configs.append(config_file)
            elif full_path.is_dir():
                configs.extend(self._scan_directory(full_path))
            else:
                self.logger.debug(MessageID.CONFIG_FILE_SKIPPED, f"Path not found: {full_path}")
        
        self.logger.info(MessageID.CONFIG_SCAN_COMPLETE, f"Found {len(configs)} config files")
        return configs
    
    def _scan_file(self, path: Path) -> Optional[ConfigFile]:
        """Scan a single config file."""
        try:
            rel_path = str(path.relative_to(self.home))
            
            if self._is_excluded(rel_path):
                self.logger.debug(MessageID.CONFIG_FILE_SKIPPED, f"Excluded: {rel_path}")
                return None
            
            stat = path.stat()
            size = stat.st_size
            
            if self.config.configs.max_file_size > 0 and size > self.config.configs.max_file_size:
                self.logger.debug(MessageID.CONFIG_FILE_SKIPPED, f"File too large: {rel_path} ({size} bytes)")
                return None
            
            try:
                content = path.read_text()
                is_binary = False
            except UnicodeDecodeError:
                content = base64.b64encode(path.read_bytes()).decode('ascii')
                is_binary = True
            
            self.logger.debug(MessageID.CONFIG_FILE_FOUND, f"Found config: {rel_path}")
            
            return ConfigFile(
                path=rel_path,
                content=content,
                is_binary=is_binary,
                size=size,
                mode=stat.st_mode & 0o777
            )
        
        except Exception as e:
            self.logger.error(MessageID.CONFIG_FILE_ERROR, f"Error reading {path}: {e}")
            return None
    
    def _scan_directory(self, path: Path) -> List[ConfigFile]:
        """Recursively scan a directory for config files."""
        configs = []
        
        try:
            for item in path.rglob('*'):
                if item.is_file():
                    config_file = self._scan_file(item)
                    if config_file:
                        configs.append(config_file)
        except Exception as e:
            self.logger.error(MessageID.CONFIG_FILE_ERROR, f"Error scanning directory {path}: {e}")
        
        return configs
    
    def _is_excluded(self, rel_path: str) -> bool:
        """Check if a path matches any exclusion pattern."""
        for pattern in self.config.configs.exclude:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if fnmatch.fnmatch('/' + rel_path, pattern):
                return True
        return False
    
    def scan_dconf(self) -> Optional[str]:
        """Dump dconf settings."""
        if not self.config.configs.capture_dconf:
            return None
        
        self.logger.info(MessageID.DCONF_DUMP_START, "Dumping dconf settings")
        
        if not shutil.which('dconf'):
            self.logger.warning(MessageID.DCONF_DUMP_ERROR, "dconf not found, skipping dconf dump")
            return None
        
        try:
            dconf_dumps = []
            for dconf_path in self.config.configs.dconf_paths:
                result = subprocess.run(
                    ['dconf', 'dump', dconf_path],
                    capture_output=True, text=True, check=True
                )
                if result.stdout.strip():
                    dconf_dumps.append(f"# dconf dump {dconf_path}\n{result.stdout}")
            
            combined = '\n'.join(dconf_dumps)
            self.logger.info(MessageID.DCONF_DUMP_COMPLETE, f"dconf dump complete ({len(combined)} bytes)")
            return combined
        
        except subprocess.CalledProcessError as e:
            self.logger.error(MessageID.DCONF_DUMP_ERROR, f"dconf dump failed: {e}")
            return None


class WorkstationSnapshot:
    """Main class for creating workstation snapshots."""
    
    def __init__(self, config: Config, logger: WorkstationLogger):
        self.config = config
        self.logger = logger
        self.package_scanner = PackageScanner(config, logger)
        self.config_scanner = ConfigScanner(config, logger)
    
    def create_snapshot(self) -> Snapshot:
        """Create a complete workstation snapshot."""
        self.logger.info(MessageID.SNAPSHOT_START, "Creating workstation snapshot")
        
        snapshot = Snapshot(
            timestamp=datetime.now().isoformat(),
            hostname=os.uname().nodename,
            username=os.getenv('USER', 'unknown'),
            metadata={
                'os_release': self._get_os_release(),
                'kernel': os.uname().release,
                'tool_version': '1.0.0'
            }
        )
        
        packages = self.package_scanner.scan_all()
        snapshot.packages = {
            manager: [asdict(pkg) for pkg in pkgs]
            for manager, pkgs in packages.items()
        }
        
        configs = self.config_scanner.scan_all()
        snapshot.configs = [asdict(cfg) for cfg in configs]
        
        snapshot.dconf = self.config_scanner.scan_dconf()
        
        self.logger.info(MessageID.SNAPSHOT_COMPLETE, "Snapshot creation complete")
        return snapshot
    
    def _get_os_release(self) -> Dict[str, str]:
        """Get OS release information."""
        os_release = {}
        os_release_path = Path('/etc/os-release')
        
        if os_release_path.exists():
            for line in os_release_path.read_text().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    os_release[key] = value.strip('"')
        
        return os_release
    
    def save_snapshot(self, snapshot: Snapshot, output_path: Optional[Path] = None) -> Path:
        """Save snapshot to a file."""
        if output_path is None:
            output_dir = self.config.snapshot.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = output_dir / f'snapshot_{timestamp}.json'
        
        try:
            with open(output_path, 'w') as f:
                json.dump(asdict(snapshot), f, indent=2)
            
            self.logger.info(MessageID.SNAPSHOT_COMPLETE, f"Snapshot saved to {output_path}")
            return output_path
        
        except Exception as e:
            self.logger.error(MessageID.SNAPSHOT_WRITE_ERROR, f"Failed to save snapshot: {e}")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Create a snapshot of the current workstation state'
    )
    parser.add_argument(
        '-c', '--config',
        type=Path,
        help='Path to configuration file'
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output path for snapshot file'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--packages-only',
        action='store_true',
        help='Only scan packages, skip configs'
    )
    parser.add_argument(
        '--configs-only',
        action='store_true',
        help='Only scan configs, skip packages'
    )
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    log_level = logging.DEBUG if args.verbose else getattr(logging, config.logging.level)
    logger = create_logger(level=log_level, log_file=config.logging.file)
    
    logger.info(MessageID.STARTUP, "Workstation Snapshot Tool starting")
    
    if args.config:
        logger.info(MessageID.CONFIG_LOADED, f"Loaded config from {args.config}")
    
    snapshot_tool = WorkstationSnapshot(config, logger)
    
    if args.packages_only:
        config.configs.include = []
        config.configs.capture_dconf = False
    elif args.configs_only:
        config.packages.managers = []
    
    snapshot = snapshot_tool.create_snapshot()
    output_path = snapshot_tool.save_snapshot(snapshot, args.output)
    
    print(f"Snapshot saved to: {output_path}")
    
    total_packages = sum(len(pkgs) for pkgs in snapshot.packages.values())
    print(f"Total packages: {total_packages}")
    print(f"Config files: {len(snapshot.configs)}")
    
    logger.info(MessageID.SHUTDOWN, "Workstation Snapshot Tool finished")


if __name__ == '__main__':
    main()

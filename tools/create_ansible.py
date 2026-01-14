#!/usr/bin/env python3
"""
Ansible Playbook Generator

Generates Ansible playbooks from workstation snapshots or install_overwatch logs.
Uses proper Ansible modules instead of shell commands where possible.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from lib.config import Config, load_config
from lib.logger import MessageID, WorkstationLogger, create_logger


@dataclass
class AnsibleTask:
    """Represents a single Ansible task."""
    name: str
    module: str
    args: Dict[str, Any] = field(default_factory=dict)
    become: bool = False
    become_user: Optional[str] = None
    when: Optional[str] = None
    loop: Optional[List[str]] = None
    loop_var: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    tags: List[str] = field(default_factory=list)


class PlaybookGenerator:
    """Generates Ansible playbooks from snapshots or logs."""
    
    def __init__(self, config: Config, logger: WorkstationLogger):
        self.config = config
        self.logger = logger
        self.tasks: List[AnsibleTask] = []
    
    def load_snapshot(self, snapshot_path: Path) -> Dict[str, Any]:
        """Load a snapshot file."""
        self.logger.info(MessageID.ANSIBLE_GEN_START, f"Loading snapshot from {snapshot_path}")
        
        with open(snapshot_path) as f:
            return json.load(f)
    
    def generate_from_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """Generate a complete Ansible playbook from a snapshot."""
        self.logger.info(MessageID.ANSIBLE_GEN_START, "Generating Ansible playbook from snapshot")
        
        self.tasks = []
        
        self._add_apt_tasks(snapshot.get('packages', {}).get('apt', []))
        self._add_pip_tasks(snapshot.get('packages', {}).get('pip', []))
        self._add_cargo_tasks(snapshot.get('packages', {}).get('cargo', []))
        self._add_flatpak_tasks(snapshot.get('packages', {}).get('flatpak', []))
        self._add_snap_tasks(snapshot.get('packages', {}).get('snap', []))
        
        self._add_config_tasks(snapshot.get('configs', []))
        
        if snapshot.get('dconf'):
            self._add_dconf_tasks(snapshot['dconf'])
        
        playbook = self._render_playbook(snapshot)
        
        self.logger.info(MessageID.ANSIBLE_GEN_COMPLETE, f"Generated playbook with {len(self.tasks)} tasks")
        return playbook
    
    def _add_apt_tasks(self, packages: List[Dict[str, Any]]):
        """Add APT package installation tasks."""
        if not packages:
            return
        
        package_names = [pkg['name'] for pkg in packages]
        
        self.tasks.append(AnsibleTask(
            name="Update apt cache",
            module="ansible.builtin.apt",
            args={"update_cache": True, "cache_valid_time": 3600},
            become=True,
            tags=["apt", "packages"]
        ))
        
        if self.config.ansible.group_by_manager:
            self.tasks.append(AnsibleTask(
                name="Install APT packages",
                module="ansible.builtin.apt",
                args={
                    "name": package_names,
                    "state": "present"
                },
                become=True,
                tags=["apt", "packages"]
            ))
            self.logger.info(MessageID.ANSIBLE_TASK_ADDED, f"Added APT task for {len(package_names)} packages")
        else:
            for pkg in packages:
                self.tasks.append(AnsibleTask(
                    name=f"Install APT package: {pkg['name']}",
                    module="ansible.builtin.apt",
                    args={
                        "name": pkg['name'],
                        "state": "present"
                    },
                    become=True,
                    tags=["apt", "packages"]
                ))
    
    def _add_pip_tasks(self, packages: List[Dict[str, Any]]):
        """Add pip package installation tasks."""
        if not packages:
            return
        
        package_specs = []
        for pkg in packages:
            if pkg.get('version'):
                package_specs.append(f"{pkg['name']}=={pkg['version']}")
            else:
                package_specs.append(pkg['name'])
        
        if self.config.ansible.group_by_manager:
            self.tasks.append(AnsibleTask(
                name="Install pip packages",
                module="ansible.builtin.pip",
                args={
                    "name": package_specs,
                    "state": "present",
                    "extra_args": "--user"
                },
                tags=["pip", "packages"]
            ))
            self.logger.info(MessageID.ANSIBLE_TASK_ADDED, f"Added pip task for {len(package_specs)} packages")
        else:
            for pkg in packages:
                spec = f"{pkg['name']}=={pkg['version']}" if pkg.get('version') else pkg['name']
                self.tasks.append(AnsibleTask(
                    name=f"Install pip package: {pkg['name']}",
                    module="ansible.builtin.pip",
                    args={
                        "name": spec,
                        "state": "present",
                        "extra_args": "--user"
                    },
                    tags=["pip", "packages"]
                ))
    
    def _add_cargo_tasks(self, packages: List[Dict[str, Any]]):
        """Add Cargo package installation tasks."""
        if not packages:
            return
        
        self.tasks.append(AnsibleTask(
            name="Ensure cargo is installed",
            module="ansible.builtin.shell",
            args={
                "cmd": "which cargo || curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                "creates": "{{ ansible_env.HOME }}/.cargo/bin/cargo"
            },
            tags=["cargo", "packages"]
        ))
        
        for pkg in packages:
            self.tasks.append(AnsibleTask(
                name=f"Install Cargo package: {pkg['name']}",
                module="ansible.builtin.shell",
                args={
                    "cmd": f"cargo install {pkg['name']}",
                    "creates": f"{{{{ ansible_env.HOME }}}}/.cargo/bin/{pkg['name']}"
                },
                environment={
                    "PATH": "{{ ansible_env.HOME }}/.cargo/bin:{{ ansible_env.PATH }}"
                },
                tags=["cargo", "packages"]
            ))
        
        self.logger.info(MessageID.ANSIBLE_TASK_ADDED, f"Added Cargo tasks for {len(packages)} packages")
    
    def _add_flatpak_tasks(self, packages: List[Dict[str, Any]]):
        """Add Flatpak package installation tasks."""
        if not packages:
            return
        
        self.tasks.append(AnsibleTask(
            name="Ensure Flatpak is installed",
            module="ansible.builtin.apt",
            args={
                "name": "flatpak",
                "state": "present"
            },
            become=True,
            tags=["flatpak", "packages"]
        ))
        
        self.tasks.append(AnsibleTask(
            name="Add Flathub repository",
            module="ansible.builtin.shell",
            args={
                "cmd": "flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo"
            },
            become=True,
            tags=["flatpak", "packages"]
        ))
        
        for pkg in packages:
            source = pkg.get('source', 'flathub')
            self.tasks.append(AnsibleTask(
                name=f"Install Flatpak: {pkg['name']}",
                module="community.general.flatpak",
                args={
                    "name": pkg['name'],
                    "state": "present",
                    "remote": source
                },
                become=True,
                tags=["flatpak", "packages"]
            ))
        
        self.logger.info(MessageID.ANSIBLE_TASK_ADDED, f"Added Flatpak tasks for {len(packages)} packages")
    
    def _add_snap_tasks(self, packages: List[Dict[str, Any]]):
        """Add Snap package installation tasks."""
        if not packages:
            return
        
        self.tasks.append(AnsibleTask(
            name="Ensure snapd is installed",
            module="ansible.builtin.apt",
            args={
                "name": "snapd",
                "state": "present"
            },
            become=True,
            tags=["snap", "packages"]
        ))
        
        for pkg in packages:
            self.tasks.append(AnsibleTask(
                name=f"Install Snap: {pkg['name']}",
                module="community.general.snap",
                args={
                    "name": pkg['name'],
                    "state": "present"
                },
                become=True,
                tags=["snap", "packages"]
            ))
        
        self.logger.info(MessageID.ANSIBLE_TASK_ADDED, f"Added Snap tasks for {len(packages)} packages")
    
    def _add_config_tasks(self, configs: List[Dict[str, Any]]):
        """Add configuration file restoration tasks."""
        if not configs:
            return
        
        config_dirs = list(set(str(Path(cfg['path']).parent) for cfg in configs if '/' in cfg['path']))
        if config_dirs:
            self.tasks.append(AnsibleTask(
                name="Create config directories",
                module="ansible.builtin.file",
                args={
                    "path": "{{ ansible_env.HOME }}/{{ item }}",
                    "state": "directory",
                    "mode": "0755"
                },
                loop=config_dirs,
                loop_var="item",
                tags=["configs"]
            ))
        
        for cfg in configs:
            if cfg.get('is_binary'):
                self.tasks.append(AnsibleTask(
                    name=f"Restore config (binary): {cfg['path']}",
                    module="ansible.builtin.copy",
                    args={
                        "content": "{{ lookup('pipe', 'echo " + cfg['content'] + " | base64 -d') }}",
                        "dest": f"{{{{ ansible_env.HOME }}}}/{cfg['path']}",
                        "mode": cfg.get('mode', '0644')
                    },
                    tags=["configs"]
                ))
            else:
                self.tasks.append(AnsibleTask(
                    name=f"Restore config: {cfg['path']}",
                    module="ansible.builtin.copy",
                    args={
                        "content": cfg.get('content', ''),
                        "dest": f"{{{{ ansible_env.HOME }}}}/{cfg['path']}",
                        "mode": cfg.get('mode', '0644')
                    },
                    tags=["configs"]
                ))
        
        self.logger.info(MessageID.ANSIBLE_TASK_ADDED, f"Added config tasks for {len(configs)} files")
    
    def _add_dconf_tasks(self, dconf_content: str):
        """Add dconf restoration tasks."""
        self.tasks.append(AnsibleTask(
            name="Create dconf restore file",
            module="ansible.builtin.copy",
            args={
                "content": dconf_content,
                "dest": "{{ ansible_env.HOME }}/.config/dconf_restore.ini",
                "mode": "0644"
            },
            tags=["dconf", "desktop"]
        ))
        
        self.tasks.append(AnsibleTask(
            name="Restore dconf settings",
            module="ansible.builtin.shell",
            args={
                "cmd": "cat {{ ansible_env.HOME }}/.config/dconf_restore.ini | dconf load /"
            },
            tags=["dconf", "desktop"]
        ))
        
        self.logger.info(MessageID.ANSIBLE_TASK_ADDED, "Added dconf restoration tasks")
    
    def _render_playbook(self, snapshot: Dict[str, Any]) -> str:
        """Render the complete playbook as YAML."""
        lines = []
        
        if self.config.ansible.include_comments:
            lines.append(f"# Ansible playbook generated from workstation snapshot")
            lines.append(f"# Generated: {datetime.now().isoformat()}")
            lines.append(f"# Source: {snapshot.get('hostname', 'unknown')}")
            lines.append(f"# User: {snapshot.get('username', 'unknown')}")
            lines.append("")
        
        lines.append("---")
        lines.append("- name: Restore workstation configuration")
        lines.append("  hosts: localhost")
        lines.append("  connection: local")
        lines.append("  gather_facts: true")
        lines.append("")
        lines.append("  vars:")
        lines.append(f"    target_user: \"{{{{ ansible_user_id }}}}\"")
        lines.append("")
        lines.append("  tasks:")
        
        for task in self.tasks:
            lines.append("")
            lines.append(f"    - name: {task.name}")
            lines.append(f"      {task.module}:")
            
            for key, value in task.args.items():
                if isinstance(value, list):
                    lines.append(f"        {key}:")
                    for item in value:
                        lines.append(f"          - \"{item}\"")
                elif isinstance(value, bool):
                    lines.append(f"        {key}: {str(value).lower()}")
                elif isinstance(value, str) and '\n' in value:
                    lines.append(f"        {key}: |")
                    for line in value.split('\n'):
                        lines.append(f"          {line}")
                else:
                    if isinstance(value, str) and ('{{' in value or ':' in value or '"' in value):
                        lines.append(f"        {key}: \"{value}\"")
                    else:
                        lines.append(f"        {key}: {value}")
            
            if task.become:
                lines.append(f"      become: true")
            if task.become_user:
                lines.append(f"      become_user: {task.become_user}")
            if task.when:
                lines.append(f"      when: {task.when}")
            if task.loop:
                lines.append(f"      loop:")
                for item in task.loop:
                    lines.append(f"        - \"{item}\"")
            if task.loop_var:
                lines.append(f"      loop_control:")
                lines.append(f"        loop_var: {task.loop_var}")
            if task.environment:
                lines.append(f"      environment:")
                for key, value in task.environment.items():
                    lines.append(f"        {key}: \"{value}\"")
            if task.tags:
                lines.append(f"      tags: [{', '.join(task.tags)}]")
        
        lines.append("")
        return '\n'.join(lines)
    
    def generate_from_logs(self, log_path: Path) -> str:
        """Generate playbook from install_overwatch logs (legacy support)."""
        self.logger.info(MessageID.ANSIBLE_GEN_START, f"Generating playbook from logs: {log_path}")
        
        package_events: Dict[str, List[tuple]] = defaultdict(list)
        
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                match = re.match(r'^(\S+)\s+(\w+)\s+command:\s+(.+)$', line)
                if not match:
                    continue
                
                timestamp_str, manager, command = match.groups()
                
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except ValueError:
                    continue
                
                action = None
                if re.search(r'\binstall\b', command):
                    action = 'install'
                elif re.search(r'\b(remove|uninstall)\b', command):
                    action = 'remove'
                else:
                    continue
                
                packages = self._extract_packages_from_command(manager, command)
                
                for pkg in packages:
                    package_events[pkg].append((timestamp, action, manager, command))
        
        final_packages: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        for pkg, events in package_events.items():
            events.sort(key=lambda x: x[0])
            
            active = False
            last_manager = None
            
            for timestamp, action, manager, command in events:
                if action == 'install':
                    active = True
                    last_manager = manager
                elif action == 'remove':
                    active = False
            
            if active and last_manager:
                final_packages[last_manager.lower()].append({'name': pkg})
        
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'hostname': os.uname().nodename,
            'username': os.getenv('USER', 'unknown'),
            'packages': dict(final_packages),
            'configs': [],
            'dconf': None
        }
        
        return self.generate_from_snapshot(snapshot)
    
    def _extract_packages_from_command(self, manager: str, command: str) -> List[str]:
        """Extract package names from a command string."""
        packages = []
        
        if manager == 'APT':
            match = re.findall(r'apt(?:-get)?\s+(?:install|remove)\s+(?:-y\s+)?([\w\-\.]+)', command)
            packages = match
        elif manager == 'PIP':
            match = re.findall(r'pip(?:3)?\s+(?:install|uninstall)\s+([\w\-\.]+)', command)
            packages = match
        elif manager == 'CARGO':
            match = re.findall(r'cargo\s+(?:install|uninstall)\s+([\w\-\.]+)', command)
            packages = match
        elif manager == 'FLATPAK':
            match = re.findall(r'flatpak\s+(?:install|remove)\s+.*?([\w\.]+/[\w\.]+)', command)
            packages = match
        
        return packages
    
    def save_playbook(self, playbook: str, output_path: Optional[Path] = None) -> Path:
        """Save the generated playbook to a file."""
        if output_path is None:
            output_path = self.config.ansible.output_path
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            f.write(playbook)
        
        self.logger.info(MessageID.ANSIBLE_GEN_COMPLETE, f"Playbook saved to {output_path}")
        return output_path


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate Ansible playbook from workstation snapshot or logs'
    )
    parser.add_argument(
        'input',
        type=Path,
        help='Path to snapshot JSON file or install_overwatch log file'
    )
    parser.add_argument(
        '-c', '--config',
        type=Path,
        help='Path to configuration file'
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output path for generated playbook'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--from-logs',
        action='store_true',
        help='Input is an install_overwatch log file instead of a snapshot'
    )
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    import logging
    log_level = logging.DEBUG if args.verbose else getattr(logging, config.logging.level)
    logger = create_logger(level=log_level, log_file=config.logging.file)
    
    logger.info(MessageID.STARTUP, "Ansible Playbook Generator starting")
    
    generator = PlaybookGenerator(config, logger)
    
    if args.from_logs:
        playbook = generator.generate_from_logs(args.input)
    else:
        snapshot = generator.load_snapshot(args.input)
        playbook = generator.generate_from_snapshot(snapshot)
    
    output_path = generator.save_playbook(playbook, args.output)
    
    print(f"Playbook generated: {output_path}")
    
    logger.info(MessageID.SHUTDOWN, "Ansible Playbook Generator finished")


if __name__ == '__main__':
    main()

# *install_overwatch*

A tool to monitor software installations on Unix workstations and generate Ansible playbooks to recreate the system state on new machines.

## Table of Contents

1. [Overview](#overview)
2. [News](#news)
3. [Installation](#installation)
4. [Uninstallation](#uninstallation)
5. [Capturing Existing Installed Applications](#capturing-existing-installed-applications)
6. [Capturing New Installations After Setup](#capturing-new-installations-after-setup)
7. [Generating an Ansible Playbook](#generating-an-ansible-playbook)
8. [Using the Ansible Playbook on a New Computer](#using-the-ansible-playbook-on-a-new-computer)
9. [How It Works Behind the Curtain](#how-it-works-behind-the-curtain)
10. [Configuration](#configuration)
11. [Troubleshooting](#troubleshooting)
12. [Todo](#todo)

## Overview

*install_overwatch* solves a common problem: you've spent months or years customizing your workstation with various packages, tools, and configurations. When it's time to set up a new machine, you can't remember everything you installed.

This tool provides two complementary approaches. First, it can take a snapshot of your current system to capture all installed packages and configurations, even if *install_overwatch* wasn't previously installed. Second, once installed, it continuously monitors all package installations (apt, pip, cargo, flatpak) and curl downloads, logging them for future reference.

The captured data can then be used to generate Ansible playbooks that recreate your workstation configuration on a new machine.

## News

### 2025-01 : Big cleanup and update

I was setting up some new workstations and VMs and I wasn't able to use *install_overwatch* to create playbooks. I started to install stuff manually, create scripts and in the end, I had as many different installation as I has computer (real or vm). So, It was time to create the officials playbooks for mbeware_baseenv,  mbeware_workstation, mbeware_dev_server and mbeware_service_server. And since *install_overwatch* wasnt re-installed when I had to reinstall my OS (nor were the logs of what was install preserved) I had to start from scratch.

what was done:

1. Create a new repo, and keep only relevant files. Gone are the prototypes and experimentations.
2. Update the existings scripts with changes that were not commited (or even on a dev computer. Code changes direcly in prod doesn't only happen at work)
3. Create new scripts to capture existing configuration
4. rewrite the documentation (*)
5. Add comments and refactor existing code (*)

(*) With the help of ollama, devin.ai, chatgpt and/or gemini.

## Installation

### Prerequisites

- Works on Linux, with with the following package managers : apt, flatpak, cargo, pip, and curl (limited).
- Need Python 3.8
- Need sudo privileges to install *install_overwatch* and also to install new applications

### Install Steps

Clone the repository and run the install command:

```bash
git clone https://github.com/mbeware/install_overwatch_2.git
cd install_overwatch_2
make install
```

This will build the installation package, install it system-wide, and start monitoring new installation. The installation places wrapper scripts in `/usr/local/bin/` which log new installation request before forwarding them to the real commands.

### Verify Installation

Check that the service is running:

```bash
systemctl status install_overwatch-init.service
```

Verify the wrappers are in place:

```bash
which apt    # Should show /usr/local/bin/apt
which pip    # Should show /usr/local/bin/pip
which cargo  # Should show /usr/local/bin/cargo
which curl   # Should show /usr/local/bin/curl
```

## Uninstallation

To completely remove *install_overwatch* from your system:

```bash
make uninstall
```

Or manually:

```bash
sudo systemctl stop install_overwatch-init.service
sudo systemctl disable install_overwatch-init.service
sudo dpkg -r install-overwatch
```

This removes the wrapper scripts and stops the monitoring service. Your log files at `/var/log/install_overwatch.log` and `/var/log/install_overwatch_curl_downloads.log` are not deleted.

## Capturing Existing Installed Applications

If you have a workstation that was set up before *install_overwatch* was installed, you can still capture its installations using the workstation snapshot tool.

### Basic Snapshot

Run the snapshot tool to capture all installed packages and user configurations:

```bash
cd install_overwatch_2
python3 tools/workstation_snapshot.py -o my_workstation.json
```

This scans for packages installed via apt (manually installed only, not auto-dependencies), pip (user packages), cargo, flatpak, and snap. It also captures user configuration files like `.bashrc`, `.gitconfig`, and files in `~/.config/`.

### Verbose Mode for workstation_snapshot.py

For detailed output showing what's being scanned:

```bash
python3 tools/workstation_snapshot.py -v -o my_workstation.json
```

### Packages Only

If you only want to capture installed packages without configuration files:

```bash
python3 tools/workstation_snapshot.py --packages-only -o packages.json
```

### Configs Only

If you only want to capture configuration files:

```bash
python3 tools/workstation_snapshot.py --configs-only -o configs.json
```

### Custom Configuration

You can customize what gets captured by editing `tools/config/snapshot_config.toml` or providing your own config file:

```bash
python3 tools/workstation_snapshot.py -c my_config.toml -o snapshot.json
```

## Capturing New Installations After Setup

Once *install_overwatch* is installed, it automatically logs all package installations and removals. You don't need to do anything special; just use your package managers normally.

### What Gets Logged

The following package manager operations are automatically logged to `/var/log/install_overwatch.log`:

- **apt**: apt install, remove, purge, and autoremove operations
- **pip**: pip install and uninstall commands
- **cargo**: cargo install and uninstall commands  
- **flatpak**: flatpak install and uninstall commands

Additionally, all curl commands are logged to `/var/log/install_overwatch_curl_downloads.log` since curl is often used to download and install software.

### Viewing the Logs

To see what has been installed since *install_overwatch* was set up:

```bash
cat /var/log/install_overwatch.log
```

Example log entries:

```log
2026-01-14T10:30:45+00:00 APT command: apt install htop
2026-01-14T10:35:22+00:00 PIP command: pip install requests
2026-01-14T11:00:00+00:00 CARGO command: cargo install ripgrep
```

### Log Format

Each log entry contains a timestamp, the package manager identifier (apt, pip, cargo, flatpak), and the full command that was executed. This format allows the Ansible generator to parse the logs and determine which packages are currently installed (accounting for installs and subsequent removals).

## Generating an Ansible Playbook

You can generate an Ansible playbook from either a snapshot file or from the *install_overwatch* logs.

### From a Snapshot

If you captured a snapshot of your workstation:

```bash
python3 tools/create_ansible.py my_workstation.json -o playbook.yml
```

This generates a complete Ansible playbook that will install all the packages and restore all the configuration files from your snapshot.

### From Logs

If you've been running *install_overwatch* and want to generate a playbook from the accumulated logs:

```bash
python3 tools/create_ansible.py --from-logs /var/log/install_overwatch.log -o playbook.yml
```

The tool analyzes the log to determine which packages are currently installed (it tracks install/remove pairs and only includes packages that were installed but not subsequently removed).

### Verbose Mode for create_ansible.py

For detailed output:

```bash
python3 tools/create_ansible.py my_workstation.json -v -o playbook.yml
```

### Generated Playbook Structure

The generated playbook uses proper Ansible modules where available. apt packages use `ansible.builtin.apt`, pip packages use `ansible.builtin.pip`, flatpak uses `community.general.flatpak`, and snap uses `community.general.snap`. Cargo packages use shell commands since there's no native Ansible module.

Configuration files are embedded directly in the playbook using `ansible.builtin.copy` with inline content. Desktop settings (dconf) are restored by writing a temporary file and piping it to `dconf load`.

## Using the Ansible Playbook on a New Computer

### Prerequisites on the New Machine

Install Ansible on the new machine:

```bash
sudo apt update
sudo apt install -y ansible git
```

For flatpak and snap support, install the community.general collection:

```bash
ansible-galaxy collection install community.general
```

### Transfer the Playbook

Copy your generated playbook to the new machine. You can use scp, a USB drive, or clone a git repository containing the playbook.

### Dry Run

Always do a dry run first to see what changes will be made:

```bash
ansible-playbook playbook.yml --check
```

### Run the Playbook

Execute the playbook to restore your workstation configuration:

```bash
ansible-playbook playbook.yml
```

Some tasks require sudo privileges. Ansible will prompt for your password, or you can use:

```bash
ansible-playbook playbook.yml --ask-become-pass
```

### Selective Installation

The generated playbook uses tags so you can install only specific components:

```bash
# Install only apt packages
ansible-playbook playbook.yml --tags apt

# Install only pip packages
ansible-playbook playbook.yml --tags pip

# Restore only configuration files
ansible-playbook playbook.yml --tags configs
```

### Post-Installation

After running the playbook, you may need to log out and back in for some changes to take effect (especially shell configuration changes). Some things cannot be automated and must be done manually, including browser logins and sync, SSH private keys, GPG keys, and password manager setup.

## How It Works Behind the Curtain

### Architecture Overview

*install_overwatch* uses a simple but effective approach: it places wrapper scripts in `/usr/local/bin/` which has higher PATH precedence than `/usr/bin/`. When you run `pip install something`, the wrapper at `/usr/local/bin/pip` is executed first. It logs the command, then uses `exec` to replace itself with the real `/usr/bin/pip`, passing through all arguments.

### Directory Structure

```doc
install_overwatch_2/
├── Makefile                 # Build and install commands
├── README.md                # This documentation
├── package/                 # Debian package source
│   ├── DEBIAN/
│   │   └── control          # Package metadata
│   ├── etc/
│   │   └── systemd/system/
│   │       └── install_overwatch-init.service
│   └── usr/
│       ├── lib/install_overwatch/
│       │   └── logger.sh    # Core logging functions
│       └── local/bin/
│           ├── apt          # apt wrapper
│           ├── pip          # pip wrapper
│           ├── cargo        # cargo wrapper
│           ├── curl         # curl wrapper
│           └── flatpak      # flatpak wrapper
└── tools/                   # Python tools
    ├── workstation_snapshot.py   # Captures current system state
    ├── create_ansible.py         # Generates Ansible playbooks
    ├── lib/
    │   ├── config.py        # TOML configuration loader
    │   └── logger.py        # Python logging with message IDs
    └── config/
        └── snapshot_config.toml  # Default configuration
```

### The Wrapper Scripts

Each wrapper script follows the same pattern. Here's the pip wrapper as an example:

```bash
#!/bin/bash
source /usr/lib/install_overwatch/logger.sh
if [[ "$1" == "install" || "$1" == "uninstall" ]]; then
  log_install "PIP" "pip $*"
fi
exec /usr/bin/pip "$@"
```

The script sources the logger, checks if the command is an install or uninstall operation, logs it if so, then uses `exec` to replace itself with the real command. The `exec` is important because it means the wrapper completely disappears and the real command runs as if it was called directly.

### The Logger

The logger script (`/usr/lib/install_overwatch/logger.sh`) provides two functions:

```bash
log_install() {
    echo "$(date --iso-8601=seconds) $1 command: $2" >> "$INSTALL_LOG"
}

log_curl() {
    echo "$(date --iso-8601=seconds) CURL command: curl $*" >> "$CURL_LOG"
}
```

Logs are written to `/var/log/install_overwatch.log` for package managers and `/var/log/install_overwatch_curl_downloads.log` for curl. The files are created with 666 permissions so any user can write to them.

### APT Logging

apt is handled the same way as other package managers - through a wrapper script at `/usr/local/bin/apt`. When you run `apt install something`, the wrapper logs the command and then passes through to `/usr/bin/apt`:

```bash
#!/bin/bash
source /usr/lib/install_overwatch/logger.sh
if [[ "$1" =~ ^(install|remove|purge|autoremove)$ ]]; then
  log_install "APT" "apt $*"
fi
exec /usr/bin/apt "$@"
```

This approach is more reliable than apt hooks and captures the exact command the user typed.

### The Snapshot Tool

The workstation snapshot tool (`tools/workstation_snapshot.py`) queries each package manager directly to get the current installed state. For apt, it runs `apt-mark showmanual` to get manually installed packages (excluding auto-installed dependencies). For pip, it runs `pip list --format=json`. For cargo, it runs `cargo install --list`. For flatpak and snap, it queries their respective list commands.

Configuration files are scanned based on the paths specified in the TOML config. Files are read and their content is stored in the snapshot JSON. Binary files are base64-encoded.

### The Ansible Generator

The Ansible generator (`tools/create_ansible.py`) takes either a snapshot JSON or the *install_overwatch* log file and produces an Ansible playbook. When processing logs, it tracks install and remove events for each package and only includes packages that are currently installed (last action was install, not remove).

The generator uses proper Ansible modules where available rather than shell commands. This makes the playbooks more idiomatic and provides better error handling and idempotency.

### SystemD Service

The `install_overwatch-init.service` is a oneshot service that runs at boot to ensure the log files exist with correct permissions:

```ini
[Service]
Type=oneshot
ExecStart=/usr/lib/install_overwatch/logger.sh
```

## Configuration

### Snapshot Configuration

The snapshot tool uses a TOML configuration file. The default is at `tools/config/snapshot_config.toml`. Key settings include:

**Package scanning**: Configure which package managers to scan and patterns to exclude (like kernel packages or dev libraries).

**Config file scanning**: Specify which dotfiles and config directories to include, patterns to exclude (like cache directories), and maximum file size.

**Logging**: Set the log level and output file location.

**Ansible output**: Configure the output path and whether to include comments in the generated playbook.

### Log File Locations

The log files are stored in the standard system log directory:

- `/var/log/install_overwatch.log` - Package manager operations
- `/var/log/install_overwatch_curl_downloads.log` - curl downloads

## Troubleshooting

### Wrapper Not Being Used

If commands aren't being logged, check that `/usr/local/bin` is in your PATH before `/usr/bin`:

```bash
echo $PATH
```

Verify the wrapper exists and is executable:

```bash
ls -la /usr/local/bin/pip
```

### Permission Denied on Log Files

If you get permission errors when logging, check the log file permissions:

```bash
ls -la /var/log/install_overwatch*.log
```

They should be 666. Fix with:

```bash
sudo chmod 666 /var/log/install_overwatch*.log
```

### Snapshot Tool Errors

If the snapshot tool fails, run with verbose mode to see detailed error messages:

```bash
python3 tools/workstation_snapshot.py -v -o test.json
```

Common issues include missing package managers (which are skipped with a warning) and permission errors reading config files.

### Ansible Playbook Errors

If the generated playbook fails, check that you have the required Ansible collections installed:

```bash
ansible-galaxy collection install community.general
```

Run with verbose mode to see detailed error output:

```bash
ansible-playbook playbook.yml -vvv
```

## Todo

1. A small program that allow to select which entry from the logs and existing installation to add to the playbook.
2. Allow adding a playbook to a playbook from the tool.
3. Add an option to pause capturing installations for X minutes.
4. Add a commandline to explicitly capture de command line
5. Add monitoring of dotfile and .config folder and log what was changed
6. Same with /etc
7. Monitor $EDITOR program to backup and diff
8. Add a periodic save of the logs to (git/nas)

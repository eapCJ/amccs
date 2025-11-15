# AMCCS Deployment Guide

This guide walks through installing and operating AMCCS on Raspberry Pi 4 rigs (2 GB or larger). It covers prerequisites, the automated installer, manual setup, configuration, lifecycle management, and how to verify the service.

## 1. Hardware & OS Requirements

- Raspberry Pi 4 with at least 2 GB RAM.
- Raspberry Pi OS Bookworm (64-bit recommended).
- Reliable power and network connectivity.
- USB access to every Android device you plan to coordinate (enable Developer Options + USB debugging).

## 2. Accounts & Permissions

AMCCS runs under a dedicated user that owns the code and virtualenv.

- Default user: `amccs`
- Default install path: `/opt/amccs`
- Runtime configuration: `/etc/amccs.env`, `/opt/amccs/config.yaml`

You can override these by exporting `AMCCS_USER`, `AMCCS_INSTALL_DIR`, or `AMCCS_PYTHON` before running the installer.

## 3. Fast Install (Recommended)

Run as root on each Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/eapCJ/adb_multicam/master/deploy/install.sh | sudo bash
```

The script:

1. Installs apt dependencies (`git`, `adb`, `python3.11`, `python3.11-venv` by default).
2. Creates the `amccs` user and `/opt/amccs` home.
3. Clones (or refreshes) the public repository.
4. Creates a `.venv`, installs the package (`pip install -e .[test,dev]`), and seeds `config.yaml`.
5. Creates `/etc/amccs.env` from `deploy/amccs.env.example`.
6. Renders systemd units (`amccs.service`, `amccs-update.service`, `amccs-update.timer`) and enables them.

After the script finishes:

```bash
sudo nano /etc/amccs.env         # set CAMERA_API_TOKEN, log level, etc.
sudo nano /opt/amccs/config.yaml # configure delays, zoom point, package names
sudo systemctl restart amccs
```

## 4. Manual Installation (If You Prefer)

1. Install packages:
   ```bash
   sudo apt update
   sudo apt install -y python3.11 python3.11-venv git adb
   ```
2. Create user & directory:
   ```bash
   sudo useradd -r -s /usr/sbin/nologin amccs || true
   sudo mkdir -p /opt/amccs && sudo chown amccs:amccs /opt/amccs
   ```
3. Clone & set up env:
   ```bash
   sudo -u amccs bash -lc '
     cd /opt/amccs
     git clone https://github.com/eapCJ/adb_multicam.git .
     python3.11 -m venv .venv
     source .venv/bin/activate
     pip install -U pip
     pip install -e .[test,dev]
     cp config.example.yaml config.yaml
   '
   sudo cp deploy/amccs.env.example /etc/amccs.env
   ```
4. Install systemd units:
   ```bash
   sudo cp deploy/amccs.service /etc/systemd/system/
   sudo cp deploy/amccs-update.service /etc/systemd/system/
   sudo cp deploy/amccs-update.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now amccs.service amccs-update.timer
   ```
5. Edit `/etc/amccs.env` and `/opt/amccs/config.yaml`, then `sudo systemctl restart amccs`.

## 5. Configuration Summary

`/etc/amccs.env` (Environment variables):

```ini
CAMERA_CONFIG_PATH=/opt/amccs/config.yaml
CAMERA_API_TOKEN=change-me
AMCCS_LOG_LEVEL=INFO
CAMERA_CONFIG_SEARCH_PATHS=/opt/amccs:/etc/amccs
AMCCS_INTEGRATION_ADB=0
```

`/opt/amccs/config.yaml` (“camera_defaults” etc.) must be tailored to your camera app package/activity, storage path, tap coordinates, and delays. Use `config.example.yaml` as the template.

## 6. Service Management

- Start/stop/restart: `sudo systemctl [start|stop|restart] amccs`
- Logs: `journalctl -u amccs -f`
- Auto-update timer (runs hourly): `sudo systemctl list-timers amccs-update.timer`
- Trigger immediate update: `sudo systemctl start amccs-update.service`

## 7. Verification & Health Checks

1. After boot, ensure adb sees devices: `sudo -u amccs adb devices`.
2. Hit the HTTP health endpoint:
   ```bash
   curl http://localhost:8080/health
   ```
   You should see `"status": "healthy"` and at least one device entry.
3. Optionally run the integration test:
   ```bash
   sudo -u amccs bash -lc '
     cd /opt/amccs
     export AMCCS_INTEGRATION_ADB=1
     .venv/bin/pytest -m integration
   '
   ```

## 8. Updates & Rollbacks

- Auto-update fetches latest `origin/master` hourly. To pin a tag or branch, edit `/etc/systemd/system/amccs-update.service` and change the `git` command (e.g., `git fetch && git checkout v0.1.0`).
- After changing unit files, always run `sudo systemctl daemon-reload`.
- For rollbacks, `sudo -u amccs bash -lc 'cd /opt/amccs && git checkout <commit>'` followed by `sudo systemctl restart amccs`.

## 9. Troubleshooting Tips

- **Service fails to start**: `journalctl -u amccs` will show stack traces; common issues include missing config, invalid YAML, or adb not installed.
- **No devices detected**: confirm `adb devices` lists them under the `amccs` user; adjust `udev` rules if necessary.
- **API unauthorized**: ensure your clients send `Authorization: Bearer <CAMERA_API_TOKEN>`.
- **Auto-update conflicts**: if you have local modifications, the timer’s `git reset --hard origin/master` will overwrite them; consider forking or using a deployment branch.

With the installer, systemd units, and environment templates in the repository, you can replicate this setup on as many rigs as needed with minimal manual work. Adjust the timer frequency, log level, and config paths to match your operational practices. Happy capturing!

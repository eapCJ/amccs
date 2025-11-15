#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)

AMCCS_USER=${AMCCS_USER:-amccs}
INSTALL_DIR=${AMCCS_INSTALL_DIR:-/opt/amccs}
PYTHON_BIN=${AMCCS_PYTHON:-python3.11}
REPO_URL=${AMCCS_REPO_URL:-https://github.com/eapCJ/adb_multicam.git}
APT_PACKAGES=${AMCCS_APT_PACKAGES:-"git adb python3.11 python3.11-venv"}

require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "This installer must be run as root (sudo)." >&2
        exit 1
    fi
}

run_as_app() {
    sudo -u "$AMCCS_USER" bash -lc "$1"
}

ensure_packages() {
    echo "Installing required apt packages..."
    apt-get update -y
    apt-get install -y $APT_PACKAGES
}

ensure_user() {
    if id "$AMCCS_USER" >/dev/null 2>&1; then
        return
    fi
    echo "Creating system user $AMCCS_USER"
    useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" "$AMCCS_USER"
}

sync_repo() {
    mkdir -p "$INSTALL_DIR"
    chown "$AMCCS_USER":"$AMCCS_USER" "$INSTALL_DIR"
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        echo "Updating existing repository..."
        run_as_app "cd $INSTALL_DIR && git fetch --all --prune && git reset --hard origin/master"
    else
        echo "Cloning repository..."
        run_as_app "git clone $REPO_URL $INSTALL_DIR"
    fi
}

ensure_venv() {
    run_as_app "
        cd $INSTALL_DIR && \
        $PYTHON_BIN -m venv .venv && \
        source .venv/bin/activate && \
        pip install -U pip && \
        pip install -e .[test,dev]
    "
}

ensure_config() {
    run_as_app "
        cd $INSTALL_DIR && \
        if [[ ! -f config.yaml ]]; then
            cp config.example.yaml config.yaml
        fi
    "
}

install_env_file() {
    if [[ ! -f /etc/amccs.env ]]; then
        echo "Installing /etc/amccs.env (edit this file to customize runtime settings)..."
        cp "$SCRIPT_DIR/amccs.env.example" /etc/amccs.env
    fi
}

render_unit() {
    local template=$1
    local destination=$2
    sed \
        -e "s#__INSTALL_DIR__#${INSTALL_DIR//\//\\/}#g" \
        -e "s#__AMCCS_USER__#${AMCCS_USER}#g" \
        "$SCRIPT_DIR/$template" > "$destination"
}

install_units() {
    echo "Installing systemd units..."
    render_unit "amccs.service" /etc/systemd/system/amccs.service
    render_unit "amccs-update.service" /etc/systemd/system/amccs-update.service
    cp "$SCRIPT_DIR/amccs-update.timer" /etc/systemd/system/amccs-update.timer
    systemctl daemon-reload
    systemctl enable --now amccs.service
    systemctl enable --now amccs-update.timer
}

main() {
    require_root
    ensure_packages
    ensure_user
    sync_repo
    ensure_venv
    ensure_config
    install_env_file
    install_units
    echo "Installation complete. Edit /etc/amccs.env and $INSTALL_DIR/config.yaml as needed, then restart the service via 'systemctl restart amccs'."
}

main "$@"

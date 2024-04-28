#!/bin/bash

# Installation script for iptables redirect

RED_COLOR='\033[0;31m'
GREEN_COLOR='\033[0;32m'
GREEN_YELLOW='\033[1;33m'
NO_COLOR='\033[0m'

ST_PORT=80

LINK="https://raw.githubusercontent.com/schizza/SWS-12500-custom-component/main/iptables_redirect.sh"

P_HA=true
P_ST=true

declare -a HA_PATHS=(
    "$PWD"
    "$PWD/config"
    "/config"
    "/homeassistant"
    "$HOME/.homeassistant"
    "/usr/share/hassio/homeassistant"
)

function info() { echo -e $2 "${GREEN_COLOR}$1${NO_COLOR}"; }
function warn() { echo -e $2 "${GREEN_YELLOW}$1${NO_COLOR}"; }
function error() {
    echo -e "${RED_COLOR}$1${NO_COLOR}"
    if [ "$2" != "false" ]; then exit 1; fi
}

function check() {
    echo -n "Checking dependencies: '$1' ... "
    if [ -z "$(command -v "$1")" ]; then
        error "not installed" $2
        false
    else
        info "OK."
        true
    fi
}

function validate_ip() {

    if [[ "$1" =~ ^(([1-9]?[0-9]|1[0-9][0-9]|2([0-4][0-9]|5[0-5]))\.){3}([1-9]?[0-9]|1[0-9][0-9]|2([0-4][0-9]|5[0-5]))$ ]]; then
        true
    else
        false
    fi
}

function validate_num() {
    if [[ "$1" =~ ^[0-9]+$ ]]; then true; else false; fi
}

function validate_dest() {
    echo "Validating host '$2' ... "
    if ping -c 4 2>/dev/null; then
        info "OK"
        true
    else
        error "cannot reach" false
        false
    fi
}

function cont() {

    while true; do
        warn "$1"
        warn "Do you want to continue? [y/N]: " -n
        read -n 1 YN
        YN=${YN:-N}
        case $YN in
        [Yy]) return 0 ;;
        [Nn]) error "\nExiting." ;;
        *) error "\nInvalid response.\n" false ;;
        esac
    done
}

echo
echo "**************************************************************"
echo "*                                                            *"
echo -e "*        ${GREEN_YELLOW}Installation for iptables_redirect.sh ${NO_COLOR}              *"
echo "*                                                            *"
echo "**************************************************************"
echo

check "wget"
check "sed"
check "ping" false && { PING=true; } || { PING=false; }

echo -n "Trying to find Home Assitant ... "
for _PATH in "${HA_PATHS[@]}"; do
    if [ -n "$HA_PATH" ]; then
        break
    fi

    if [ -f "$_PATH/.HA_VERSION" ]; then
        HA_PATH="$_PATH"
    fi
done

[ -z $HA_PATH ] && { error "Home Assistant not found!"; }
info "found at $HA_PATH"

while true; do
    read -r -p "Your station's IP: " ST_IP
    if validate_ip $ST_IP; then break; fi
    warn "Provide valid IP address."
done

while true; do
    read -r -p "Home Assistant's IP: " HA_IP
    if validate_ip $HA_IP; then break; fi
    warn "Provide valid IP address."
done

while true; do
    read -r -p "Home Assistant's port [8123]: " HA_PORT
    HA_PORT=${HA_PORT:-8123}
    if validate_num $HA_PORT && ((HA_PORT >= 1 && HA_PORT <= 65535)); then
        break
    fi
    warn "Provide valid port number."
done

if $PING; then
    validate_dest $HA_IP || {
        cont "Home Assistant host is unreachable."
        P_HA=false
    }
    validate_dest $ST_IP || {
        cont "Station is unreachable."
        P_ST=false
    }
fi

echo -n "Downloading 'iptables_redirect.sh' ... "
wget -q -O - "$LINK" | sed -e "s/\[_STATION_IP_\]/$ST_IP/" \
    -e "s/\[_HA_\]/$HA_IP/" \
    -e "s/\[_SRC_PORT_\]/$ST_PORT/" \
    -e "s/\[_DST_PORT_\]/$HA_PORT/" >./iptables_redirect.sh

EXIT_STATUS=$?
if [ $EXIT_STATUS -ne 0 ]; then
    warn "wget exited with error: $EXIT_STATUS"
    error "Could not download 'iptables_redirect.sh'."
else
    info "iptables_redirect.sh downloaded succeffully."
fi

info "\nYour configuration:"
info "   Home Assistant at: $HA_PATH"
info "   Home Assistant server at: $HA_IP:$HA_PORT" -n
if $PING; then
    if $P_HA; then info " (ping OK)"; else error " (unreachable)" false; fi
else
    error " (not tested)" false
fi
info "   Station at: ${ST_IP}:$ST_PORT" -n
if $PING; then
    if $P_ST; then info " (ping OK)"; else error " (unreachable)" false; fi
else
    error " (not tested)" false
fi

/bin/bash ./iptables_redirect.sh

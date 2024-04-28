#!/bin/bash

# Script for frowarding SWS 12500 station's destination port 80
# to your Home Assistant's instance port (8123)
#
# Workaround for station's firmware 1.0 bug
#
#
# Script pro přesměrování portu pro stanici SWS12500

STATION_IP=[_STATION_IP_]
HA=[_HA_]
SRC_PORT=[_SRC_PORT_]
DST_PORT=[_DST_PORT_]

INSTALL_IPTABLES=0
APK_MISSING=0

RED_COLOR='\033[0;31m'
GREEN_COLOR='\033[0;32m'
GREEN_YELLOW='\033[1;33m'
NO_COLOR='\033[0m'

function info() { echo -e "${GREEN_COLOR}$1${NO_COLOR}"; }
function warn() { echo -e "${GREEN_YELLOW}$1${NO_COLOR}"; }
function error() {
    echo -e "${RED_COLOR}$1${NO_COLOR}"
    if [ "$2" != "false" ]; then exit 1; fi
}

function check() {
    echo -n "Checking dependencies: '$1' ... "
    if [ -z "$(command -v "$1")" ]; then
        error "not installed" $2
        return 1
    fi
    info "OK."
    return 0
}

echo
echo "**************************************************************"
echo "*                                                            *"
echo -e "*        ${GREEN_YELLOW}Running iptables forward for port $SRC_PORT -> $DST_PORT ${NO_COLOR}       *"
echo "*                                                            *"
echo "**************************************************************"
echo

# Check for dependencies

check "iptables" false
INSTALL_IPTABLES=$?

check "apk" false
APK_MISSING=$?

if [ $APK_MISSING -eq 1 ] && [ $INSTALL_IPTABLES -eq 1 ]; then
    error "Could not install and run iptables.\n'apk' installer is missing and 'iptables' are not installed.\n"
fi

if [ $INSTALL_IPTABLES -eq 1 ] && [ $APK_MISSING -eq 0 ]; then
    declare -a RUNINSTALL=(apk add iptables)
    echo -n "Installing 'iptables' ... ${RUNINSTALL[@]} ... "
    ${RUNINSTALL[@]}
    EXIT_STATUS=$?
    if [ $EXIT_STATUS -ne 0 ]; then
        warn "apk error code: $EXIT_STATUS"
        error "Installation of iptables failed!"
    else
        info "'iptables' installed successfully."
    fi
fi
declare -a RULE=(PREROUTING -t nat -s $STATION_IP -d $HA -p tcp -m tcp --dport $SRC_PORT -j REDIRECT --to-ports $DST_PORT)
echo -n "Chceking for existing rule in iptables ... "
$(iptables -C ${RULE[@]} 2>/dev/null)
if [ $? -eq 0 ]; then
    warn "Rule is already present in PREROUTING chain."
else
    info "not found."
    echo -n "Inserting iptables rule to PREROUTING chain ... "
    $(iptables -I ${RULE[@]})
fi
EXIT_STATUS=$?
if [ $EXIT_STATUS -ne 0 ]; then
    warn "iptables error code: ${EXIT_STATUS} "
    error "Rule could not be added!"
fi

info "OK."
info "iptables are now set to redirect incomming connections from $STATION_IP:Any -> $HA:$SRC_PORT to $HA:$DST_PORT"

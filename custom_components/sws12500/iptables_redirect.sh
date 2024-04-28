#!/bin/bash

# Script pro přesměrování portu pro stanici SWS12500

# set -e

STATION_IP=192.168.2.95
HA=192.168.2.219
SRC_PORT=80
DST_PORT=8123

INSTALL_IPTABLES=0
APK_MISSING=0

RED_COLOR='\033[0;31m'
GREEN_COLOR='\033[0;32m'
GREEN_YELLOW='\033[1;33m'
NO_COLOR='\033[0m'


function info () { echo -e "${GREEN_COLOR}INFO: $1${NO_COLOR}";}
function warn () { echo -e "${GREEN_YELLOW}WARN: $1${NO_COLOR}";}
function error () { echo -e "${RED_COLOR}ERROR: $1${NO_COLOR}"; if [ "$2" != "false" ]; then exit 1;fi; }

function check () {
	echo -n "Kontrola dostupnosti $1 ... "
	if [ -z "$(command -v "$1")" ]; then
		error "'$1' není nainstalován." $2
		return 1
	fi
	info "OK."
	return 0
}


echo 
echo "**************************************************************"
echo "*                                                            *"
echo -e "*     ${GREEN_YELLOW}Spouštím iptables přesměrování pro port $SRC_PORT -> $DST_PORT ${NO_COLOR}    *"
echo "*                                                            *"
echo "**************************************************************"
echo

# Máme nainstalované iptables a apk?

check "iptables" false
INSTALL_IPTABLES=$?

check "apk" false

APK_MISSING=$?


if [ $APK_MISSING -eq 1 ] && [ $INSTALL_IPTABLES -eq 1 ]; then
        error "Nelze nakonfigurovat IP Tables. \n'iptables' chybí a chybí i instalační aplikace 'apk'!!\n"
fi

if [ $INSTALL_IPTABLES -eq 1 ] && [ $APK_MISSING -eq 0 ]; then
        declare -a RUNINSTALL=(apk add iptables)
        echo -n "Spouštím instalaci iptables ... ${RUNINSTAll[@]} ... "
		${RUNINSTALL[@]}
        EXIT_STATUS=$?
        if [ $EXIT_STATUS -ne 0 ]; then
				warn "Chybový kód instalace: $EXIT_STATUS"
                error "Instalace iptables se nezdařila!"
        else
            info "'iptables' úspěšně nainstalovány."
        fi
fi
declare -a RULE=(PREROUTING -t nat -s $STATION_IP -d $HA -p tcp -m tcp --dport $SRC_PORT -j REDIRECT --to-ports $DST_PORT)
echo -ne "Spouštím iptables ... "
$(iptables -C ${RULE[@]} 2>/dev/null)
if [ $? -eq 0 ]; then
    warn "Pravidlo je již v iptables zapsáno."
else
    $(iptables -I ${RULE[@]})
fi
EXIT_STATUS=$?
if [ $EXIT_STATUS -ne 0 ]; then
	warn "Chybový kód iptables: ${EXIT_STATUS} "
	error "Přidání pravidla do iptables se nezdařilo!"
fi

info "iptables jsou nastaveny na přesměrování portu $SRC_PORT -> $DST_PORT pro stanici na IP: $STATION_IP"


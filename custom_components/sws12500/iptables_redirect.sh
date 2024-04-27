#!/bin/zsh

# Script pro přesměrování portu pro stanici SWS12500

STATION_IP = 192.168.2.95
HA = 192.168.2.219
SRC_PORT = 80
DST_PORT = 8123

INSTALL_IPTABLES = 0
APK_MISSING = 0

echo "Spoštím iptables pro 80 -> 8123 přesměrování"

# Máme nainstalované iptables?

echo -n "Kontrola zda jsou dostupné iptable ... "
IPTABLES='$(type -p "iptables")'
if ! [ -f "$IPTABLES" ]; then
	echo "chybí"
	INSTALL_IPTABLES = 1
else
	echo "OK"
fi

# Máme apk?
echo -n "Kontrola zda je dostupný apk  ..."
APK='$(type -p "apk")'
if ! [ -f "$APK" ]; then
	echo "chybí"
	APK_MISSING = 1
else
	echo "OK"
fi

if [ APK_MISSING == 1 -a INSTALL_IPTABLES == 1 ]
	echo "Nelze nakonfigurovat IP Tables. iptables chybí a chybí i instalační aplikace apk!!"
	exit 1
fi

if [ INSTALL_IPTABLES == 1 -a APK_MISSING == 0]
	runinstall=(apk add iptables)
        echo -n "Spouštím instalaci iptables ... ${runinstall[@]} ... "
        ${runinstall[@]}
        EXIT_STATUS=$?
	if [ $EXIT_STATUS -ne 0 ]
                echo "Instalace iptables se nezdařila!"
                exit $EXIT_STATUS
	fi
        runiptables=(iptables -t nat -I PREROUTING --src $STATION_IP --dst $HA -p tcp --dport $SRC_PORT -j REDIRECT --to-ports $DST_PORT)
        echo -n "Spouštím iptables ... ${runiptables[@]} ..."
        ${runiptables[@]}
        EXIT_STATUS=$?
        if [ $EXIT_STATUS -ne 0 ]
                echo "Přidní pravidla do iptables se nezdařilo!"
                exit $EXIT_STATUS
	fi
fi
echo "iptables jsou nastaveny na přesměrování portu $SRC_PORT -> $DST_PORT pro stanici na IP: $STATION_IP"
exit



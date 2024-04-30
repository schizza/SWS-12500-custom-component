#!/bin/bash

# Installation script for iptables redirect

RED_COLOR='\033[0;31m'
GREEN_COLOR='\033[0;32m'
GREEN_YELLOW='\033[1;33m'
NO_COLOR='\033[0m'

ST_PORT=80

LINK="https://raw.githubusercontent.com/schizza/SWS-12500-custom-component/main/iptables_redirect.sh"
FILENAME="iptables_redirect.sh"
SCRIPT_DIR="iptables_redirect"

P_HA=true
P_ST=true

declare -a HA_PATHS=(
    "$PWD"
    "$PWD/config"
    "/config"
    "/homeassistant"
    "$HOME/.homeassistant"
    "/usr/share/hassio/homeassistant"
    "./HA"
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
    echo -n "Validating host '$1' ... "
    if ping -c 2 $1 >/dev/null 2>&1; then
        info "OK"
        true
    else
        error "cannot reach" false
        false
    fi
}

function exit_status() {
    # argv 1 - status
    #      2 - called function
    #      3 - error message
    #      4 - success message
    #      5 - exit on error bool

    if [ $1 -ne 0 ]; then
        warn "$2 exited with error: $1"
        error "$3" $5
    else
        info "$4"
    fi
}

function cont() {

    while true; do
        warn "$1"
        warn "Do you want to continue? [y/N]: " -n
        read -n 1 YN
        YN=${YN:-N}
        case $YN in
        [Yy])
            echo -e "\n"
            return 0
            ;;
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
check "ssh-keygen" false && { KEYGEN=true; } || { KEYGEN=false; }

echo -n "Trying to find Home Assitant ... "
for _PATH in "${HA_PATHS[@]}"; do
    if [ -n "$HA_PATH" ]; then
        break
    fi

    if [ -f "$_PATH/.HA_VERSION" ]; then
        HA_PATH="$_PATH"
    fi
done

COMPLETE_PATH="$HA_PATH/$SCRIPT_DIR"
FILENAME="$COMPLETE_PATH/$FILENAME"

[ -z $HA_PATH ] && { error "Home Assistant not found!"; }
info "found at $HA_PATH"

[ -d $COMPLETE_PATH ] && {
    warn "Previous version of script exists ... removing directory ($COMPLETE_PATH)"
    rm -r $COMPLETE_PATH
}

mkdir -p $COMPLETE_PATH

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

read -r -p "SSH server username: " SSH_USER
read -r -p "SSH server port: " SSH_PORT

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
    -e "s/\[_DST_PORT_\]/$HA_PORT/" >$FILENAME

exit_status $? "wget" \
    "Could not download 'iptables_redirect.sh'." \
    "iptables_redirect.sh downloaded successffully."

if $KEYGEN; then
    echo -n "Generating ssh key-pairs ... "
    mkdir -p "$COMPLETE_PATH/ssh"
    ssh-keygen -t ecdsa -b 521 -N "" -f "$COMPLETE_PATH/ssh/ipt_dsa" -q
    exit_status $? "ssh-keygen" \
        "Could not create ssh key-pairs." \
        "SSH key-pairs created successfully (at $COMPLETE_PATH/ssh/)" \
        false
fi

echo -n "Creating 'exec.sh' script ... "
cat >$COMPLETE_PATH/exec.sh <<-EOF
#!/bin/bash

cat $COMPLETE_PATH/runscript | ssh -i $COMPLETE_PATH/ssl/ipt_dsa -o StrictHostKeyChecking=no -p $SSH_PORT -l $SSH_USER $HA_IP /bin/zsh
EOF

exit_status $? "cat" \
    "Could not write '$COMPLETE_PATH/exec.sh'" \
    "OK."

echo -n "Setting 'exec.sh' script right privileges ... "
chmod +x --quiet "$COMPLETE_PATH/exec.sh"
exit_status $? "chmod" \
                "Filed to set +x on exec.sh" \
                "OK."

echo -n "Creating 'runscript' ... "
cat >$COMPLETE_PATH/runscript <<-"EOF"
#!/bin/zsh

SCRIPT=$(find /homeassistant -name "iptables_redirect.sh" | sed -n 1p)
sudo /bin/bash "$SCRIPT"
EOF

exit_status $? "cat" \
    "Could not write 'runscript'" \
    "OK."

echo -n "Modifying configuration.yaml ... "
cat >> $HA_PATH/configuration.yaml <<EOF

shell_command:
  iptables_script: ./iptables_redirect/exec.sh
EOF

exit_status $? "cat" \
            "Could not modify configuration.yaml" \
            "OK." \
            false

echo "Executing 'iptables_redirecet.sh' ..."

/bin/bash $FILENAME
FIRST_RUN=$?
exit_status $FIRST_RUN "iptables_redirect.sh" \
    "iptables_redirect scritp did not run successfully.\n But is installed in $FILENAME.\n Please run it again a look at the log." \
    "First run of 'iptables_redirect.sh' was successfful. Your iptables are set." \
    false

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

info "   First run of 'iptables_redirect.sh' script " -n
[ $FIRST_RUN -ne 0 ] && { error " failed." false; } || { info " passed."; }

info "   SSH pub_key: at $COMPLETE_PATH/ssh/ipt_dsa.pub"

#!/bin/sh
# Configure and start Dropbear SSH on CMCC RAX3000Q/QY.
# Run this on the router as root (via Telnet 4719 or an existing shell).
#
# After running, set the root password interactively:
#   passwd root
#
# Then disable the temporary Telnet service from the Web API (cmd=234, telnet=0).

set -e

echo "[*] Current dropbear config:"
uci show dropbear || true

echo "[*] Setting Dropbear to port 22 and enabling it..."
uci set dropbear.@dropbear[0].Port=22
uci set dropbear.@dropbear[0].enable=1
uci set dropbear.@dropbear[0].PasswordAuth=on
uci set dropbear.@dropbear[0].RootPasswordAuth=on
uci commit dropbear

echo "[*] Enabling and starting service..."
/etc/init.d/dropbear enable
/etc/init.d/dropbear start

sleep 2
echo "[*] Process:"
ps | grep dropbear | grep -v grep || true

echo "[*] Listening ports:"
netstat -ltn | grep ':22' || true

echo
echo "[!] Do not forget to set a root password:"
echo "    passwd root"
echo
echo "[!] Verify SSH from the client:"
echo "    ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa root@<router-ip>"

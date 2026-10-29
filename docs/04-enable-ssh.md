# 04. 配置并启用 Dropbear SSH

## 1. 初始状态

```text
/etc/config/dropbear:
  option PasswordAuth 'on'
  option RootPasswordAuth 'on'
  option Port         '8357'
  option enable       '0'

/etc/init.d/dropbear 存在
进程：只有 /usr/sbin/telnetd -p 4719
```

`dropbear -V`：

```text
Dropbear v2019.78
```

`dropbearkey -h` 仅支持：

```text
-t type  Type of key to generate. One of:
         rsa
```

因此该固件无法在路由器端生成 ECDSA/Ed25519 主机密钥，客户端需要兼容 `ssh-rsa`。

## 2. 修改 UCI 配置

在 root shell（Telnet 4719 或已有 SSH）中执行：

```sh
uci set dropbear.@dropbear[0].Port=22
uci set dropbear.@dropbear[0].enable=1
uci set dropbear.@dropbear[0].PasswordAuth=on
uci set dropbear.@dropbear[0].RootPasswordAuth=on
uci commit dropbear

/etc/init.d/dropbear enable
/etc/init.d/dropbear start
```

验证：

```sh
ps | grep dropbear | grep -v grep
netstat -ltn | grep ':22'
```

输出示例：

```text
 2353 root  860 S  /usr/sbin/dropbear -F -P /var/run/dropbear.1.pid -p
tcp  0  0 0.0.0.0:22  0.0.0.0:*  LISTEN
tcp  0  0 :::22       :::*       LISTEN
```

开机自启链接：

```text
/etc/rc.d/K50dropbear
/etc/rc.d/S19dropbear
```

## 3. 设置 root 密码

root 密码此前被清空，需要重新设置：

```sh
passwd root
```

输入两次新密码。示例交互：

```text
Changing password for root
New password:
Retype password:
passwd: password for root changed by root
```

> 仓库不记录真实密码。请使用你自己的强密码，并妥善保存。

## 4. 客户端连接

由于 Dropbear 只提供 `ssh-rsa` 主机密钥，新版 OpenSSH 会报：

```text
Unable to negotiate with 192.168.123.1 port 22:
no matching host key type found. Their offer: ssh-rsa
```

使用兼容参数：

```bash
ssh -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    root@192.168.123.1
```

或写入 `~/.ssh/config`：

```text
Host 192.168.123.1
  HostName 192.168.123.1
  User root
  HostKeyAlgorithms +ssh-rsa
  PubkeyAcceptedAlgorithms +ssh-rsa
```

之后直接：

```bash
ssh root@192.168.123.1
```

验证输出：

```text
uid=0(root) gid=0(root)
Linux OpenWrt 4.4.60 #2 SMP Thu Jan 6 22:19:36 CST 2022 armv7l GNU/Linux
SSH_OK
```

## 5. 关闭临时 Telnet

确认 SSH 可用后，回到 Web API：

```json
{
  "cmd": 234,
  "method": "POST",
  "telnet": "0",
  "ssh": "1",
  "sessionId": "<sessionId>"
}
```

确认端口：

```text
22   open
23   closed
4719 closed
```

## 6. 防火墙检查建议

SSH 监听在 `0.0.0.0:22` 和 `:::22`。如果路由器 WAN 口有公网地址，请确认：

- WAN 区域没有放行 22 端口
- 或只允许 LAN/指定管理网段访问

旧固件的 Dropbear 较弱，不建议直接暴露到公网。

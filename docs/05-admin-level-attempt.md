# 05. 将 admin 的 Web 等级改为 1（尝试，未生效）

## 目标

把 Web 管理员账号 `admin` 的等级从 `3` 提升到 `1`（superadmin 级），从而在 Web UI 中直接看到所有隐藏功能，不再需要代理改响应。

## 结论先行

- `mdlcfg -a SYS_USER_LOGIN_LEVEL=1` + `mdlcfg -c` 曾让 `mdlcfg -g` 和 `system_config.use` 短暂显示 `1`。
- 但随后配置被守护进程/服务自动回滚为 `3`；复查 `.use`、`.bak`、`mdlcfg -g` 均为 `3`。
- 且即使在那段短暂窗口内重新登录 Web，返回仍然是：

```json
{"user_level":"3","AUTH":"AUTH"}
```

- `INIT_PAGE` 的 `account_level` 仍然是 `3`。
- **因此该修改没有达到目的。** 该字段很可能不是 Web 登录等级的唯一来源，或者登录逻辑按用户名硬编码/缓存了等级。

## 配置定位

```sh
ls -l /etc/tzcfg/
```

关键文件：

```text
-rw-r--r-- 1 root root 153600 ... system_config.bak
-rw-r--r-- 1 root root 153600 ... system_config.use
```

`system_config.use` 中包含的账号相关键：

```text
SYS_SUPER_LOGIN_NAME   = superadmin
SYS_SENIOR_LOGIN_NAME  = senior
SYS_USER_LOGIN_NAME    = admin
SYS_USER_LOGIN_LEVEL   = 3
SYS_USER_LOGIN_PWD     = <明文密码，已脱敏>
SYS_USER_LOGIN_TIMES   = <登录次数>
```

> 安全发现：该固件把 Web 登录密码以**明文**形式存放在 `system_config.use` 中。该文件不应外传，备份也要加密。

## 二进制记录格式

`system_config.use` 是 153600 字节的定长记录数组：

- 每条记录 128 字节
- 键名位于记录偏移 `+64`，长度 64 字节，`\0` 填充
- 值位于键名之后 `+64`，长度 64 字节，`\0` 填充

也就是说，若键的起始偏移为 `K`：

```text
value: [K+64, K+128)
key:   [K,    K+64)
```

示例（修改前）：

| 键 | 键偏移 | 值偏移 | 值 |
|---|---:|---:|---|
| `SYS_SECURITY_LEVEL` | 10176 | 10240 | `0` |
| `SYS_USER_LOGIN_LEVEL` | 62976 | 63040 | `3` |
| `SYS_USER_LOGIN_NAME` | 125376 | 125440 | `admin` |
| `SYS_USER_LOGIN_PWD` | 133056 | 133120 | `<redacted>` |

## 修改过程

使用固件自带的 `mdlcfg` 工具（不是直接改二进制文件）：

```sh
# 读取
mdlcfg -g SYS_USER_LOGIN_LEVEL
# 3

# 备份到 /tmp（重启会丢失；完整备份请自行保存）
cp /etc/tzcfg/system_config.use /tmp/system_config.use.before_level1
cp /etc/tzcfg/system_config.bak /tmp/system_config.bak.before_level1

# 修改并写回闪存
mdlcfg -a SYS_USER_LOGIN_LEVEL=1
mdlcfg -c

# 验证
mdlcfg -g SYS_USER_LOGIN_LEVEL
# 1
dd if=/etc/tzcfg/system_config.use bs=1 skip=63040 count=1 2>/dev/null
# 1
```

`mdlcfg` 用法：

```text
mdlcfg -a XXX=YYY   赋值
mdlcfg -g XXX       读取
mdlcfg -c           保存到闪存
mdlcfg -e           导出全部参数
mdlcfg -d XXX       删除参数
```

## 验证结果

重新走登录 API：

```json
{
  "cmd": 100,
  "method": "POST",
  "username": "admin",
  "passwd": "<sha256(token + password)>",
  "isAutoUpgrade": "0",
  "sessionId": ""
}
```

返回：

```json
{
  "success": true,
  "cmd": 100,
  "user_level": "3",
  "AUTH": "AUTH",
  "sessionId": "<redacted>"
}
```

`cmd=80`：

```json
{"account_level":"3"}
```

说明修改没有影响 Web 登录等级。

## 回滚观察

在登录验证之后再次复查，发现配置已经自动恢复为 `3`：

```sh
$ mdlcfg -g SYS_USER_LOGIN_LEVEL
3

$ dd if=/etc/tzcfg/system_config.use bs=1 skip=63040 count=1 2>/dev/null
3

$ dd if=/etc/tzcfg/system_config.bak bs=1 skip=63040 count=1 2>/dev/null
3
```

也就是说：

- `mdlcfg -a` / `-c` 的效果是**短暂的**，没有在闪存/守护进程状态中持久化。
- 很可能是 `mdlcfgd` / `cfgucid` 从 `.bak`、`/tmp/mdlcfgd/generic_system_config_file.sqlite` 或启动时的默认配置重新加载，覆盖了修改。
- 因此最终状态与初始状态一致：`admin` 仍是 3 级。

## 可能原因

1. **按用户名硬编码**：`superadmin` → 1、`senior` → 2、`admin` → 3，`SYS_USER_LOGIN_LEVEL` 只用于其他逻辑。
2. **CGI/守护进程缓存**：`http.cgi` 或 `cfgucid`/`mdlcfgd` 在启动时缓存了等级，`mdlcfg -a` 只更新了配置内存，没有刷新登录模块的缓存。
3. **登录等级来自另一份配置**：例如 `/etc/tzcfg/main_config`、`/system/cusetc/system_config.def` 或 Web 会话表。
4. **`SYS_USER_LOGIN_LEVEL` 只对 `SYS_USER_LOGIN_NAME` 之外的账号生效**，而 `admin` 走的是另一条分支。

## 建议的下一步

按风险从低到高：

1. **重启 Web/CGI 相关服务**后重试登录：
   ```sh
   /etc/init.d/cfgucid restart
   # 或重启整机（会短暂断网）
   reboot
   ```
   如果重启后 `user_level` 变成 1，说明是缓存问题。

2. **反汇编/分析 `http.cgi` 的登录分支**：
   ```sh
   strings -t d /tzwww/cgi-bin/http.cgi | grep -i -E 'superadmin|senior|user_level|SYS_USER_LOGIN_LEVEL'
   ```
   重点看 `cmd=100` 处理函数里 `user_level` 的赋值来源。

3. **临时改用 `superadmin` 账号**：如果只是需要 1 级权限，可以直接把 `superadmin` 的密码改成已知值，用 `superadmin` 登录；这比改 `admin` 的等级更符合固件原有设计。

4. **修改 `SYS_USER_LOGIN_NAME` 为 `superadmin`**：不推荐，可能与已有账号冲突。

## 最终状态

复查时配置已自动回滚，当前：

```text
mdlcfg -g SYS_USER_LOGIN_LEVEL  -> 3
/etc/tzcfg/system_config.use    -> 3
/etc/tzcfg/system_config.bak    -> 3
```

已回到初始值，无需手动恢复。Web 登录始终返回 `user_level=3`。

如果后续再次尝试，建议：

1. 先确认 `mdlcfgd` / `cfgucid` 的真实配置来源（sqlite、`.bak`、flash 分区）。
2. 使用配置事务接口，或修改后重启并立即验证。
3. 修改前备份 `.use` / `.bak`，并准备恢复手段。

> 直接覆盖文件后需要重启相关服务或整机，且可能被 `mdlcfgd` 覆盖；不要只依赖 `mdlcfg -c`。

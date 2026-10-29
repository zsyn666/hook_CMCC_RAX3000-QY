# `/etc/tzcfg/system_config.use` 记录格式

## 基本信息

```text
路径: /etc/tzcfg/system_config.use
大小: 153600 字节
备份: /etc/tzcfg/system_config.bak
权限: 644 root:root
```

该文件是定长记录数组，不是文本配置文件。

## 记录布局

每条记录 **128 字节**：

```text
偏移 +0   .. +63   值 value（64 字节，\0 填充）
偏移 +64  .. +127  键 key  （64 字节，\0 填充）
```

等价地，若键的起始偏移为 `K`：

```text
key:   [K,    K+64)
value: [K+64, K+128)
```

## 已确认的键偏移（修改前）

| 键 | 键偏移 `K` | 值偏移 `K+64` | 值 |
|---|---:|---:|---|
| `SYS_SECURITY_LEVEL` | 10176 | 10240 | `0` |
| `SYS_USER_LOGIN_LEVEL` | 62976 | 63040 | `3` |
| `SYS_USER_LOGIN_NAME` | 125376 | 125440 | `admin` |
| `SYS_USER_LOGIN_PWD` | 133056 | 133120 | `<redacted>` |
| `SYS_SUPER_LOGIN_NAME` | 10944 | 11008 | `superadmin` |
| `SYS_SENIOR_LOGIN_NAME` | 68544 | 68608 | `senior` |

> 键偏移会随固件/配置项数量变化，不要硬编码到脚本里；先 `grep -abo` 或 `strings -t d` 定位。

## 安全发现

`SYS_USER_LOGIN_PWD` 的值是**明文密码**（不是哈希）。这意味着：

- `/etc/tzcfg/system_config.use` 和 `.bak` 都是敏感文件
- 导出配置、备份、日志时要注意脱敏
- 不要把它们提交到 Git 仓库

本仓库的 `.gitignore` 已忽略 `*.use` / `*.bak`。

## 推荐修改方式

不要直接改二进制文件，使用固件自带的 `mdlcfg`：

```sh
# 读
mdlcfg -g SYS_USER_LOGIN_LEVEL

# 写（运行内存）
mdlcfg -a SYS_USER_LOGIN_LEVEL=1

# 保存到闪存
mdlcfg -c

# 再读确认
mdlcfg -g SYS_USER_LOGIN_LEVEL
```

`mdlcfg` 帮助：

```text
mdlcfg -a XXX=YYY   assign parameter XXX
mdlcfg -e           export all parameters
mdlcfg -c           save all parameters to flash
mdlcfg -d XXX       delete parameter XXX
mdlcfg -g XXX       get value of one key XXX
mdlcfg -m XXX       export all macro definitions to file XXX
mdlcfg -p           purge all information about config
mdlcfg -f XXX=YYY   assign one tmp flag XXX
mdlcfg -o XXX       obtain flag XXX
mdlcfg -t XXX       test flag exist status
mdlcfg -v           view all flags
mdlcfg -k superkey  check superkey
```

## 为什么改了 `SYS_USER_LOGIN_LEVEL` 仍返回 3

见 [`docs/05-admin-level-attempt.md`](../docs/05-admin-level-attempt.md)。简单说：

- `mdlcfg -g` 已显示 `1`
- 文件偏移 63040 的字节已变成 `1`
- 但重新登录 Web 仍返回 `user_level=3`

说明 Web 登录等级还受其他逻辑影响（按用户名硬编码、缓存、或另一份配置）。

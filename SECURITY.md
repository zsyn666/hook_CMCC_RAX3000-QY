# 安全说明

## 授权范围

本仓库记录的是对**自有**路由器的维护过程。请勿将其中方法用于未授权设备。

## 凭据

- 仓库中不包含 Web 密码、root 密码、sessionId、MAC 地址等敏感信息。
- 脚本从环境变量读取密码：

```sh
export ROUTER_IP=192.168.123.1
export ROUTER_USER=admin
export ROUTER_PASS='<your-password>'
```

- `secrets.env` 已被 `.gitignore` 忽略；`secrets.env.example` 只是模板。
- 如果密码曾经出现在聊天、日志或截图中，建议立即修改。

## 固件安全发现

1. **Web 密码明文存储**：`/etc/tzcfg/system_config.use` 中的 `SYS_USER_LOGIN_PWD` 是明文。该文件及 `.bak` 必须按敏感文件保护。
2. **命令注入**：ping 接口的 `url` 参数可注入 `$()`，且以 root 执行。
3. **弱 SSH 主机密钥**：Dropbear 2019.78 仅编译 RSA，客户端必须临时启用 `ssh-rsa`。
4. **Telnet 风险**：临时开启的 Telnet 使用 root + 空密码，验证 SSH 后必须关闭。

## 加固建议

- 设置强 root 密码，不要与 Web 密码相同。
- 确认 WAN 区域没有放行 22/4719。
- 不需要时关闭 Web 远程管理。
- 定期备份配置，但备份文件要加密。
- 如果固件支持，升级到较新的 Dropbear/OpenWrt，使用 Ed25519 主机密钥。
- 不要在生产网络中长期保留命令注入入口；本机维护完成后尽量升级或隔离。

## 恢复手段

修改配置前应：

- 备份 `/etc/tzcfg/system_config.use` 和 `.bak`
- 确认有串口、U-Boot 或恢复模式
- 记录当前 LAN/WAN/VLAN 配置

命令注入和配置修改存在变砖、失联风险。

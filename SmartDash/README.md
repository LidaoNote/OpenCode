# SmartDash 安装与管理脚本

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)

SmartDash 是一个基于 SmartDNS 的智能 DNS 外部面板程序。此脚本提供 SmartDash 的自动化安装与管理功能，适用于 Linux 系统。

## 功能特点

- 检查依赖环境（Python 和模块），并提供安装选项。
- 安装 SmartDash 为系统服务（包括下载程序和依赖安装）。
- 卸载 SmartDash 服务（可选删除应用文件）。
- 检测 SmartDNS 是否已安装（作为前提条件）。

## 安装与使用

### 下载脚本

```bash
wget https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/SmartDash/install_smartdash.sh -O install_smartdash.sh
```

### 运行脚本

赋予执行权限

```bash
chmod +x install_smartdash.sh
```

### 运行脚本

```bash
./install_smartdash.sh
```

### 交互式菜单

脚本将显示交互式菜单，选择操作：

1：检查依赖环境。

 2：安装 SmartDash 为系统服务。 

3：卸载 SmartDash 服务。 

4：退出。

## 注意事项

必须先安装 SmartDNS（配置文件需位于 /etc/smartdns/smartdns.conf）。 脚本需要网络连接以下载文件和安装依赖。 建议以具有 sudo 权限的用户运行。

## 许可

此项目遵循 MIT 许可证。

<br>
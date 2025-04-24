# SmartDash 安装与管理脚本

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-green.svg)](https://www.linux.org/)

**SmartDash** 是一个基于 **SmartDNS** 的智能 DNS 外部面板程序。本脚本提供自动化安装与管理功能，专为 Linux 系统设计，简化 SmartDash 的部署与维护。

## ✨ 功能亮点

- **依赖检查**：自动检测 Python 环境及必要模块，支持一键安装缺失依赖。
- **服务安装**：将 SmartDash 配置为系统服务，包含程序下载与依赖部署。
- **便捷卸载**：支持卸载 SmartDash 服务，并可选删除相关文件。
- **前置检测**：确保 SmartDNS 已正确安装，作为运行前提。

## 📥 安装与使用

### 1. 通过以下命令安装：

```bash
bash <(curl -sL https://lidao.win/smartdash.sh)
```

### 2. 交互式菜单

运行脚本后，将显示以下交互式菜单供选择：

- **1**：检查依赖环境
- **2**：安装 SmartDash 为系统服务
- **3**：卸载 SmartDash 服务
- **4**：退出

## ⚠️ 注意事项

- **前置条件**：必须先安装 **SmartDNS**，且配置文件位于 `/etc/smartdns/smartdns.conf`。
- **网络要求**：脚本运行需要联网以下载文件和依赖。
- **权限建议**：建议使用具有 `sudo` 权限的用户运行脚本。

> **提示**：请确保系统环境干净，避免因依赖冲突导致安装失败。

## 📜 许可

本项目采用 [MIT 许可证](https://opensource.org/licenses/MIT)，欢迎自由使用与修改。

## 🔗 相关资源

- [SmartDNS 官方文档](https://github.com/pymumu/smartdns)
- [SmartDash 项目主页](https://github.com/LidaoNote/OpenCode/tree/main/SmartDash)
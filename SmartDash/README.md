# SmartDash

![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

SmartDash 是一个基于 Flask 的 Web 应用，用于管理和配置 SmartDNS 服务。它提供直观的中文界面，支持上游服务器管理、域名组配置、服务设置、缓存管理（包括乐观缓存）、配置备份/还原和 DNS 测试等功能。SmartDash 兼容 CentOS、Ubuntu 等主流 Linux 系统，通过自动化安装脚本简化部署流程，适合网络管理员和开发者快速配置 SmartDNS。

## 功能

- **上游服务器管理**：添加、编辑、删除服务器，支持 UDP、TLS、HTTPS 协议，服务器地址合并显示。
- **域名组配置**：管理域名列表，支持源 URL 更新、测速模式（Ping/TCP）、响应模式（Fastest/First-Ping）、IPv6 设置。
- **服务设置**：配置 UDP/TCP 端口、全局 IPv6 禁用。
- **缓存管理**：支持基本缓存（启用、记录数、持久化）和乐观缓存（TTL、回复 TTL、预获取时间）。
- **备份与还原**：一键备份 SmartDNS 配置，支持从备份文件还原。
- **DNS 测试**：测试域名解析，快速验证 SmartDNS 功能。
- **自动化安装**：安装脚本支持环境检测和修复，兼容 CentOS（yum/dnf）、Ubuntu/Debian（apt）。
- **中文界面**：全中文提示和错误消息，操作简便。

## 依赖

- **系统**：CentOS 7/8/9, Ubuntu 20.04/22.04, Debian 11/12
- **软件**：Python 3.6+, pip3
- **Python 包**：
  - flask
  - flask-bootstrap
  - dnspython
  - requests

## 安装

### 1. 克隆仓库
```bash
git clone https://github.com/your-username/SmartDash.git
cd SmartDash
```

将 `your-username` 替换为您的 GitHub 用户名。

### 2. 运行安装脚本
安装脚本会自动检测和安装依赖（Python 3, pip3, Python 包），配置 systemd 服务，并启动 SmartDash。

```bash
chmod +x install_smartdash.sh
sudo ./install_smartdash.sh
```

- **提示输入路径**：输入 SmartDash 安装路径（默认 `/root/SmartDash/`），或直接按 Enter 使用默认值。
- **依赖安装**：
  - Ubuntu/Debian：使用 `apt` 安装 `python3`, `python3-pip`。
  - CentOS：使用 `yum`（CentOS 7）或 `dnf`（CentOS 8/9）。
  - 自动安装 Python 包：`flask`, `flask-bootstrap`, `dnspython`, `requests`。
- **服务配置**：创建 `/etc/systemd/system/smartdash.service`，启用并启动服务。

### 3. 验证安装
- 检查服务状态：
  ```bash
  systemctl status smartdash
  ```
  确认显示 `Active: active (running)`。
- 访问 Web 界面：
  打开浏览器，访问 `http://localhost:8088`（或服务器 IP 的 8088 端口）。

## 用法

1. **访问界面**：
   - 打开 `http://<服务器 IP>:8088`。
   - 使用中文界面管理 SmartDNS 配置。

2. **主要操作**：
   - **服务设置**：调整 UDP/TCP 端口，启用/禁用全局 IPv6。
   - **缓存设置**：配置基本缓存和乐观缓存参数。
   - **上游服务器**：添加服务器（例如 `8.8.8.8:53`），指定组别。
   - **域名组**：添加域名组，设置源 URL、测速模式、IPv6 等。
   - **测试与备份**：测试 DNS 解析，备份/还原配置。
   - **重启 SmartDNS**：点击顶部“重启 SmartDNS”按钮应用更改。

3. **配置文件**：
   - SmartDash 修改 `/etc/smartdns/smartdns.conf`。
   - 备份存储在 `/etc/smartdns/backups/`。

## 贡献

欢迎为 SmartDash 贡献代码！请按照以下步骤提交 Pull Request：

1. Fork 本仓库。
2. 创建分支：`git checkout -b feature/your-feature`。
3. 提交更改：`git commit -m "添加新功能：描述"`。
4. 推送到 Fork：`git push origin feature/your-feature`。
5. 在 GitHub 创建 Pull Request。

请确保代码遵循 PEP 8（Python 编码规范），并附带必要的测试。

## 许可

本项目采用 [MIT 许可证](LICENSE)。详情请查看 [LICENSE](LICENSE) 文件。

---

如果您有任何问题或建议，请在 [Issues](https://github.com/your-username/SmartDash/issues) 中提出！
# SmartDash

SmartDash 是一个基于 Flask 的 Web 工具，用于管理 SmartDNS 配置，提供简洁的中文界面。支持上游服务器、域名组、缓存设置、备份还原和 DNS 测试，兼容 CentOS 和 Ubuntu。自动化安装脚本从 GitHub 下载并部署，快速高效。

## 功能

- 管理上游服务器和域名组（测速、IPv6）。
- 配置端口、缓存（基本/乐观缓存）。
- 备份/还原配置，测试 DNS 解析。
- 全中文界面，自动化安装。

## 依赖

- **系统**：CentOS 7/8/9, Ubuntu 20.04/22.04, Debian 11/12
- **软件**：Python 3.6+, pip3, curl, unzip
- **Python 包**：`flask`, `flask-bootstrap`, `dnspython`, `requests`

## 安装

1. **下载安装脚本**：

   ```bash
   curl -L -o install_smartdash.sh https://raw.githubusercontent.com/LidaoNote/OpenCode/SmartDash/main/install_smartdash.sh
   chmod +x install_smartdash.sh
   ```

2. **运行脚本**：

   ```bash
   sudo ./install_smartdash.sh
   ```

   - 输入安装路径（默认 `/root/SmartDash/`）或按 Enter。
   - 脚本自动：
     - 下载 SmartDash ZIP 包并解压。
     - 安装依赖（`python3`, `pip3`, Python 包）。
     - 配置并启动 `smartdash` 服务。

3. **验证**：

   - 检查服务：`systemctl status smartdash`
   - 访问：`http://<服务器 IP>:8088`

## 用法

- **访问**：打开 `http://<服务器 IP>:8088`，使用中文界面。
- **操作**：配置端口、缓存、服务器、域名组，测试 DNS，备份/还原配置。
- **重启**：点击“重启 SmartDNS”应用更改。

## 贡献

欢迎贡献！请 Fork 仓库，创建分支，提交 Pull Request，遵循 PEP 8 规范。

## 许可

采用 MIT 许可证。详情见 LICENSE 文件.

---

问题或建议？请在 Issues 提出！
# iKuai IP 同步服务说明文档

## 概述
`ikuai-ip-update.py` 是一个 Python 脚本，用于自动化更新 iKuai 路由器上的运营商 IP 列表（默认“CN”，中国）。它从公开仓库获取最新的 IP 列表，与本地保存的列表比较，并在检测到变化或运营商条目不存在时更新路由器的自定义运营商设置。脚本以服务形式运行，支持每天、每周或每月定时更新，适用于长期自动化管理。

配套的 `install-iksip.sh` 脚本提供一键安装功能，从 GitHub 下载 `ikuai-ip-update.py`，交互式生成配置文件，并配置为 `systemd` 服务（服务名：`iksip`）。

## 前提条件
- **操作系统**：基于 `systemd` 的 Linux 系统（如 Debian 12、Ubuntu 18.04+、CentOS 7+）。
- **Python 3.x**：确保系统中已安装 Python 3（Debian 12 默认 Python 3.11）。
- **网络访问**：需要联网以下载脚本、依赖和 IP 列表。
- **iKuai 路由器**：路由器需通过 Web 界面可访问，并提供管理员凭据。
- **权限**：安装需 root 或 `sudo` 权限。

## 安装
### 1. 下载安装脚本
将 `install-iksip.sh` 保存到本地，或直接从 GitHub 下载（假设已上传到同一仓库）。

### 2. 赋予执行权限
```bash
chmod +x install-iksip.sh
```

### 3. 运行一键安装
以 root 用户或使用 `sudo` 执行：
```bash
sudo ./install-iksip.sh
```

安装过程：
- 检查环境（Python 3, pip, curl, systemd）。
- 为 Debian 12 强制安装 Python 依赖（`requests`, `tenacity`, `schedule`）。
- 从 GitHub 下载 `ikuai-ip-update.py`（URL: `https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/iKuai/ikuai-ip-update.py`）。
- 交互式生成 `config.json`，提示输入：
  - iKuai 管理地址（`ikuai_url`，如 `http://192.168.1.1`）
  - 管理员账号（`username`）
  - 管理员密码（`password`）
  - ISP 名称（`isp_name`，如 `CN`）
  - 更新周期（`schedule_type`：daily, weekly, monthly）
  - 更新时间（`schedule_time`：HH:MM，如 `00:00`）
  - 每周更新星期（仅 weekly，输入 1-7，1=周一，7=周日）
  - 每月更新日期（仅 monthly，1-28）
- 显示配置并要求确认（y/n），若不确认则重新输入。
- 安装服务到 `/opt/iksip`，配置 `systemd` 服务（`iksip`），并启动。

### 4. 验证安装
- 检查服务状态：
  ```bash
  systemctl status iksip
  ```
- 查看日志：
  ```bash
  cat /opt/iksip/ikuai-ip-update.log
  ```

## 配置
`config.json` 由安装脚本生成，位于 `/opt/iksip/config.json`，包含以下字段：
- `ikuai_url`：iKuai 路由器 Web 界面 URL（如 `http://192.168.1.1`）。
- `username`：管理员用户名。
- `password`：管理员密码。
- `china_ip_url`：IP 列表 URL（默认：`https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/china_ip.txt`）。
- `last_ip_file`：本地 IP 列表存储文件（默认：`last_china_ip.json`）。
- `timeout`：HTTP 请求超时（秒，默认：10）。
- `chunk_size`：API 更新分块大小（默认：1000）。
- `isp_name`：运营商名称（如 `CN`）。
- `schedule_type`：更新周期（`daily`, `weekly`, `monthly`）。
- `schedule_time`：更新时间（HH:MM，如 `00:00`）。
- `schedule_day`：每周更新星期（`monday`, `tuesday`, ..., `sunday`，仅 weekly 有效）。
- `schedule_date`：每月更新日期（1-28，仅 monthly 有效）。

**注意**：修改 `config.json` 后，需重启服务：
```bash
sudo systemctl restart iksip
```

## 工作原理
1. **加载配置**：从 `/opt/iksip/config.json` 读取配置，验证所有字段。
2. **登录**：使用用户名和密码登录 iKuai 路由器。
3. **获取 IP 列表**：从 `china_ip_url` 下载最新 IP 列表，验证 CIDR 格式。
4. **比较 IP 列表**：与本地 `last_ip_file` 比较，检查变化。
5. **检查运营商**：查询路由器上是否存在指定 `isp_name` 条目。
6. **更新运营商**：若 IP 列表变化或条目不存在，更新或创建运营商设置，分块处理（`chunk_size`）。
7. **保存 IP 列表**：将新 IP 列表保存到 `last_ip_file`。
8. **调度任务**：根据 `schedule_type`, `schedule_time`, `schedule_day`, `schedule_date` 定时运行。
9. **日志记录**：将所有操作（登录、获取、更新、错误）记录到 `/opt/iksip/ikuai-ip-update.log`。

## 使用方法
安装后，服务自动以 `iksip` 名称运行，无需手动执行脚本。管理服务命令：
- 查看状态：
  ```bash
  systemctl status iksip
  ```
- 停止服务：
  ```bash
  sudo systemctl stop iksip
  ```
- 重启服务：
  ```bash
  sudo systemctl restart iksip
  ```
- 禁用开机自启：
  ```bash
  sudo systemctl disable iksip
  ```

查看运行日志：
```bash
cat /opt/iksip/ikuai-ip-update.log
```

## 错误处理
- **配置错误**：缺少 `config.json` 或无效字段，脚本退出并记录错误。
- **登录失败**：无法登录路由器，记录错误并跳过更新。
- **IP 列表获取失败**：无法下载 IP 列表，跳过更新并记录错误。
- **API 错误**：路由器 API 调用失败，记录详细错误信息。
- **网络问题**：使用重试机制（3 次，间隔 2 秒）处理网络不稳定。

## Debian 12 特别说明
- **依赖安装**：Debian 12 默认限制外部 `pip` 安装，`install-iksip.sh` 使用 `--break-system-packages` 强制安装 `requests`, `tenacity`, `schedule`。
- **环境**：确保 `apt-get` 源可用，建议配置国内镜像：
  ```bash
  echo "deb http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list
  ```
- **Python**：Debian 12 使用 Python 3.11，脚本已验证兼容。

## 定时任务
脚本内置调度机制（基于 Python `schedule` 库），无需外部工具如 `cron`。更新周期由 `config.json` 的 `schedule_type` 控制：
- **Daily**：每天在 `schedule_time` 运行。
- **Weekly**：每周在 `schedule_day`（如 `sunday`）的 `schedule_time` 运行。
- **Monthly**：每月在 `schedule_date`（1-28）的 `schedule_time` 运行。

## 注意事项
- **网络依赖**：确保路由器和 IP 列表 URL 可访问。
- **配置安全**：`config.json` 权限为 600，仅 root 可读写，保护密码。
- **日志管理**：定期清理 `/opt/iksip/ikuai-ip-update.log`。
- **GitHub 可用性**：若 GitHub URL 不可靠，检查 `china_ip_url` 或联系管理员。
- **服务名**：`iksip`（5 个字符），简洁高效。

## 示例日志
```
2025-05-04 00:00:01,234 [INFO] iKuai IP 同步服务启动
2025-05-04 00:00:01,235 [INFO] 设置调度任务: weekly 周期，时间 02:00
2025-05-04 02:00:00,123 [INFO] 开始执行更新任务
2025-05-04 02:00:00,456 [INFO] 准备登录: http://192.168.1.1/Action/login
2025-05-04 02:00:00,789 [INFO] 登录成功
2025-05-04 02:00:01,012 [INFO] 获取中国 IP 列表: https://raw.githubusercontent.com/...
2025-05-04 02:00:01,345 [INFO] 获取到 1234 条 IP 记录
2025-05-04 02:00:01,678 [INFO] 查询 CN 运营商 ID
2025-05-04 02:00:01,901 [INFO] 找到 CN 运营商 ID: 123
2025-05-04 02:00:02,234 [INFO] 开始更新 CN 运营商
2025-05-04 02:00:02,567 [INFO] CN 运营商分块 1 更新成功 (Result: 10000)
2025-05-04 02:00:02,890 [INFO] 成功保存当前的 IP 列表
2025-05-04 02:00:03,123 [INFO] 更新任务结束
```
# iKuai IP 同步服务说明文档

## 概述
`ikuai-ip-update.py` 是一个 Python 脚本，用于自动更新 iKuai 路由器上的运营商 IP 列表（默认“CN”）。它从指定 URL 获取最新 IP 列表，与本地缓存比较，若有变化或运营商条目不存在，则更新路由器设置。脚本以服务形式运行，支持定时更新（每天、每周、每月）。

配套脚本 `install-iksip.sh` 提供一键安装，支持交互式配置和卸载，部署为 `systemd` 服务（`iksip`）。

## 前提条件
- **操作系统**：基于 `systemd` 的 Linux（如 Ubuntu 18.04+、CentOS 7+、Debian 12）。
- **Python 3**：确保已安装（Debian 12 默认 Python 3.11）。
- **网络**：可访问 GitHub 和 iKuai 路由器。
- **权限**：需 `root` 或 `sudo` 权限。
- **iKuai 路由器**：需提供 Web 界面地址和管理员凭据。

## 安装
1. **下载安装脚本**：
   ```bash
   wget -O install-iksip.sh https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/iKuai/install-iksip.sh
   ```

2. **赋予执行权限**：
   ```bash
   chmod +x install-iksip.sh
   ```

3. **运行脚本**：
   ```bash
   sudo ./install-iksip.sh
   ```
   - 选择操作：
     ```
     1. 安装 iKuai IP 更新服务
     2. 卸载 iKuai IP 更新服务
     3. 退出
     ```
   - 安装（选项 1）：
     - 输入路由器地址（例如 `http://10.0.0.1`）、用户名（默认 `admin`）、密码、运营商名称（默认 `CN`）。
     - 脚本下载 `ikuai-ip-update.py`，生成 `config.json` 和 `config.json.example`，安装依赖，配置服务。
   - 卸载（选项 2）：
     - 停止并删除服务，删除 `/opt/iksip/`（需确认）。
   - 退出（选项 3）：退出脚本。

4. **验证安装**：
   ```bash
   systemctl status iksip
   cat /opt/iksip/ikuai-ip-update.log
   ```

## 配置
配置文件位于 `/opt/iksip/config.json`，主要字段：
- `ikuai_url`：路由器地址（如 `http://10.0.0.1`）。
- `username`, `password`：管理员凭据。
- `china_ip_url`：IP 列表 URL（默认：`https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/china_ip.txt`）。
- `last_ip_file`：本地缓存文件（默认：`last_sync_ip.json`）。
- `isp_name`：运营商名称（默认：`CN`）。
- `schedule_type`：调度周期（`d`=每天，`w`=每周，`m`=每月）。
- `schedule_time`：调度时间（`HH:MM`，如 `05:00`）。
- `schedule_day`：每周星期（`monday` 等，仅每周有效）。
- `schedule_date`：每月日期（1-28，仅每月有效）。

**修改配置**：
```bash
sudo nano /opt/iksip/config.json
sudo systemctl restart iksip
```

## 工作原理
- **加载配置**：读取 `/opt/iksip/config.json`。
- **获取 IP 列表**：从 `china_ip_url` 下载 IP 列表。
- **比较 IP 列表**：与 `last_ip_file` 比较。
- **更新路由器**：若列表变化或运营商不存在，登录 iKuai，更新运营商 IP 列表。
- **验证更新**：检查 iKuai 条数是否匹配。
- **保存缓存**：更新 `last_ip_file`。
- **定时任务**：按 `schedule_type` 和 `schedule_time` 运行。
- **日志**：记录操作到 `/opt/iksip/ikuai-ip-update.log`。

## 使用方法
服务以 `root` 用户运行，自动启动。管理命令：
- 查看状态：`systemctl status iksip`
- 停止服务：`sudo systemctl stop iksip`
- 重启服务：`sudo systemctl restart iksip`
- 查看日志：`cat /opt/iksip/ikuai-ip-update.log`

## 错误处理
- **配置错误**：无效 `config.json`，记录错误并退出。
- **登录失败**：无法登录路由器，跳过更新。
- **IP 列表失败**：无法下载 IP 列表，跳过更新。
- **网络问题**：重试 3 次（间隔 2 秒）。

## 定时任务
内置调度（Python `schedule` 库）：
- **每天**：在 `schedule_time` 运行。
- **每周**：在 `schedule_day` 的 `schedule_time` 运行。
- **每月**：在 `schedule_date` 的 `schedule_time` 运行。

## 注意事项
- **网络**：确保路由器和 IP 列表 URL 可访问。
- **安全**：服务以 `root` 用户运行，定期检查脚本安全性。
- **日志管理**：定期清理日志：
  ```bash
  sudo truncate -s 0 /opt/iksip/ikuai-ip-update.log
  ```
- **配置备份**：修改 `config.json` 前备份。
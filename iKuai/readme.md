# iKuai IP 更新脚本说明文档

## 概述
`ikuai-ip-update.py` 脚本用于自动化更新 iKuai 路由器上的“CN”（中国）运营商 IP 列表。它从公开仓库获取最新的中国 IP 列表，与之前保存的列表进行比较，并在检测到变化或“CN”运营商条目不存在时更新路由器的自定义运营商设置。

## 前提条件
- **Python 3.x**：确保系统中已安装 Python 3。
- **依赖库**：使用以下命令安装所需的 Python 库：
  ```bash
  pip install requests
  ```
- **iKuai 路由器**：路由器需通过其 Web 界面可访问，并且需要管理员凭据。
- **网络访问**：脚本需要联网以获取 IP 列表。

## 配置
在脚本中编辑以下变量以匹配您的环境：

- `IKUAI_URL`：iKuai 路由器 Web 界面的 URL（例如：`http://10.0.0.1`）。
- `USERNAME`：iKuai 路由器的管理员用户名（默认：`admin`）。
- `PASSWORD`：iKuai 路由器的管理员密码（默认：`admin`）。
- `CHINA_IP_URL`：中国 IP 列表的 URL（默认：`https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt`）。
- `LAST_IP_FILE`：本地存储上次获取的 IP 列表的文件（默认：`last_china_ip.json`）。

## 工作原理
1. **登录**：脚本使用提供的凭据登录 iKuai 路由器。
2. **获取 IP 列表**：从指定 URL 下载最新的中国 IP 列表。
3. **比较 IP 列表**：将获取的 IP 列表与之前保存的列表（如果存在）进行比较。
4. **检查 CN 运营商**：检查路由器上是否存在“CN”运营商条目。
5. **更新运营商**：如果 IP 列表发生变化或“CN”运营商条目不存在，脚本会更新或创建“CN”运营商条目并应用新的 IP 列表。
6. **保存 IP 列表**：将更新的 IP 列表保存到本地以供后续比较。
7. **日志记录**：脚本将运行进度和任何错误信息记录到控制台。

## 使用方法
1. 将脚本保存为 `ikuai-ip-update.py`。
2. 根据“配置”部分的说明修改相关变量。
3. 运行脚本：
   ```bash
   python3 ikuai-ip-update.py
   ```
4. 查看控制台输出的进度和错误信息。

## 定时任务
为了保持 IP 列表的最新状态，可以使用 `cron`（Linux）或任务计划程序（Windows）等工具定时运行脚本。例如，在 Linux 上每天午夜运行：

```bash
0 0 * * * /usr/bin/python3 /path/to/ikuai-ip-update.py >> /path/to/logfile.log 2>&1
```

## 错误处理
- **登录失败**：如果登录失败，脚本将退出并显示错误信息。
- **IP 列表获取失败**：如果无法获取 IP 列表，脚本将跳过更新并退出。
- **API 错误**：脚本会记录任何 API 调用相关的错误信息。
## miniChat

**miniChat** 是一个轻量、临时的私密聊天室，支持电脑和手机浏览器使用。  
- **核心特点**：
  - 服务器仅作为消息中转，不存储任何数据。
  - 新加入用户无法查看历史聊天记录。
  - 刷新浏览器即清空本地聊天记录。
  - 强调隐私，无监管、无敏感词过滤。
- **使用场景**：适合需要快速、安全、临时沟通的场景。

### 安装流程

要将 miniChat 安装为系统服务，请按照以下步骤操作：

1. **准备工作**：
   - 确保您使用的是基于 Debian/Ubuntu 的 Linux 系统（如 Ubuntu 20.04 或更高版本）。
   - 确保您有 root 权限以执行安装脚本。
   - 将以下文件放置在同一目录下：`server.py`、`index.html` 和 `install_minichat_service.sh`。

2. **运行安装脚本**：
   - 打开终端，进入包含上述文件的目录。
   - 赋予安装脚本执行权限：
     ```bash
     chmod +x install_minichat_service.sh
     ```
   - 以 root 权限运行脚本：
     ```bash
     sudo ./install_minichat_service.sh
     ```
   - 脚本将自动完成以下操作：
     - 安装必要的依赖（如 Python3、pip、nginx 等）。
     - 创建专用用户 `minichat` 用于运行服务。
     - 在 `/opt/miniChat` 目录下创建安装目录并复制文件。
     - 设置 Python 虚拟环境并安装所需 Python 包（`aiohttp`、`aiohttp-jinja2`、`jinja2`）。
     - 创建并启用 systemd 服务 `minichat.service`。
     - 启动 miniChat 服务。

3. **验证安装**：
   - 检查服务状态：
     ```bash
     systemctl status minichat
     ```
   - 查看服务日志：
     ```bash
     journalctl -u minichat.service
     ```
   - 如果服务正常运行，您可以通过浏览器访问 `http://<您的服务器IP>:8080` 来使用聊天室。

4. **配置 Nginx 反向代理**：
   - 按照下方的 “Nginx 反向代理配置” 部分配置 Nginx，以支持 HTTPS 和 WebSocket。
   - 配置完成后，重启 Nginx：
     ```bash
     systemctl restart nginx
     ```

5. **故障排查**：
   - 如果服务未能启动，检查日志以获取错误信息：
     ```bash
     journalctl -u minichat.service
     ```
   - 确保端口 8080 未被占用。
   - 验证 Nginx 配置是否正确：
     ```bash
     nginx -t
     ```

### 依赖安装
运行 miniChat 需要以下 Python 扩展（安装脚本会自动处理）：
```bash
pip install aiohttp aiohttp-jinja2 jinja2
```

### Nginx 反向代理配置
以下是推荐的 Nginx 配置，用于支持 HTTPS 和 WebSocket：
```nginx
server {
    listen 60000 ssl; # 对外监听端口
    server_name example.com; # 替换为您的域名
    ssl_certificate /path/to/example.com.pem; # 证书路径
    ssl_certificate_key /path/to/example.com.key; # 证书密钥路径
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 静态页面
    location / {
        proxy_pass http://<服务器IP>:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # WebSocket
    location /ws {
        proxy_pass http://<服务器IP>:8080/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
}
```
**注意**：请将 `<服务器IP>` 替换为您的实际服务器 IP 地址，`example.com` 替换为您的域名，并确保证书路径正确。

### 联系方式
- **GitHub Issues**：提交问题或咨询。  
- **Telegram**：@FreeQQ
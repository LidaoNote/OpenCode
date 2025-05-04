以下是对您提供的 miniChat 描述和配置的润色版本，语言更流畅、简洁，结构更清晰，同时保持技术细节准确无误：

---

## miniChat

**miniChat** 是一个轻量、临时的私密聊天室，支持电脑和手机浏览器使用。  
- **核心特点**：
  - 服务器仅作为消息中转，不存储任何数据。
  - 新加入用户无法查看历史聊天记录。
  - 刷新浏览器即清空本地聊天记录。
  - 强调隐私，无监管、无敏感词过滤。
- **使用场景**：适合需要快速、安全、临时沟通的场景。

### 依赖安装
运行 miniChat 需要以下 Python 扩展：
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
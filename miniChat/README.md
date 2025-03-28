# miniChat
一个迷你的聊天室。
可以在电脑和手机浏览器上使用
服务器仅作为中转，不存储任何信息
后进聊天室的无法看到先前的聊天内容，刷新浏览器会清空聊天记录
主打私密临时聊天
无监管无敏感词

# 依赖扩展安装
```
pip install aiohttp aiohttp_jinja2 jinja2
```

# nginx反代设置
```
server {
    listen 60000 ssl; # 对外监听端口
    server_name name.com;  # 添加域名
    ssl_certificate /cert/name.com.pem; #
    ssl_certificate_key /cert/name.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;  # 修正 avoid 为 aNULL

    # 静态页面
    location / {
        proxy_pass http://IP:8080; 
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # WebSocket
    location /ws {
        proxy_pass http://IP:8080/ws;
        proxy_http_version 1.1;  # 支持 WebSocket
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
}
```

## 联系方式

- **GitHub Issues**：报告问题或提问。
- **Telegram**：@FreeQQ
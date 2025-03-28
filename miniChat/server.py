#!/usr/bin/env python3

from aiohttp import web, WSMsgType
import aiohttp_jinja2
import jinja2
import json
import asyncio
import logging
import time
import os

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

users = {}  # 存储 {username: {'ws': ws, 'fingerprint': fingerprint, 'last_active': timestamp}}
connections = {}  # WebSocket 连接与用户名的映射

async def websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=30)  # 启用内置心跳
    await ws.prepare(request)
    logger.debug(f"New WebSocket connection from {request.remote}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                event = data.get('event')

                if event == 'join':
                    username = data['name']
                    fingerprint = data.get('fingerprint')
                    if not fingerprint:
                        await ws.send_json({'event': 'error', 'error': '缺少指纹信息'})
                        return ws
                    if username in users and users[username]['fingerprint'] != fingerprint:
                        await ws.send_json({'event': 'name_taken', 'error': '用户名已存在'})
                        return ws
                    # 如果是重连，检查指纹是否匹配
                    if username in users and users[username]['fingerprint'] == fingerprint:
                        old_ws = users[username]['ws']
                        if old_ws in connections:
                            del connections[old_ws]  # 移除旧连接
                        logger.debug(f"{username} reconnected with fingerprint {fingerprint}")
                    else:
                        users[username] = {'ws': ws, 'fingerprint': fingerprint, 'last_active': time.time()}
                        logger.debug(f"{username} joined with fingerprint {fingerprint}")
                        await broadcast({'name': '系统', 'msg': f'{username} 加入了聊天室'})
                    connections[ws] = username
                    users[username]['ws'] = ws
                    users[username]['last_active'] = time.time()  # 更新最后活动时间
                    await ws.send_json({'event': 'join_success', 'name': username, 'fingerprint': fingerprint})

                elif event == 'message' and ws in connections:
                    username = connections[ws]
                    users[username]['last_active'] = time.time()  # 更新最后活动时间
                    await broadcast({'name': username, 'msg': data['msg']})

                elif event == 'ping' and ws in connections:
                    username = connections[ws]
                    users[username]['last_active'] = time.time()  # 更新最后活动时间
                    await ws.send_json({'event': 'pong'})

    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}")
    finally:
        if ws in connections:
            username = connections.pop(ws)
            if username in users and users[username]['ws'] == ws:
                logger.debug(f"{username} disconnected, awaiting potential reconnect")

    return ws

async def broadcast(data, exclude=None):
    if connections:
        message = {'event': 'message', 'name': data['name'], 'msg': data['msg']} if 'msg' in data else data
        await asyncio.gather(
            *[ws.send_json(message) for ws in connections if ws != exclude],
            return_exceptions=True
        )

async def check_offline_users():
    while True:
        await asyncio.sleep(5)  # 每 5 秒检查一次
        current_time = time.time()
        for username in list(users.keys()):
            user_info = users[username]
            if (current_time - user_info['last_active'] > 10 and
                (user_info['ws'].closed or user_info['ws'] not in connections)):
                # 用户超过 10 秒未活动且连接已关闭，判定为离线
                del users[username]
                if user_info['ws'] in connections:
                    del connections[user_info['ws']]
                await broadcast({'name': '系统', 'msg': f'{username} 已离线'})
                logger.debug(f"{username} marked as offline")

async def on_startup(app):
    # 在应用启动时注册离线检查任务
    asyncio.create_task(check_offline_users())
    logger.info("Offline check task started")

async def index(request):
    return aiohttp_jinja2.render_template('index.html', request, {})

app = web.Application()

# 获取当前脚本文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(current_dir))

app.router.add_get('/', index)
app.router.add_get('/ws', websocket_handler)
app.on_startup.append(on_startup)  # 注册启动时的回调函数

if __name__ == '__main__':
    logger.info("Server starting on port 8080")
    web.run_app(app, host='0.0.0.0', port=8080)

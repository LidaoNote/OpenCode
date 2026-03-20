"""
支持多会话的 WebShell
"""
import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import asyncssh
import os
import tempfile
import configparser
from pydantic import BaseModel
from typing import Optional, List
import struct
import base64
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateNumbers, RSAPublicNumbers
from cryptography.hazmat.primitives import serialization


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from pathlib import Path
 
# 获取当前脚本所在的目录
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
SESSIONS_DIR = BASE_DIR / "Sessions"
USER_KEYS_DIR = BASE_DIR / "UserKeys"

SESSIONS_DIR.mkdir(exist_ok=True)
USER_KEYS_DIR.mkdir(exist_ok=True)

# 接口路由定义在下方

def parse_xshell_pri(pri_content: str) -> str:
    lines = pri_content.strip().splitlines()
    b64_pub = ""
    pub_start = -1
    for i, line in enumerate(lines):
        if line.startswith("AAAAB3NzaC"):
            pub_start = i
            break
            
    if pub_start != -1:
        for line in lines[pub_start:]:
            if line.startswith("----") or not line.strip() or line.startswith("bnNzc2gta2V5"):
                break
            b64_pub += line
            
    b64_priv = ""
    priv_start = -1
    for i, line in enumerate(lines):
        if line.startswith("bnNzc2gta2V5"):
            priv_start = i
            break
            
    if priv_start != -1:
        for line in lines[priv_start:]:
            if line.startswith("----") or not line.strip():
                break
            b64_priv += line

    if not b64_pub or not b64_priv:
        raise ValueError("无法解析 Xshell 私钥格式")
        
    pub = base64.b64decode(b64_pub)
    raw = base64.b64decode(b64_priv)

    def read_string(data, offset):
        l = struct.unpack(">I", data[offset:offset+4])[0]
        return data[offset+4:offset+4+l], offset+4+l

    def to_int(b):
        return int.from_bytes(b, byteorder='big', signed=False)

    p_off = 0
    keytype_pub, p_off = read_string(pub, p_off)
    e, p_off = read_string(pub, p_off)
    n, p_off = read_string(pub, p_off)

    offset = raw.find(b'\0') + 1
    cipher, offset = read_string(raw, offset)
    if cipher != b'none':
        raise ValueError("不支持带密码的 Xshell 私钥解析，请取消密码保护，或导出为 OpenSSH 格式")
        
    kdf, offset = read_string(raw, offset)
    kdfopt, offset = read_string(raw, offset)
    offset += 4

    privkey, offset = read_string(raw, offset)
    pr_off = 8
    c0, pr_off = read_string(privkey, pr_off)
    c1, pr_off = read_string(privkey, pr_off)
    c2, pr_off = read_string(privkey, pr_off)
    c3, pr_off = read_string(privkey, pr_off)

    n_i, e_i = to_int(n), to_int(e)
    p_i, q_i = to_int(c0), to_int(c1)
    d_i = to_int(c2)
    iqmp_i = to_int(c3)

    p_new = q_i
    q_new = p_i
    dmp1_i = d_i % (p_new - 1)
    dmq1_i = d_i % (q_new - 1)

    pub_nums = RSAPublicNumbers(e=e_i, n=n_i)
    priv_nums = RSAPrivateNumbers(
        p=p_new, q=q_new, d=d_i,
        dmp1=dmp1_i, dmq1=dmq1_i,
        iqmp=iqmp_i,
        public_numbers=pub_nums
    )
    
    priv_key = priv_nums.private_key()
    pem = priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )
    return pem.decode('ascii')


# 活跃的连接/会话管理（内存中的会话对象）
class SSHSession:
    def __init__(self, conn, process, host, user, port, title):
        self.conn = conn
        self.process = process
        self.host = host
        self.user = user
        self.port = port
        self.title = title
        self.sftp = None
        self.listeners = set()
        self.buffer = bytearray()
        # 简单的回滚缓冲区（用于新连接补发历史输出）
        self.max_buffer = 1024 * 100  # 100KB 缓冲区
        # 最大缓冲区大小，超过则截断为最近的内容（100KB）
        self.read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        logger.info(f"Starting read loop for {self.host} ({self.title})")
        try:
            while True:
                data = await self.process.stdout.read(4096)
                if not data:
                    break
                
                # 更新缓冲区 —— 使用高效的追加与切片操作
                self.buffer.extend(data)
                if len(self.buffer) > self.max_buffer:
                    # 超出最大长度时截断，保留最近的数据
                    self.buffer = self.buffer[-self.max_buffer:]
                
                # 将数据广播给监听者的副本，以避免集合在迭代中被修改导致的问题
                if self.listeners:
                    targets = list(self.listeners)
                    for ws in targets:
                        try:
                            await ws.send_bytes(data)
                        except Exception:
                            # 如果发送失败，说明监听器可能已断开，后续断开操作会清理
                            pass
        except Exception as e:
            logger.error(f"Read loop error for {self.host}: {e}")
        finally:
            logger.info(f"Read loop finished for {self.host}")

    async def attach(self, websocket: WebSocket):
        self.listeners.add(websocket)
        # 发送当前缓冲区内容以便新连接补上历史输出
        if self.buffer:
            try:
                await websocket.send_bytes(bytes(self.buffer))
            except Exception as e:
                logger.error(f"Failed to send buffer to new listener: {e}")

    def detach(self, websocket: WebSocket):
        if websocket in self.listeners:
            self.listeners.remove(websocket)
            logger.info(f"Listener detached from {self.host}")

class LoginRequest(BaseModel):
    host: str
    port: int = 22
    username: Optional[str] = "root"
    password: Optional[str] = None
    use_key: bool = False
    key_name: Optional[str] = None
    name: Optional[str] = None

class ConnectionManager:
    def __init__(self):
        self.active_sessions: dict[str, SSHSession] = {}

    async def connect(self, req: LoginRequest):
        try:
            username = req.username or "root"
            logger.info(f"Attempting SSH connection to {req.host}:{req.port} as {username}")
            
            # 准备连接参数（主机/端口/用户名等）
            conn_kwargs = {
                "host": req.host,
                "port": req.port,
                "username": username,
                "known_hosts": None,
                "login_timeout": 15
            }

            if req.use_key and req.key_name:
                key_path = os.path.join(USER_KEYS_DIR, req.key_name)
                if os.path.exists(key_path):
                    try:
                        with open(key_path, 'r') as kf:
                            key_data = kf.read()
                        
                        if "NSSSH PRIVATE KEY" in key_data or "bnNzc2gta2V5LXY" in key_data:
                            key_data = parse_xshell_pri(key_data)

                        # 验证私钥能否被导入（检查格式与是否需口令）
                        key_obj = asyncssh.import_private_key(key_data, passphrase=req.password)
                        conn_kwargs["client_keys"] = [key_obj]
                        if req.password:
                            conn_kwargs["passphrase"] = req.password
                    except Exception as key_err:
                        logger.error(f"Private key error: {key_err}")
                        raise ValueError(f"私钥验证失败: {str(key_err)}。请确保是 OpenSSH 格式，若有密码请填写在密码框中。")
                else:
                    raise ValueError(f"私钥文件 {req.key_name} 不存在")
            else:
                conn_kwargs["password"] = req.password

            conn = await asyncssh.connect(**conn_kwargs)
            process = await conn.create_process(term_type='xterm-256color', term_size=(80, 24), encoding=None)
            
            session_id = f"{req.host}_{username}_{os.urandom(4).hex()}"
            title = req.name or req.host
            self.active_sessions[session_id] = SSHSession(conn, process, req.host, username, req.port, title)
            logger.info(f"Successfully created session: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"SSH Connection failed: {str(e)}")
            raise e
    
    async def disconnect(self, session_id: str):
        session = self.active_sessions.get(session_id)
        if session:
            try:
                if session.sftp:
                    session.sftp.exit()
            except Exception as e:
                logger.error(f"Error closing sftp for {session_id}: {e}")
            try:
                session.process.terminate()
                session.process.close()
                session.conn.close()
            except Exception as e:
                logger.error(f"Error closing conn for {session_id}: {e}")
            if session.read_task:
                session.read_task.cancel()
            del self.active_sessions[session_id]
            logger.info(f"Session {session_id} removed")

    def get_active_sessions(self):
        return [
            {
                "sid": sid,
                "host": s.host,
                "user": s.user,
                "port": s.port,
                "title": s.title
            }
            for sid, s in self.active_sessions.items()
        ]

    async def get_sftp(self, session_id):
        session = self.active_sessions.get(session_id)
        if not session:
            return None
        if not session.sftp:
            session.sftp = await session.conn.start_sftp_client()
        return session.sftp

manager = ConnectionManager()

@app.post("/login")
async def login(req: LoginRequest):
    try:
        session_id = await manager.connect(req)
        return {"sessionId": session_id}
    except Exception as e:
        return JSONResponse(status_code=401, content={"message": str(e)})

@app.get("/active-sessions")
async def list_active_sessions():
    """返回当前仍然存活的会话"""
    return manager.get_active_sessions()

@app.delete("/session/{session_id}")
async def close_session(session_id: str):
    await manager.disconnect(session_id)
    return {"message": "Success"}

@app.get("/keys")
async def list_keys():
    try:
        if not os.path.exists(USER_KEYS_DIR):
            return []
        keys = [f for f in os.listdir(USER_KEYS_DIR) if f.endswith('.pri')]
        return keys
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    session = manager.active_sessions.get(session_id)
    if not session:
        logger.error(f"WebSocket attempt for invalid session: {session_id}")
        await websocket.close(code=1008)
        return

    # 将此 websocket 关联到会话的广播器，以接收远程终端输出
    await session.attach(websocket)
    logger.info(f"WebSocket attached to session {session_id}")

    try:
        while True:
            # 接收原始消息，以同时处理文本和二进制数据
            msg = await websocket.receive()
            
            # 明确处理断开事件，避免出现运行时错误
            if msg["type"] == "websocket.disconnect":
                logger.info(f"WebSocket disconnect signal for {session_id}")
                break

            if msg.get("bytes"):
                # 直接的二进制数据（例如键盘中断序列）
                session.process.stdin.write(msg["bytes"])
            elif "text" in msg:
                data = msg["text"]
                # 尝试解析为 JSON，用于处理调整终端大小的命令
                if data.startswith('{'):
                    try:
                        msg_json = json.loads(data)
                        if msg_json.get("type") == "resize":
                            cols = msg_json.get("cols", 80)
                            rows = msg_json.get("rows", 24)
                            logger.info(f"Resizing session {session_id} to {cols}x{rows}")
                            session.process.change_terminal_size(cols, rows)
                            continue
                    except json.JSONDecodeError:
                        pass
                
                # 否则当作终端输入发送给远程进程
                session.process.stdin.write(data.encode('utf-8'))
    except Exception as e:
        logger.error(f"WebSocket loop error for {session_id}: {e}")
    finally:
        session.detach(websocket)

@app.get("/sftp/list/{session_id}")
async def sftp_list(session_id: str, path: str = "."):
    sftp = await manager.get_sftp(session_id)
    if not sftp:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
    
    try:
        # Resolve to absolute path on the remote server
        real_path = await sftp.realpath(path)
        files = await sftp.listdir(real_path)
        result = []
        for f in files:
            full_path = os.path.join(real_path, f)
            try:
                # Use lstat to get raw attributes, avoiding broken symlink errors
                attrs = await sftp.lstat(full_path)
                # Check for symlink
                is_link = (attrs.permissions & 0o120000) == 0o120000
                is_dir = (attrs.permissions & 0o40000) != 0
                
                # If it is a symlink, try to check if the target is a directory
                if is_link:
                    try:
                        target_attrs = await sftp.stat(full_path)
                        is_dir = (target_attrs.permissions & 0o40000) != 0
                    except:
                        # Broken symlink, keep is_dir as false
                        pass
                
                result.append({
                    "name": f,
                    "is_dir": is_dir,
                    "is_link": is_link,
                    "size": attrs.size,
                    "mtime": attrs.mtime,
                    "permissions": oct(attrs.permissions & 0o777),
                    "uid": attrs.uid,
                    "gid": attrs.gid
                })
            except Exception:
                # Add basic entry even if stat/lstat fails
                result.append({
                    "name": f,
                    "is_dir": False,
                    "size": 0,
                    "mtime": 0
                })
        return {"path": real_path, "files": result}
    except Exception as e:
        logger.error(f"SFTP List error for {session_id} on path {path}: {str(e)}")
        return JSONResponse(status_code=500, content={"message": f"Listing failed: {str(e)}"})

@app.delete("/sftp/delete/{session_id}")
async def sftp_delete(session_id: str, path: str):
    sftp = await manager.get_sftp(session_id)
    if not sftp: return JSONResponse(status_code=404, content={"message": "Session not found"})
    try:
        attrs = await sftp.lstat(path)
        is_dir = (attrs.permissions & 0o40000) != 0
        is_link = (attrs.permissions & 0o120000) == 0o120000
        if is_dir and not is_link:
            await sftp.rmtree(path)
        else:
            await sftp.remove(path)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sftp/mkdir/{session_id}")
async def sftp_mkdir(session_id: str, path: str = Form(...)):
    sftp = await manager.get_sftp(session_id)
    if not sftp: return JSONResponse(status_code=404, content={"message": "Session not found"})
    try:
        await sftp.mkdir(path)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sftp/touch/{session_id}")
async def sftp_touch(session_id: str, path: str = Form(...)):
    sftp = await manager.get_sftp(session_id)
    if not sftp: return JSONResponse(status_code=404, content={"message": "Session not found"})
    try:
        async with sftp.open(path, 'w') as f:
            await f.write("")
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sftp/rename/{session_id}")
async def sftp_rename(session_id: str, old_path: str = Form(...), new_path: str = Form(...)):
    sftp = await manager.get_sftp(session_id)
    if not sftp: return JSONResponse(status_code=404, content={"message": "Session not found"})
    try:
        await sftp.rename(old_path, new_path)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sftp/chmod/{session_id}")
async def sftp_chmod(session_id: str, path: str = Form(...), mode: str = Form(...)):
    sftp = await manager.get_sftp(session_id)
    if not sftp: return JSONResponse(status_code=404, content={"message": "Session not found"})
    try:
        # 将像 "755" 这样的八进制字符串转换为整数
        await sftp.chmod(path, int(mode, 8))
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/sftp/download/{session_id}")
async def sftp_download(session_id: str, path: str):
    sftp = await manager.get_sftp(session_id)
    if not sftp:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
    
    try:
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp:
            await sftp.get(path, tmp.name, preserve=True)
            tmp_path = tmp.name
        return FileResponse(tmp_path, filename=os.path.basename(path))
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sftp/upload/{session_id}")
async def sftp_upload(session_id: str, remote_path: str = Form(...), file: UploadFile = File(...)):
    sftp = await manager.get_sftp(session_id)
    if not sftp:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
    
    try:
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        await sftp.put(tmp_path, os.path.join(remote_path, file.filename))
        os.unlink(tmp_path)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

class TransferRequest(BaseModel):
    direction: str  # 传输方向："upload"（上传）或 "download"（下载）
    local_path: str
    remote_path: str

@app.post("/sftp/transfer/{session_id}")
async def sftp_direct_transfer(session_id: str, req: TransferRequest):
    sftp = await manager.get_sftp(session_id)
    if not sftp:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
    
    def progress_handler(src, dst, transferred, total):
        session = manager.active_sessions.get(session_id)
        if session and session.listeners:
            msg = json.dumps({
                "__type__": "sftp_progress",
                "src": str(src),
                "transferred": transferred,
                "total": total
            })
            for ws in list(session.listeners):
                try: asyncio.create_task(ws.send_text(msg))
                except: pass

    try:
        if req.direction == "upload":
            if not os.path.exists(req.local_path):
                return JSONResponse(status_code=400, content={"message": "Local file not found"})
            await sftp.put(req.local_path, req.remote_path, recurse=True, preserve=True, progress_handler=progress_handler)
        elif req.direction == "download":
            await sftp.get(req.remote_path, req.local_path, recurse=True, preserve=True, progress_handler=progress_handler)
        else:
            return JSONResponse(status_code=400, content={"message": "Invalid direction"})
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/local/read")
async def local_read(path: str):
    try:
        if not os.path.exists(path):
            return JSONResponse(status_code=404, content={"message": "File not found"})
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/local/write")
async def local_write(data: dict):
    path = data.get("path")
    content = data.get("content", "")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})



@app.get("/local/list")
async def local_list(path: str = str(Path.home())):
    try:
        resolved_path = os.path.abspath(path)
        if not os.path.exists(resolved_path):
            return JSONResponse(status_code=404, content={"message": "Path not found"})
        
        result = []
        # 在列表中加入上级目录指示项（".."），便于前端导航到上级目录
        if os.path.dirname(resolved_path) != resolved_path:
             result.append({
                "name": "..",
                "is_dir": True,
                "size": 0,
                "mtime": 0
            })

        for f in os.listdir(resolved_path):
            full_path = os.path.join(resolved_path, f)
            try:
                is_dir = os.path.isdir(full_path)
                stat = os.stat(full_path)
                result.append({
                    "name": f,
                    "is_dir": is_dir,
                    "size": stat.st_size if not is_dir else 0,
                    "mtime": stat.st_mtime
                })
            except OSError:
                # 跳过因权限问题无法访问的文件
                pass
        return {"path": resolved_path, "files": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/sftp/read/{session_id}")
async def sftp_read(session_id: str, path: str):
    sftp = await manager.get_sftp(session_id)
    if not sftp:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
    try:
        # Standard open followed by read in binary mode.
        # This handles symlinks automatically on the server side and is the most compatible.
        async with sftp.open(path, 'rb') as f:
            data = await f.read()
            
        # Try UTF-8 first, fallback to common Chinese/Latin encodings
        content = None
        for encoding in ['utf-8', 'gbk', 'latin-1']:
            try:
                content = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            content = data.decode('utf-8', errors='replace')
            
        return {"content": content}
    except Exception as e:
        logger.error(f"SFTP Read fail (Session {session_id}, Path {path}): {type(e).__name__} - {str(e)}")
        
        # Check if it was a directory to provide a more descriptive error if it failed
        try:
            attrs = await sftp.stat(path)
            if (attrs.permissions & 0o40000) != 0:
                return JSONResponse(status_code=400, content={"message": "Cannot read directory as a file"})
        except:
            pass
            
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sftp/write/{session_id}")
async def sftp_write(session_id: str, data: dict):
    path = data.get("path")
    content = data.get("content")
    sftp = await manager.get_sftp(session_id)
    if not sftp:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
    try:
        if isinstance(content, str):
            content = content.encode('utf-8')
        async with sftp.open(path, 'wb') as f:
            await f.write(content)
        return {"message": "Success"}
    except Exception as e:
        logger.error(f"SFTP Write error for {session_id} on path {path}: {str(e)}")
        return JSONResponse(status_code=500, content={"message": str(e)})

# 会话管理端点
@app.get("/sessions")
async def list_sessions():
    """递归列出 SESSIONS_DIR 下的会话文件和文件夹"""
    if not os.path.exists(SESSIONS_DIR):
        return {"name": "所有会话", "type": "folder", "children": []}

    def get_session_tree(current_path, name="所有会话"):
        node = {
            "name": name,
            "type": "folder",
            "path": os.path.relpath(current_path, SESSIONS_DIR) if current_path != str(SESSIONS_DIR) else ".",
            "children": []
        }
        
        try:
            items = os.listdir(current_path)
        except Exception as e:
            logger.error(f"Failed to list {current_path}: {e}")
            return node

        for item in sorted(items):
            if item.startswith('.'): continue
            full_path = os.path.join(current_path, item)
            
            if os.path.isdir(full_path):
                node["children"].append(get_session_tree(full_path, item))
            elif item.endswith(".xsh"):
                config = configparser.ConfigParser(interpolation=None)
                session_data = {
                    "name": item.replace(".xsh", ""),
                    "filename": item,
                    "type": "file",
                    "path": os.path.relpath(full_path, SESSIONS_DIR)
                }
                
                # 尝试为属性面板提取一些基本信息（主机/端口/用户等）
                for enc in ['utf-8-sig', 'utf-8', 'utf-16']:
                    try:
                        with open(full_path, 'r', encoding=enc) as cf:
                            file_str = cf.read()
                            if '[INFORMATION]' in file_str.upper() or '[CONNECTION]' in file_str.upper():
                                config.read_string(file_str)
                                
                                def get_val(sections, keys_to_find, default=""):
                                    for s in sections:
                                        actual_section = next((sec for sec in config.sections() if sec.upper() == s.upper()), None)
                                        if actual_section:
                                            for key_in_config in config[actual_section]:
                                                for kf in keys_to_find:
                                                    if key_in_config.upper() == kf.upper():
                                                        return config[actual_section][key_in_config]
                                    return default

                                session_data.update({
                                    "host": get_val(["CONNECTION", "Connection"], ["Host"]),
                                    "port": get_val(["CONNECTION", "Connection"], ["Port"], "22"),
                                    "user": get_val(["CONNECTION:AUTHENTICATION", "Authentication", "CONNECTION", "Connection"], ["UserName", "username"]),
                                    "pass": get_val(["CONNECTION:AUTHENTICATION", "Authentication"], ["Password", "password"])
                                })
                                break
                    except:
                        # 无法以该编码读取时继续尝试下一个编码
                        continue
                node["children"].append(session_data)
        return node

    return get_session_tree(SESSIONS_DIR)

@app.post("/sessions/mkdir")
async def make_session_dir(data: dict):
    path = data.get("path", "")
    # 基本路径清理（移除上级引用，避免目录穿越）
    path = path.replace("..", "").strip("/")
    if not path: return JSONResponse(status_code=400, content={"message": "Invalid path"})
    
    full_path = os.path.join(SESSIONS_DIR, path)
    try:
        os.makedirs(full_path, exist_ok=True)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sessions/open-folder")
async def open_session_folder(data: dict):
    # 仅在服务器与用户在同一台机器上运行时有效（用于本地运行场景）
    import subprocess
    import platform
    path = os.path.join(SESSIONS_DIR, data.get("path", ""))
    abs_path = os.path.abspath(path)
    
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", abs_path])
        elif platform.system() == "Windows":
            os.startfile(abs_path)
        else:
            subprocess.run(["xdg-open", abs_path])
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.delete("/sessions")
async def delete_session(path: str):
    # 清理传入路径，防止非法或越权删除
    path = path.replace("..", "").strip("/")
    if not path or path == ".": 
        return JSONResponse(status_code=400, content={"message": "Cannot delete root"})
    
    full_path = os.path.join(SESSIONS_DIR, path)
    if not os.path.exists(full_path):
        return JSONResponse(status_code=404, content={"message": "Path not found"})
        
    try:
        if os.path.isdir(full_path):
            import shutil
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.post("/sessions")
async def save_session(data: dict):
    name = data.get("name", "New Session")
    folder_path = data.get("folder", "")  # 相对于 SESSIONS_DIR 的路径
    filename = f"{name}.xsh"
    
    target_dir = os.path.join(SESSIONS_DIR, folder_path)
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, filename)
    
    original_path = data.get("originalPath")
    if original_path:
        old_full_path = os.path.join(SESSIONS_DIR, original_path)
        if os.path.exists(old_full_path) and os.path.abspath(old_full_path) != os.path.abspath(filepath):
            try:
                os.remove(old_full_path)
            except Exception as e:
                logger.error(f"Failed to remove old session file: {e}")
    
    config = configparser.ConfigParser()
    config["Information"] = {"Version": "1.1"}
    config["Connection"] = {
        "Host": data.get("host", ""),
        "Port": str(data.get("port", "22")),
        "Protocol": "SSH",
        "UserName": data.get("user", "")
    }
    config["Authentication"] = {
        "Method": "Password",
        "Password": data.get("pass", "")
    }
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            config.write(f)
        return {"message": "Success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

# 从 `frontend` 目录提供静态文件（前端资源）
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # 如果请求的资源在前端目录存在则直接返回该文件
        local_file = os.path.join(FRONTEND_DIR, full_path)
        if full_path and os.path.isfile(local_file):
            return FileResponse(local_file)
        # 否则统一返回单页应用的入口 index.html
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8108)
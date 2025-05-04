#!/usr/bin/env python3
import requests
import hashlib
import time
import json
import os
import logging
import schedule
import threading
import signal
from tenacity import retry, stop_after_attempt, wait_fixed
import ipaddress

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("ikuai-ip-update.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# 加载配置文件（假设与脚本在同一目录）
config_path = os.path.join(os.path.dirname(__file__), "config.json")
try:
    with open(config_path, "r") as f:
        config = json.load(f)
except FileNotFoundError:
    logger.error(f"配置文件 {config_path} 不存在")
    exit(1)
except json.JSONDecodeError:
    logger.error(f"配置文件 {config_path} 格式错误")
    exit(1)

# 从 config.json 获取所有配置，无默认值
required_configs = [
    "ikuai_url",
    "username",
    "password",
    "china_ip_url",
    "last_ip_file",
    "timeout",
    "chunk_size",
    "isp_name",
    "schedule_type",
    "schedule_time",
    "schedule_day",
    "schedule_date"
]
for key in required_configs:
    if key not in config:
        logger.error(f"配置文件缺少必需项: {key}")
        exit(1)

IKUAI_URL = config["ikuai_url"]
USERNAME = config["username"]
PASSWORD = config["password"]
CHINA_IP_URL = config["china_ip_url"]
LAST_IP_FILE = config["last_ip_file"]
TIMEOUT = config["timeout"]
CHUNK_SIZE = config["chunk_size"]
ISP_NAME = config["isp_name"]
SCHEDULE_TYPE = config["schedule_type"].lower()
SCHEDULE_TIME = config["schedule_time"]
SCHEDULE_DAY = config["schedule_day"].lower()
SCHEDULE_DATE = config["schedule_date"]

# 验证关键配置
if SCHEDULE_TYPE not in ["d", "w", "m"]:
    logger.error(f"无效的 schedule_type: {SCHEDULE_TYPE}，必须为 d（每天）, w（每周）或 m（每月）")
    exit(1)
if not (1 <= SCHEDULE_DATE <= 28):
    logger.error(f"无效的 schedule_date: {SCHEDULE_DATE}，必须在 1-28 之间")
    exit(1)
if SCHEDULE_DAY not in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
    logger.error(f"无效的 schedule_day: {SCHEDULE_DAY}，必须为 monday, tuesday 等")
    exit(1)
try:
    # 验证 schedule_time 格式 (HH:MM)
    time.strptime(SCHEDULE_TIME, "%H:%M")
except ValueError:
    logger.error(f"无效的 schedule_time: {SCHEDULE_TIME}，必须为 HH:MM 格式")
    exit(1)
if not isinstance(TIMEOUT, (int, float)) or TIMEOUT <= 0:
    logger.error(f"无效的 timeout: {TIMEOUT}，必须为正数")
    exit(1)
if not isinstance(CHUNK_SIZE, int) or CHUNK_SIZE <= 0:
    logger.error(f"无效的 chunk_size: {CHUNK_SIZE}，必须为正整数")
    exit(1)

# API 端点
LOGIN_API = f"{IKUAI_URL}/Action/login"
CUSTOM_ISP_API = f"{IKUAI_URL}/Action/call"

# 全局标志，用于控制服务停止
RUNNING = True

def md5_hash(text):
    """计算文本的 MD5 哈希值。

    Args:
        text (str): 要加密的文本。

    Returns:
        str: MD5 哈希值（十六进制）。
    """
    return hashlib.md5(text.encode('utf-8')).hexdigest()

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def login():
    """登录 iKuai 路由器并返回会话对象。

    Returns:
        requests.Session: 登录成功时的会话对象，失败时返回 None。
    """
    logger.info(f"准备登录: {LOGIN_API}")
    payload = {
        "username": USERNAME,
        "passwd": md5_hash(PASSWORD),
        "pass": str(int(time.time() * 1000)),
        "remember_password": ""
    }
    try:
        response = requests.post(LOGIN_API, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if data.get("Result") == 10000:
            session = requests.Session()
            session.cookies.update(response.cookies)
            logger.info("登录成功")
            return session
        logger.error(f"登录失败: {data.get('ErrMsg')}")
        return None
    except Exception as e:
        logger.error(f"登录错误: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_china_ip_list():
    """从指定 URL 获取中国 IP 列表。

    Returns:
        list: 有效 IP 范围列表，失败或空时返回 None。
    """
    logger.info(f"获取中国 IP 列表: {CHINA_IP_URL}")
    try:
        response = requests.get(CHINA_IP_URL, timeout=TIMEOUT)
        response.raise_for_status()
        ip_list = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ipaddress.ip_network(line)  # 验证 CIDR 格式
                ip_list.append(line)
            except ValueError:
                logger.warning(f"无效 IP 范围已跳过: {line}")
        if not ip_list:
            logger.error("获取到的 IP 列表为空")
            return None
        logger.info(f"获取到 {len(ip_list)} 条 IP 记录")
        return ip_list
    except Exception as e:
        logger.error(f"获取 IP 列表失败: {e}")
        return None

def load_last_ip_list():
    """加载上次保存的 IP 列表。

    Returns:
        list: 保存的 IP 列表，文件不存在或失败时返回空列表。
    """
    last_ip_file_path = os.path.join(os.path.dirname(__file__), LAST_IP_FILE)
    if os.path.exists(last_ip_file_path):
        try:
            with open(last_ip_file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取上次 IP 列表失败: {e}")
    return []

def save_last_ip_list(ip_list):
    """保存当前 IP 列表到本地文件。

    Args:
        ip_list (list): 要保存的 IP 列表。
    """
    last_ip_file_path = os.path.join(os.path.dirname(__file__), LAST_IP_FILE)
    try:
        with open(last_ip_file_path, 'w') as f:
            json.dump(ip_list, f)
        logger.info("成功保存当前的 IP 列表")
    except Exception as e:
        logger.error(f"保存 IP 列表失败: {e}")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def get_isp_id(session, isp_name):
    """查询指定运营商的 ID。

    Args:
        session (requests.Session): 已认证的会话对象。
        isp_name (str): 运营商名称。

    Returns:
        int: 运营商 ID，未找到或失败时返回 None。
    """
    logger.info(f"查询 {isp_name} 运营商 ID")
    payload = {
        "func_name": "custom_isp",
        "action": "show",
        "param": {"TYPE": "data,total", "limit": "0,1000"}
    }
    try:
        response = session.post(CUSTOM_ISP_API, json=payload, headers={"Content-Type": "application/json"}, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if data.get("Result") != 30000:
            logger.error(f"获取运营商信息失败: {data.get('ErrMsg')}")
            return None
        for isp in data.get("Data", {}).get("data", []):
            if isinstance(isp, dict) and isp.get("name") == isp_name:
                logger.info(f"找到 {isp_name} 运营商 ID: {isp.get('id')}")
                return isp.get("id")
        logger.info(f"未找到 {isp_name} 运营商")
        return None
    except Exception as e:
        logger.error(f"获取 {isp_name} 运营商 ID 失败: {e}")
        return None

def update_custom_isp(session, ip_list, isp_name, chunk_size=CHUNK_SIZE):
    """更新或创建指定运营商的 IP 列表。

    Args:
        session (requests.Session): 已认证的会话对象。
        ip_list (list): IP 范围列表。
        isp_name (str): 运营商名称。
        chunk_size (int): 备用分块大小（当前未使用）。
    """
    logger.info(f"开始更新 {isp_name} 运营商，总计 {len(ip_list)} 条 IP 范围")
    isp_id = get_isp_id(session, isp_name)
    
    # 合并所有 IP 范围为单一字符串
    ipgroup_str = ",".join(ip_list)
    payload = {
        "func_name": "custom_isp",
        "action": "edit" if isp_id else "add",
        "param": {
            "id": isp_id,
            "name": isp_name,
            "ipgroup": ipgroup_str
        } if isp_id else {
            "name": isp_name,
            "ipgroup": ipgroup_str
        }
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = session.post(CUSTOM_ISP_API, json=payload, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        result = response.json()
        if result.get("Result") in [10000, 30000]:
            logger.info(f"{isp_name} 运营商更新成功")
        else:
            logger.error(f"更新失败: {result.get('ErrMsg')} (Result: {result.get('Result')})")
    except Exception as e:
        logger.error(f"更新 {isp_name} 运营商出错: {e}")

def update_job():
    """执行 IP 列表更新任务。"""
    logger.info("开始执行更新任务")
    session = login()
    if session:
        try:
            china_ip_list = fetch_china_ip_list()
            if china_ip_list:
                last_ip_list = load_last_ip_list()
                isp_id = get_isp_id(session, ISP_NAME)
                if china_ip_list != last_ip_list or isp_id is None:
                    update_custom_isp(session, china_ip_list, ISP_NAME)
                    save_last_ip_list(china_ip_list)
                else:
                    logger.info(f"IP 列表没有变化，且 {ISP_NAME} 运营商已存在，无需更新")
            else:
                logger.error("未获取到 IP 列表，不更新路由器设置")
        except Exception as e:
            logger.error(f"更新任务失败: {e}")
        finally:
            session.close()
    else:
        logger.error("登录失败，无法执行更新任务")
    logger.info("更新任务结束")

def schedule_jobs():
    """根据配置文件设置调度任务。"""
    logger.info(f"设置调度任务: {SCHEDULE_TYPE} 周期，时间 {SCHEDULE_TIME}")
    try:
        if SCHEDULE_TYPE == "d":
            schedule.every().day.at(SCHEDULE_TIME).do(update_job)
        elif SCHEDULE_TYPE == "w":
            getattr(schedule.every(), SCHEDULE_DAY).at(SCHEDULE_TIME).do(update_job)
        elif SCHEDULE_TYPE == "m":
            schedule.every(1).months.at(f"{SCHEDULE_DATE:02d} {SCHEDULE_TIME}").do(update_job)
        else:
            logger.error(f"不支持的调度类型: {SCHEDULE_TYPE}")
            exit(1)
    except schedule.ScheduleValueError as e:
        logger.error(f"调度配置错误: {e}")
        exit(1)

def run_scheduler():
    """运行调度器，持续检查待执行任务。"""
    schedule_jobs()
    while RUNNING:
        schedule.run_pending()
        time.sleep(60)  # 每分钟检查一次

def signal_handler(sig, frame):
    """处理终止信号，优雅退出。"""
    global RUNNING
    logger.info("收到终止信号，正在停止服务...")
    RUNNING = False

if __name__ == "__main__":
    logger.info("iKuai IP 更新服务启动")
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 在单独线程中运行调度器
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # 保持主线程运行，直到收到终止信号
    try:
        while RUNNING:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到键盘中断，停止服务")
        RUNNING = False
    
    scheduler_thread.join()
    logger.info("iKuai IP 更新服务停止")
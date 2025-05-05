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

# 全局标志和配置
RUNNING = True
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
CONFIG_CHECK_INTERVAL = 60
LAST_CONFIG_MTIME = 0
CURRENT_CONFIG = None
CURRENT_SCHEDULE = None

def load_config():
    global LAST_CONFIG_MTIME, CURRENT_CONFIG
    try:
        stat = os.stat(CONFIG_PATH)
        mtime = stat.st_mtime
        if mtime != LAST_CONFIG_MTIME:
            with open(CONFIG_PATH, "r") as f:
                config = json.load(f)
            required_configs = [
                "ikuai_url", "username", "password", "china_ip_url", "last_ip_file",
                "timeout", "chunk_size", "isp_name", "schedule_type", "schedule_time",
                "schedule_day", "schedule_date"
            ]
            for key in required_configs:
                if key not in config:
                    logger.error(f"缺少必需配置项: {key}")
                    return None
            if config["schedule_type"].lower() not in ["d", "w", "m"]:
                logger.error(f"无效 schedule_type: {config['schedule_type']}")
                return None
            if not (1 <= config["schedule_date"] <= 28):
                logger.error(f"无效 schedule_date: {config['schedule_date']}")
                return None
            if config["schedule_day"].lower() not in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                logger.error(f"无效 schedule_day: {config['schedule_day']}")
                return None
            try:
                time.strptime(config["schedule_time"], "%H:%M")
            except ValueError:
                logger.error(f"无效 schedule_time: {config['schedule_time']}")
                return None
            if not isinstance(config["timeout"], (int, float)) or config["timeout"] <= 0:
                logger.error(f"无效 timeout: {config['timeout']}")
                return None
            if not isinstance(config["chunk_size"], int) or config["chunk_size"] <= 0:
                logger.error(f"无效 chunk_size: {config['chunk_size']}")
                return None
            LAST_CONFIG_MTIME = mtime
            CURRENT_CONFIG = config
            logger.info(f"加载配置文件，修改时间: {time.ctime(mtime)}")
            return config
        return CURRENT_CONFIG
    except FileNotFoundError:
        logger.error(f"配置文件 {CONFIG_PATH} 不存在")
        return None
    except json.JSONDecodeError:
        logger.error(f"配置文件 {CONFIG_PATH} 格式错误")
        return None
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return None

def md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def login(config):
    logger.info(f"登录: {config['ikuai_url']}/Action/login")
    payload = {
        "username": config["username"],
        "passwd": md5_hash(config["password"]),
        "pass": str(int(time.time() * 1000)),
        "remember_password": ""
    }
    response = requests.post(f"{config['ikuai_url']}/Action/login", json=payload, timeout=config["timeout"])
    response.raise_for_status()
    data = response.json()
    if data.get("Result") == 10000:
        session = requests.Session()
        session.cookies.update(response.cookies)
        logger.info("登录成功")
        return session
    logger.error(f"登录失败: {data.get('ErrMsg')}")
    return None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_china_ip_list(config):
    logger.info(f"获取 IP 列表: {config['china_ip_url']}")
    response = requests.get(config["china_ip_url"], timeout=config["timeout"])
    response.raise_for_status()
    ip_list = []
    for line in response.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ipaddress.ip_network(line)
            ip_list.append(line)
        except ValueError:
            logger.warning(f"无效 IP: {line}")
    if not ip_list:
        logger.error("IP 列表为空")
        return None
    logger.info(f"获取 {len(ip_list)} 条 IP")
    return ip_list

def load_last_ip_list(config):
    path = os.path.join(os.path.dirname(__file__), config["last_ip_file"])
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        logger.warning(f"IP 列表文件 {path} 不存在或为空")
        return []
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"读取 IP 列表失败: {e}")
        return []

def save_last_ip_list(config, ip_list):
    path = os.path.join(os.path.dirname(__file__), config["last_ip_file"])
    try:
        with open(path, 'w') as f:
            json.dump(ip_list, f)
        logger.info("保存 IP 列表成功")
    except Exception as e:
        logger.error(f"保存 IP 列表失败: {e}")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def get_isp_info(session, isp_name, config):
    logger.info(f"查询 {isp_name} 运营商信息")
    payload = {
        "func_name": "custom_isp",
        "action": "show",
        "param": {"TYPE": "data,total", "limit": "0,1000"}
    }
    response = session.post(f"{config['ikuai_url']}/Action/call", json=payload, headers={"Content-Type": "application/json"}, timeout=config["timeout"])
    response.raise_for_status()
    data = response.json()
    if data.get("Result") != 30000:
        logger.error(f"获取运营商失败: {data.get('ErrMsg')}")
        return None, 0
    for isp in data.get("Data", {}).get("data", []):
        if isinstance(isp, dict) and isp.get("name") == isp_name:
            ipgroup = isp.get("ipgroup", "")
            ip_count = len(ipgroup.split(",")) if ipgroup else 0
            logger.info(f"找到 {isp_name} ID: {isp.get('id')}，IP 条数: {ip_count}")
            return isp.get("id"), ip_count
    logger.info(f"未找到 {isp_name}")
    return None, 0

def update_custom_isp(session, ip_list, isp_name, config):
    logger.info(f"更新 {isp_name}，{len(ip_list)} 条 IP")
    isp_id, isp_ip_count = get_isp_info(session, isp_name, config)
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
    response = session.post(f"{config['ikuai_url']}/Action/call", json=payload, headers={"Content-Type": "application/json"}, timeout=config["timeout"])
    response.raise_for_status()
    result = response.json()
    if result.get("Result") not in [10000, 30000]:
        logger.error(f"更新失败: {result.get('ErrMsg')} (Result: {result.get('Result')})")
        return False
    expected_count = len(ip_list)
    if isp_id and isp_ip_count == expected_count:
        logger.info(f"验证成功: {isp_name} IP 条数 {isp_ip_count} 匹配预期 {expected_count}")
        return True
    logger.error(f"验证失败: {isp_name} IP 条数 {isp_ip_count} 不匹配预期 {expected_count}")
    return False

def update_job(config):
    logger.info("开始更新任务")
    if not config:
        logger.error("无有效配置，跳过任务")
        return
    china_ip_list = fetch_china_ip_list(config)
    if not china_ip_list:
        logger.error("无 IP 列表，跳过更新")
        return
    last_ip_list = load_last_ip_list(config)
    if sorted(china_ip_list) == sorted(last_ip_list):
        logger.info("远程 IP 列表无变化，跳过更新")
        return
    logger.info(f"远程 IP 列表变更（新: {len(china_ip_list)} 条，旧: {len(last_ip_list)} 条），开始更新")
    session = login(config)
    if session:
        try:
            if update_custom_isp(session, china_ip_list, config["isp_name"], config):
                save_last_ip_list(config, china_ip_list)
            else:
                logger.error("更新未成功，不保存新 IP 列表")
        except Exception as e:
            logger.error(f"任务失败: {e}")
        finally:
            session.close()
    else:
        logger.error("登录失败，跳过任务")
    logger.info("更新任务结束")

def schedule_jobs(config):
    logger.info(f"设置调度: {config['schedule_type']} 周期，时间 {config['schedule_time']}")
    try:
        schedule.clear()
        if config["schedule_type"] == "d":
            schedule.every().day.at(config["schedule_time"]).do(update_job, config)
        elif config["schedule_type"] == "w":
            getattr(schedule.every(), config["schedule_day"].lower()).at(config["schedule_time"]).do(update_job, config)
        elif config["schedule_type"] == "m":
            schedule.every(1).months.at(f"{config['schedule_date']:02d} {config['schedule_time']}").do(update_job, config)
        else:
            logger.error(f"无效调度类型: {config['schedule_type']}")
            return False
        logger.info(f"调度任务已设置: {config['schedule_type']} {config['schedule_time']}")
        return True
    except schedule.ScheduleValueError as e:
        logger.error(f"调度错误: {e}")
        return False

def run_scheduler():
    config = load_config()
    if not config or not schedule_jobs(config):
        logger.error("初始配置或调度失败，退出")
        return
    global CURRENT_SCHEDULE, CURRENT_CONFIG
    CURRENT_SCHEDULE = {
        "schedule_type": config["schedule_type"],
        "schedule_time": config["schedule_time"],
        "schedule_day": config["schedule_day"],
        "schedule_date": config["schedule_date"]
    }
    CURRENT_CONFIG = config
    last_check = 0
    while RUNNING:
        if time.time() - last_check >= CONFIG_CHECK_INTERVAL:
            new_config = load_config()
            if new_config:
                new_schedule = {
                    "schedule_type": new_config["schedule_type"],
                    "schedule_time": new_config["schedule_time"],
                    "schedule_day": new_config["schedule_day"],
                    "schedule_date": new_config["schedule_date"]
                }
                if not CURRENT_SCHEDULE or new_schedule != CURRENT_SCHEDULE:
                    logger.info("调度配置变更，重新设置")
                    if schedule_jobs(new_config):
                        CURRENT_SCHEDULE = new_schedule
                        CURRENT_CONFIG = new_config
                    else:
                        logger.error("重新设置调度失败，使用旧配置")
            last_check = time.time()
        schedule.run_pending()
        time.sleep(5)

def signal_handler(sig, frame):
    global RUNNING
    logger.info("收到终止信号，停止服务...")
    RUNNING = False

if __name__ == "__main__":
    logger.info("iKuai IP 更新服务启动")
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    try:
        while RUNNING:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("键盘中断，停止服务")
        RUNNING = False
    scheduler_thread.join()
    logger.info("iKuai IP 更新服务停止")
#!/usr/bin/env python3
import requests
import hashlib
import time
import json
import os

# 配置
IKUAI_URL = "http://10.0.0.1  # ikuai访问地址
USERNAME = "admin"  # ikuai用户名
PASSWORD = "admin"  #ikuai 密码
CHINA_IP_URL = "https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt"
LAST_IP_FILE = "last_china_ip.json"  # 获取的 IP 列表文件存档

# API 端点
LOGIN_API = f"{IKUAI_URL}/Action/login"
CUSTOM_ISP_API = f"{IKUAI_URL}/Action/call"

def md5_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def login():
    print(f"[INFO] 准备登录: {LOGIN_API}")
    payload = {
        "username": USERNAME,
        "passwd": md5_hash(PASSWORD),
        "pass": str(int(time.time() * 1000)),  # 当前时间戳（毫秒）
        "remember_password": ""
    }
    try:
        response = requests.post(LOGIN_API, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("Result") == 10000:
            session = requests.Session()
            session.cookies.update(response.cookies)
            print("[INFO] 登录成功")
            return session
        else:
            print(f"[ERROR] 登录失败: {data.get('ErrMsg')}")
            return None
    except Exception as e:
        print(f"[ERROR] 登录错误: {e}")
        return None

def fetch_china_ip_list():
    print(f"[INFO] 获取中国 IP 列表: {CHINA_IP_URL}")
    try:
        response = requests.get(CHINA_IP_URL, timeout=10)
        response.raise_for_status()
        ip_list = [line.strip() for line in response.text.splitlines() if line.strip()]
        if not ip_list:
            print("[ERROR] 获取到的 IP 列表为空")
            return None
        print(f"[INFO] 获取到 {len(ip_list)} 条 IP 记录")
        return ip_list
    except Exception as e:
        print(f"[ERROR] 获取 IP 列表失败: {e}")
        return None

def load_last_ip_list():
    if os.path.exists(LAST_IP_FILE):
        try:
            with open(LAST_IP_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取上次 IP 列表失败: {e}")
    return []

def save_last_ip_list(ip_list):
    try:
        with open(LAST_IP_FILE, 'w') as f:
            json.dump(ip_list, f)
        print("[INFO] 成功保存当前的 IP 列表")
    except Exception as e:
        print(f"[ERROR] 保存 IP 列表失败: {e}")

def get_cn_isp_id(session):
    print("[INFO] 查询 CN 运营商 ID")
    payload = {
        "func_name": "custom_isp",
        "action": "show",
        "param": {"TYPE": "data,total", "limit": "0,1000"},
    }
    try:
        response = session.post(CUSTOM_ISP_API, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
        if data.get("Result") != 30000:
            print(f"[ERROR] 获取运营商信息失败: {data.get('ErrMsg')}")
            return None
        for isp in data.get("Data", {}).get("data", []):
            if isinstance(isp, dict) and isp.get("name") == "CN":
                print(f"[INFO] 找到 CN 运营商 ID: {isp.get('id')}")
                return isp.get("id")
        print("[INFO] 未找到 CN 运营商")
        return None
    except Exception as e:
        print(f"[ERROR] 获取运营商 ID 失败: {e}")
        return None

def update_custom_isp(session, ip_list):
    print("[INFO] 开始更新 CN 运营商")
    cn_isp_id = get_cn_isp_id(session)
    ipgroup_str = ",".join(ip_list)
    if cn_isp_id:
        payload = {
            "func_name": "custom_isp",
            "action": "edit",
            "param": {
                "id": cn_isp_id,
                "name": "CN",
                "ipgroup": ipgroup_str
            }
        }
        print(f"[INFO] 更新现有 CN 运营商，ID: {cn_isp_id}")
    else:
        payload = {
            "func_name": "custom_isp",
            "action": "add",
            "param": {
                "name": "CN",
                "ipgroup": ipgroup_str
            }
        }
        print("[INFO] 创建新的 CN 运营商")
    headers = {"Content-Type": "application/json"}
    try:
        response = session.post(CUSTOM_ISP_API, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        if result.get("Result") in [10000, 30000]:
            print("[INFO] CN 运营商更新成功")
        else:
            print(f"[ERROR] 更新失败: {result.get('ErrMsg')} (Result: {result.get('Result')})")
    except Exception as e:
        print(f"[ERROR] 更新 CN 运营商出错: {e}")

if __name__ == "__main__":
    print("[INFO] 脚本启动")
    session = login()
    if session:
        china_ip_list = fetch_china_ip_list()
        if china_ip_list:
            last_ip_list = load_last_ip_list()
            cn_isp_id = get_cn_isp_id(session)  # 提前检查 "CN" 是否存在
            # 如果 IP 列表有变化 或 "CN" 运营商不存在，则更新
            if china_ip_list != last_ip_list or cn_isp_id is None:
                update_custom_isp(session, china_ip_list)
                save_last_ip_list(china_ip_list)
            else:
                print("[INFO] IP 列表没有变化，且 CN 运营商已存在，无需更新")
        else:
            print("[ERROR] 未获取到 IP 列表，不更新路由器设置")
        session.close()
    else:
        print("[ERROR] 登录失败，无法继续")
    print("[INFO] 脚本结束")
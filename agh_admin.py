#!/usr/bin/env python3
import bcrypt
import yaml
import os
import subprocess

def generate_bcrypt_password(password: str) -> str:
    """生成 bcrypt 加密的密码。"""
    salt = bcrypt.gensalt(rounds=10)
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def update_adguard_credentials(yaml_file: str, new_username: str, new_password: str):
    """更新 AdGuardHome.yaml 文件中的用户名和密码。"""
    with open(yaml_file, 'r') as file:
        config = yaml.safe_load(file)

    # 更新用户名和密码
    config['users'][0]['name'] = new_username
    config['users'][0]['password'] = generate_bcrypt_password(new_password)

    with open(yaml_file, 'w') as file:
        yaml.dump(config, file)

    print("管理员账号和密码已更新。")

def restart_adguard_service():
    """重启 AdGuardHome 服务。"""
    try:
        subprocess.run(['systemctl', 'restart', 'AdGuardHome'], check=True)
        print("AdGuardHome 服务已重启。")
    except subprocess.CalledProcessError as e:
        print(f"重启 AdGuardHome 服务失败: {e}")

if __name__ == "__main__":
    yaml_file_path = '/opt/AdGuardHome/AdGuardHome.yaml'
    
    if not os.path.exists(yaml_file_path):
        print(f"错误: {yaml_file_path} 文件不存在。")
        exit(1)

    new_username = input("请输入新的管理员用户名: ")
    new_password = input("请输入新的管理员密码: ")

    update_adguard_credentials(yaml_file_path, new_username, new_password)
    restart_adguard_service()
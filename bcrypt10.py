#!/usr/bin/env python3
import bcrypt

def generate_bcrypt_password(password: str) -> str:
    # 生成盐，设置轮数为10
    salt = bcrypt.gensalt(rounds=10)
    # 哈希密码
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

# 示例用法
if __name__ == "__main__":
    plain_password = input("请输入要加密的密码: ")
    hashed = generate_bcrypt_password(plain_password)
    print(f"加密后的密码: {hashed}")
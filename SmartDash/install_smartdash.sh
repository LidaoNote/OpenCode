#!/bin/bash

# 检查是否以 root 或 sudo 运行
if [ "$(id -u)" -ne 0 ]; then
    echo "错误：请以 root 用户或使用 sudo 运行此脚本！"
    exit 1
fi

# 检测系统类型
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        VERSION_ID=$VERSION_ID
    else
        echo "错误：无法检测操作系统，请确保 /etc/os-release 存在！"
        exit 1
    fi
}

# 安装依赖（根据系统类型）
install_dependencies() {
    echo "正在检测和安装依赖..."

    # 检测 Python 3
    if ! command -v python3 &> /dev/null; then
        echo "未找到 Python 3，正在安装..."
        case $OS in
            ubuntu|debian)
                apt update && apt install -y python3
                ;;
            centos)
                if [[ $VERSION_ID == "7" ]]; then
                    yum install -y python3
                else
                    dnf install -y python3
                fi
                ;;
            *)
                echo "错误：不支持的操作系统 $OS，请手动安装 python3！"
                exit 1
                ;;
        esac
        if [ $? -ne 0 ]; then
            echo "错误：安装 python3 失败！"
            exit 1
        fi
    else
        echo "Python 3 已安装"
    fi

    # 检测 pip3
    if ! command -v pip3 &> /dev/null; then
        echo "未找到 pip3，正在安装..."
        case $OS in
            ubuntu|debian)
                apt install -y python3-pip
                ;;
            centos)
                if [[ $VERSION_ID == "7" ]]; then
                    yum install -y python3-pip
                else
                    dnf install -y python3-pip
                fi
                ;;
            *)
                echo "错误：不支持的操作系统 $OS，请手动安装 python3-pip！"
                exit 1
                ;;
        esac
        if [ $? -ne 0 ]; then
            echo "错误：安装 python3-pip 失败！"
            exit 1
        fi
    else
        echo "pip3 已安装"
    fi

    # 检测 Python 包
    required_packages=("flask" "flask-bootstrap" "dnspython" "requests")
    for pkg in "${required_packages[@]}"; do
        if ! pip3 list | grep -q "^$pkg "; then
            echo "未找到 $pkg，正在安装..."
            pip3 install $pkg
            if [ $? -ne 0 ]; then
                echo "错误：安装 $pkg 失败！"
                exit 1
            fi
        else
            echo "$pkg 已安装"
        fi
    done
}

# 提示用户输入 app.py 的路径，默认为 /root/SmartDash/
read -p "请输入 SmartDash 的安装路径（默认 /root/SmartDash/，直接按 Enter 使用默认值）： " install_path

# 如果未输入路径，使用默认值
if [ -z "$install_path" ]; then
    install_path="/root/SmartDash/"
fi

# 确保路径以 / 结尾
install_path="${install_path%/}/"

# 验证路径是否存在且包含 app.py
app_path="${install_path}app.py"
if [ ! -d "$install_path" ]; then
    echo "错误：路径 $install_path 不存在！"
    exit 1
fi
if [ ! -f "$app_path" ]; then
    echo "错误：$app_path 文件不存在！"
    exit 1
fi

# 检测操作系统
detect_os

# 安装依赖
install_dependencies

# 设置 app.py 的可执行权限
echo "设置 $app_path 的可执行权限..."
chmod +x "$app_path"

# 创建并编辑服务文件
echo "创建并配置 /etc/systemd/system/smartdash.service ..."
cat <<EOF | tee /etc/systemd/system/smartdash.service
[Unit]
Description=SmartDash
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $app_path
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd 配置
echo "重新加载 systemd 配置..."
systemctl daemon-reload

# 启用并启动服务
echo "启用并启动 smartdash 服务..."
systemctl enable smartdash
systemctl start smartdash

# 显示服务状态
echo "显示 smartdash 服务状态..."
systemctl status smartdash
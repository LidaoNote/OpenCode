#!/bin/sh

# 确保脚本以 root 用户身份运行
if [ "$EUID" -ne 0 ]; then
    echo "请以 root 用户身份运行此脚本"
    exit 1
fi

# 菜单选择
show_menu() {
    echo "请选择操作选项:"
    echo "1) 安装更新和依赖"
    echo "2) 安装 SmartDNS"
    echo "3) 安装 SmartDNS 和 AdGuardHome"
    echo "4) 卸载 SmartDNS"
    echo "5) 卸载 AdGuardHome"
    read -p "输入选项 (1/2/3/4/5): " choice
}

# 安装所需软件
install_dependencies() {
    echo "正在安装更新和所需软件..."
    apt update
    apt install -y wget curl net-tools sed
}

# 安装 SmartDNS
install_smartdns() {
    echo "正在安装 SmartDNS..."
    wget https://github.com/pymumu/smartdns/releases/download/Release46/smartdns.1.2024.06.12-2222.x86_64-linux-all.tar.gz
    tar zxf smartdns.1.2024.06.12-2222.x86_64-linux-all.tar.gz
    cd smartdns
    chmod +x ./install
    ./install -i
    cd ..
    rm -rf smartdns smartdns.1.2024.06.12-2222.x86_64-linux-all.tar.gz
}

# 安装 AdGuardHome
install_adguardhome() {
    echo "正在安装 AdGuardHome..."
    curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s --
}

# 卸载 SmartDNS
uninstall_smartdns() {
    echo "正在卸载 SmartDNS..."
    wget https://github.com/pymumu/smartdns/releases/download/Release46/smartdns.1.2024.06.12-2222.x86_64-linux-all.tar.gz
    tar zxf smartdns.1.2024.06.12-2222.x86_64-linux-all.tar.gz
    cd smartdns
    chmod +x ./install
    ./install -u
    cd ..
    rm -rf smartdns smartdns.1.2024.06.12-2222.x86_64-linux-all.tar.gz
    echo "SmartDNS 卸载完成"
}

# 卸载 AdGuardHome
uninstall_adguardhome() {
    echo "正在卸载 AdGuardHome..."
    curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -u
    echo "AdGuardHome 卸载完成"
}

# 下载并配置 SmartDNS
configure_smartdns() {
    mkdir -p /etc/smartdns
    wget -O /etc/smartdns/smartdns.conf https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/SmartDNS/smartdns_s.conf

    echo "设置监听端口..."
    if [ "$1" = "adguard" ]; then
        # 设置端口为 5353
        sed -i 's/bind \[::\]:[0-9]\+/bind \[::\]:5353/g' /etc/smartdns/smartdns.conf
        sed -i 's/bind-tcp \[::\]:[0-9]\+/bind-tcp \[::\]:5353/g' /etc/smartdns/smartdns.conf
    else
        # 设置端口为 53
        sed -i 's/bind \[::\]:[0-9]\+/bind \[::\]:53/g' /etc/smartdns/smartdns.conf
        sed -i 's/bind-tcp \[::\]:[0-9]\+/bind-tcp \[::\]:53/g' /etc/smartdns/smartdns.conf
    fi

    echo "请输入您的运营商 DNS 服务器地址 (按 Enter 使用默认值):"
    read -p "DNS1: " dns1
    read -p "DNS2: " dns2

    # 如果用户未输入，使用默认值
    if [ -z "$dns1" ]; then
        dns1="223.6.6.6"
    fi
    if [ -z "$dns2" ]; then
        dns2="119.29.29.29"
    fi

    # 修改 DNS 服务器组配置
    sed -i "s|server  运营商DNS1 -group china -exclude-default-group|server $dns1 -group china -exclude-default-group|g" /etc/smartdns/smartdns.conf
    sed -i "s|server  运营商DNS2 -group china -exclude-default-group|server $dns2 -group china -exclude-default-group|g" /etc/smartdns/smartdns.conf

    wget -O /etc/smartdns/all_domains.conf https://github.com/LidaoNote/OpenCode/raw/refs/heads/main/SmartDNS/all_domains.conf

    echo "重启 SmartDNS 服务..."
    systemctl restart smartdns
}

# 下载 AdGuardHome 配置文件并重启服务
download_adguard_config() {
    mkdir -p /opt/AdGuardHome
    echo "正在下载 AdGuardHome 配置文件..."
    wget -O /opt/AdGuardHome/AdGuardHome.yaml https://github.com/LidaoNote/OpenCode/raw/refs/heads/main/AdGuardHome/AdGuardHome.yaml

    # 检查下载是否成功
    if [ $? -eq 0 ]; then
        echo "配置文件下载成功，保存到 /opt/AdGuardHome/AdGuardHome.yaml"
    else
        echo "配置文件下载失败"
        exit 1
    fi

    # 重启 AdGuardHome 服务
    echo "重启 AdGuardHome 服务..."
    systemctl restart AdGuardHome

    # 检查服务状态
    if systemctl is-active --quiet AdGuardHome; then
        echo "AdGuardHome 服务已成功重启"
    else
        echo "AdGuardHome 服务重启失败"
    fi
}

# 执行操作
show_menu

case $choice in
    1)
        install_dependencies
        ;;
    2)
        install_dependencies
        install_smartdns
        configure_smartdns ""
        ;;
    3)
        install_dependencies
        install_smartdns
        install_adguardhome
        configure_smartdns "adguard"
        download_adguard_config
        ;;
    4)
        uninstall_smartdns
        ;;
    5)
        uninstall_adguardhome
        ;;
    *)
        echo "无效选项"
        exit 1
        ;;
esac
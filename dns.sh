#!/bin/sh

# 确保脚本以 root 用户身份运行
if [ "$EUID" -ne 0 ]; then
    echo "请以 root 用户身份运行此脚本"
    exit 1
fi

# 检测系统架构
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)
        SMARTDNS_ARCH="x86_64"
        INSTALL_METHOD="tar"
        ;;
    aarch64)
        SMARTDNS_ARCH="aarch64"
        INSTALL_METHOD="binary"  # Using smartdns-aarch64 binary
        ;;
    arm*)
        SMARTDNS_ARCH="arm"
        INSTALL_METHOD="tar"
        ;;
    *)
        echo "不支持的架构: $ARCH"
        exit 1
        ;;
esac

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
    apt install -y wget curl net-tools sed jq
    if [ $? -ne 0 ]; then
        echo "依赖安装失败，请检查网络或软件源"
        exit 1
    fi
}

# 检查端口冲突
check_port_conflict() {
    if netstat -tulnp | grep -q ":53"; then
        echo "端口 53 已被占用，禁用 systemd-resolved..."
        systemctl disable --now systemd-resolved
        rm -f /etc/resolv.conf
        echo "nameserver 8.8.8.8" > /etc/resolv.conf
    fi
}

# 获取最新 SmartDNS 版本
get_latest_smartdns_url() {
    echo "正在获取最新 SmartDNS 版本..."
    LATEST_RELEASE=$(curl -s https://api.github.com/repos/pymumu/smartdns/releases/latest)
    if [ "$INSTALL_METHOD" = "binary" ]; then
        DOWNLOAD_URL=$(echo "$LATEST_RELEASE" | jq -r ".assets[] | select(.name == \"smartdns-${SMARTDNS_ARCH}\") | .browser_download_url")
    else
        DOWNLOAD_URL=$(echo "$LATEST_RELEASE" | jq -r ".assets[] | select(.name | contains(\"${SMARTDNS_ARCH}-linux-all.tar.gz\")) | .browser_download_url")
    fi
    if [ -z "$DOWNLOAD_URL" ]; then
        echo "无法获取 SmartDNS 下载链接"
        exit 1
    fi
    echo "最新 SmartDNS 下载链接: $DOWNLOAD_URL"
}

# 安装 SmartDNS
install_smartdns() {
    echo "正在安装 SmartDNS..."
    install_dependencies
    check_port_conflict
    get_latest_smartdns_url
    if [ "$INSTALL_METHOD" = "binary" ]; then
        wget "$DOWNLOAD_URL" -O smartdns
        if [ $? -ne 0 ]; then
            echo "下载 SmartDNS 二进制文件失败"
            exit 1
        fi
        mv smartdns /usr/sbin/smartdns
        chmod +x /usr/sbin/smartdns
        chown root:root /usr/sbin/smartdns
    else
        wget "$DOWNLOAD_URL" -O smartdns.tar.gz
        if [ $? -ne 0 ]; then
            echo "下载 SmartDNS .tar.gz 包失败"
            exit 1
        fi
        tar zxf smartdns.tar.gz
        cd smartdns
        chmod +x ./install
        ./install -i
        if [ $? -ne 0 ]; then
            echo "安装 SmartDNS 失败"
            cd ..
            rm -rf smartdns smartdns.tar.gz
            exit 1
        fi
        cd ..
        rm -rf smartdns smartdns.tar.gz
    fi
    # 验证二进制
    if command -v smartdns >/dev/null 2>&1; then
        echo "SmartDNS 安装成功，版本: $(smartdns --version)"
    else
        echo "SmartDNS 安装失败，未找到 smartdns 命令"
        exit 1
    fi
    # 创建 systemd 服务文件
    cat > /lib/systemd/system/smartdns.service << EOF
[Unit]
Description=SmartDNS server
After=network.target

[Service]
Type=forking
ExecStart=/usr/sbin/smartdns -f -c /etc/smartdns/smartdns.conf
ExecReload=/bin/kill -HUP \$MAINPID
ExecStop=/bin/kill -TERM \$MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
    # 确保配置目录存在
    mkdir -p /etc/smartdns
    # 重新加载并启动服务
    systemctl daemon-reload
    systemctl enable smartdns
    systemctl restart smartdns
    if systemctl is-active --quiet smartdns; then
        echo "SmartDNS 服务已成功启动"
    else
        echo "SmartDNS 服务启动失败，请检查 'systemctl status smartdns.service'"
        exit 1
    fi
}

# 安装 AdGuardHome
install_adguardhome() {
    echo "正在安装 AdGuardHome..."
    curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s --
    if [ $? -ne 0 ]; then
        echo "AdGuardHome 安装失败"
        exit 1
    fi
}

# 卸载 SmartDNS
uninstall_smartdns() {
    echo "正在卸载 SmartDNS..."
    systemctl stop smartdns
    systemctl disable smartdns
    rm -f /lib/systemd/system/smartdns.service
    rm -f /usr/sbin/smartdns
    rm -rf /etc/smartdns
    systemctl daemon-reload
    echo "SmartDNS 卸载完成"
}

# 卸载 AdGuardHome
uninstall_adguardhome() {
    echo "正在卸载 AdGuardHome..."
    curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -u
    if [ $? -ne 0 ]; then
        echo "AdGuardHome 卸载失败"
        exit 1
    fi
    echo "AdGuardHome 卸载完成"
}

# 下载并配置 SmartDNS
configure_smartdns() {
    mkdir -p /etc/smartdns
    wget -O /etc/smartdns/smartdns.conf https://raw.githubusercontent.com/LidaoNote/OpenCode/refs/heads/main/SmartDNS/smartdns_s.conf
    if [ $? -ne 0 ]; then
        echo "下载 SmartDNS 配置文件失败"
        exit 1
    fi

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
    if [ $? -ne 0 ]; then
        echo "下载 SmartDNS 域名列表失败"
        exit 1
    fi

    echo "重启 SmartDNS 服务..."
    systemctl restart smartdns
    if [ $? -ne 0 ]; then
        echo "SmartDNS 服务重启失败，请检查服务状态"
        exit 1
    fi
}

# 下载 AdGuardHome 配置文件并重启服务
download_adguard_config() {
    mkdir -p /opt/AdGuardHome
    echo "正在下载 AdGuardHome 配置文件..."
    wget -O /opt/AdGuardHome/AdGuardHome.yaml https://github.com/LidaoNote/OpenCode/raw/refs/heads/main/AdGuardHome/AdGuardHome.yaml
    if [ $? -ne 0 ]; then
        echo "AdGuardHome 配置文件下载失败"
        exit 1
    fi

    echo "配置文件下载成功，保存到 /opt/AdGuardHome/AdGuardHome.yaml"

    # 重启 AdGuardHome 服务
    echo "重启 AdGuardHome 服务..."
    systemctl restart AdGuardHome
    if [ $? -ne 0 ]; then
        echo "AdGuardHome 服务重启失败"
        exit 1
    fi

    # 检查服务状态
    if systemctl is-active --quiet AdGuardHome; then
        echo "AdGuardHome 服务已成功重启"
    else
        echo "AdGuardHome 服务未运行"
        exit 1
    fi
}

# 执行操作
show_menu

case $choice in
    1)
        install_dependencies
        ;;
    2)
        install_smartdns
        configure_smartdns ""
        ;;
    3)
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
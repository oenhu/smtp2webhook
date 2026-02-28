## 🤖 Assistant

这是一个基于 Python `aiosmtpd` 库开发的**轻量级 SMTP 服务器**。它的主要功能是**监听 25 端口接收邮件，并将邮件内容通过 Markdown 格式转发至钉钉群机器人**。

以下是为您整理的 `README.md` 文件内容：

---

# 钉钉邮件转发服务 (DingSMTP)

这是一个基于 `aiosmtpd` 的异步 SMTP 服务器，专为局域网环境设计。它能够快速接收邮件（已针对 Windows 环境优化），并自动将邮件内容（发件人、标题、正文）以 Markdown 格式发送到指定的钉钉群聊中。

## 🚀 核心功能

1. **极速邮件接收**：
 * 基于 `asyncio` 异步框架，高并发处理。
 * **Windows 优化**：禁用了反向 DNS 解析和 `STARTTLS` 握手阻塞，解决了 Windows 下 Python SMTP 服务响应慢的问题。
 * **免认证模式**：配置了万能验证器，客户端无需复杂认证即可发送邮件。
2. **钉钉通知**：
 * 自动解析邮件主题、发件人及正文（支持 HTML/Text）。
 * 通过 Markdown 格式发送，手机端和 PC 端均可读。
3. **日报系统**：
 * 每日指定时间（默认 18:00）自动发送服务状态日报，统计当日转发邮件总数。
4. **自动流控**：
 * 支持 `HELO` 和 `EHLO` 指令，兼容各类邮件客户端（Outlook, Foxmail, 手机自带邮箱等）。

---

## 📦 环境依赖

本项目基于 Python 3.7+ 开发。

### 1. Python 库依赖
请确保安装以下库（可通过 `requirements.txt` 管理）：

```text
aiosmtpd
requests
```

**安装命令：**
```bash
pip install aiosmtpd requests
```

### 2. 运行环境
* **操作系统**：支持 Windows 10/11, Linux, macOS。
* **网络要求**：
 * 运行机器需与邮件发送端（如路由器、监控设备）在同一局域网。
 * **Windows 防火墙**：需允许 Python 进程通过 25 端口通信（通常需要管理员权限运行）。

---

## ⚙️ 配置说明

编辑代码中的 **配置区域 (Configuration Area)**：

```python
# ================= 配置区域 =================
SMTP_HOST = '0.0.0.0'             # 监听所有 IP
SMTP_PORT = 25                    # 监听端口 (Linux下需 sudo 权限)
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=..." # 钉钉机器人地址

KEYWORD = "告警"                   # 钉钉消息标题前缀
REPORT_HOUR = 18                  # 每日日报发送小时 (24小时制)
REPORT_MINUTE = 0                 # 每日日报发送分钟
MAX_EMAIL_SIZE = 10 * 1024 * 1024 # 最大邮件处理大小 (10MB)
# ===========================================
```

### 如何获取钉钉 Webhook？
1. 在钉钉群中添加“自定义机器人”。
2. 复制 Webhook URL 填入 `DINGTALK_WEBHOOK`。

---

## 🚀 使用方法

### 1. Windows 环境运行
由于监听 25 端口通常需要管理员权限，请以 **管理员身份** 打开 CMD 或 PowerShell：

```powershell
python your_script_name.py
```

### 2. Linux 环境运行
由于 25 端口是特权端口，需要使用 `sudo`：

```bash
sudo python3 your_script_name.py
```

### 3. 作为后台服务运行 (Linux)
建议使用 `systemd` 或 `supervisor` 进行守护进程管理。以下是一个简单的 `systemd` 配置示例 (`/etc/systemd/system/dingsmtp.service`)：

```ini
[Unit]
Description=DingSMTP Server
After=network.target

[Service]
User=root
WorkingDirectory=/path/to/your/script
ExecStart=/usr/bin/python3 /path/to/your/script/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动命令：
```bash
sudo systemctl enable dingsmtp
sudo systemctl start dingsmtp
```

---

## 📡 协议与兼容性

### 认证机制 (AUTH)
本服务配置了 `AnyAuthenticator`，采用**宽松验证模式**：
* 客户端发送 `AUTH LOGIN` 或 `AUTH PLAIN` 时，服务器会直接返回 `235 Authentication successful`。
* **安全提示**：由于跳过了真实的用户名/密码校验，请确保该服务仅在受信任的局域网内运行，防止对外开放后成为垃圾邮件中继。

### 数据处理
* **编码**：自动处理 Base64/Quoted-Printable 编码，支持 UTF-8, GBK, GB18030 等中文编码。
* **附件**：自动忽略附件内容，仅提取纯文本（plain text）或 HTML 正文进行转发。
* **长度限制**：为防止钉钉消息过长，正文超过 1000 字符的部分会被截断。

---

## 📅 日报机制

服务内置了一个定时任务，默认在每天 **18:00** 发送上一天的统计信息（如果当天未重置计数器，即显示当天数据）。
* **内容**：服务状态、当前时间、当日转发邮件总数。
* **计数**：每成功处理一封邮件并转发至钉钉，计数器 `DAILY_SEND_COUNT` 加 1。

---


## 📄 许可证

本项目代码仅供学习和内部网络环境使用。请勿将其暴露在公网环境中，以免被滥用于垃圾邮件转发。

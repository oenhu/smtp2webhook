import asyncio
import logging
import email
import signal
import sys
import os
import traceback
from email.header import decode_header
import requests
import json
import datetime
from concurrent.futures import ThreadPoolExecutor
# Copyright (c) 2023-2024 [https://github.com/oenhu/smtp2webhook/]. All rights reserved.
# 引入基础 SMTP 协议类
from aiosmtpd.smtp import SMTP as AioSMTP

# ================= 配置区域 =================
# 建议保持 0.0.0.0，这样可以自动监听本机所有 IP (包括 192.168.x.x)
SMTP_HOST = '0.0.0.0'
SMTP_PORT = 25
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token"

KEYWORD = "KEYWORD-TEST"
REPORT_HOUR = 18
REPORT_MINUTE = 0
MAX_EMAIL_SIZE = 10 * 1024 * 1024
# ===========================================

DAILY_SEND_COUNT = 0

# === 日志配置 ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger("mail.log").setLevel(logging.WARNING)
logging.getLogger("aiosmtpd").setLevel(logging.WARNING)
logger = logging.getLogger("MySMTPServer")
logger.setLevel(logging.INFO)

executor = ThreadPoolExecutor(max_workers=3)

# === 万能验证器 ===
class AnyAuthenticator:
    def validate(self, server, mechanism, credentials, challenge=None):
        return True

# === 1. 无赖模式 SMTP 协议类 (盲目接受所有指令) ===
class RobustLegacySMTP(AioSMTP):

    # --- [关键修改 1] 重写连接建立，跳过反向 DNS 解析 ---
    def connection_made(self, transport):
        super().connection_made(transport)
        peer = transport.get_extra_info('peername')
        if self.session and peer:
            # 强制将主机名设为 IP，避免库内部尝试解析域名导致卡顿
            self.session.host_name = peer[0]
            # logger.info(f"[{peer[0]}] 快速连接已建立")
    # ------------------------------------------------

    async def smtp_HELO(self, arg):
        """兼容 HELO 指令，但强制开启 ESMTP"""
        await super().smtp_HELO(arg)
        self.extended_smtp = True

    async def smtp_AUTH(self, arg):
        """
        彻底接管 AUTH 指令。直接告诉客户端：你通过了。
        """
        client_ip = self.session.peer[0]
        # logger.info(f"[{client_ip}] 收到认证请求: {arg} -> 准备直接放行")

        try:
            if arg and 'LOGIN' in arg.upper():
                await self.push('334 VXNlcm5hbWU6') # Username:
                await self._reader.readline()
                await self.push('334 UGFzc3dvcmQ6') # Password:
                await self._reader.readline()

            await self.push('235 2.7.0 Authentication successful')
            self.session.authenticated = True
            logger.info(f"[{client_ip}] 认证成功 (强制放行)")

        except Exception:
            logger.error(traceback.format_exc())
            await self.push('235 2.7.0 Authentication successful')

def decode_str(header_text):
    if not header_text: return ""
    decoded_fragments = []
    try:
        headers = decode_header(header_text)
        for content, encoding in headers:
            if isinstance(content, bytes):
                encoding = encoding if encoding else 'utf-8'
                try:
                    decoded_fragments.append(content.decode(encoding, errors='ignore'))
                except LookupError:
                    decoded_fragments.append(content.decode('utf-8', errors='ignore'))
                except UnicodeDecodeError:
                    decoded_fragments.append(content.decode('gb18030', errors='ignore'))
            else:
                decoded_fragments.append(str(content))
        return "".join(decoded_fragments)
    except Exception as e:
        logger.warning(f"Header decoding error: {e}")
        return str(header_text)

def get_email_content(msg):
    content = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if "attachment" in str(part.get("Content-Disposition", "")):
                    continue
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    try: content = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                    except: content = payload.decode('gb18030', errors='replace')
                    break
                elif content_type == "text/html" and not content:
                    payload = part.get_payload(decode=True)
                    try: content = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                    except: content = payload.decode('gb18030', errors='replace')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                try: content = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
                except: content = payload.decode('gb18030', errors='replace')
    except Exception as e:
        logger.error(f"解析邮件正文失败: {e}")
        return "[正文解析失败]"
    return content.strip() if content else "[无文本正文]"

def _sync_send_dingtalk(title, text):
    data = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    try:
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(DINGTALK_WEBHOOK, data=json.dumps(data), headers=headers, timeout=10)
        return resp.status_code == 200 and resp.json().get('errcode') == 0
    except Exception as e:
        logger.error(f"钉钉请求异常: {e}")
        return False

async def async_send_dingtalk(title, text):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, _sync_send_dingtalk, title, text)

async def daily_report_task():
    global DAILY_SEND_COUNT
    logger.info(f"日报调度器已启动，目标时间: {REPORT_HOUR}:{REPORT_MINUTE:02d}")
    while True:
        try:
            now = datetime.datetime.now()
            target = now.replace(hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0)
            if now >= target:
                target += datetime.timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"下次日报将在 {wait_seconds/3600:.2f} 小时后发送")

            await asyncio.sleep(wait_seconds)

            logger.info("正在发送日报...")
            report_text = (
                f"### {KEYWORD}: 服务日报 📅\n\n"
                f"**状态:** ✅ 服务运行正常\n\n"
                f"**时间:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"**今日转发:** <font color=#FF0000 size=4>{DAILY_SEND_COUNT}</font> 封\n\n"
                f"---"
            )
            await async_send_dingtalk(f"{KEYWORD}: 服务日报", report_text)
            DAILY_SEND_COUNT = 0
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("日报任务已取消")
            break
        except Exception as e:
            logger.error(f"日报任务出错: {e}")
            await asyncio.sleep(60)

class EmailHandler:
    async def handle_DATA(self, server, session, envelope):
        global DAILY_SEND_COUNT
        peer = session.peer
        logger.info(f"正在处理邮件 DATA，来源: {peer}")
        try:
            msg = email.message_from_bytes(envelope.content)
            subject = decode_str(msg.get("Subject", "无主题"))
            sender = decode_str(msg.get("From", "Unknown"))
            body = get_email_content(msg)

            logger.info(f"邮件接收成功: From={sender} Subject={subject}")

            if len(body) > 1000: body = body[:1000] + "\n...(截断)..."

            markdown_text = (
                f"### {KEYWORD}: 新邮件\n"
                f"**From:** {sender}\n"
                f"**Subject:** {subject}\n"
                f"---\n{body}"
            )

            success = await async_send_dingtalk(f"邮件: {subject}", markdown_text)
            if success:
                logger.info("钉钉通知发送成功")
            else:
                logger.error("钉钉通知发送失败")

            DAILY_SEND_COUNT += 1
            return '250 OK'
        except Exception as e:
            logger.error(f"处理邮件内容出错: {e}")
            return '500 Error'

async def main():
    loop = asyncio.get_running_loop()

    handler = EmailHandler()

    # 定义协议工厂
    def protocol_factory():
        return RobustLegacySMTP(
            handler,
            data_size_limit=MAX_EMAIL_SIZE,
            authenticator=AnyAuthenticator(),
            auth_require_tls=False,
            # --- [关键修改 2] 显式指定 hostname ---
            # 解决 Windows 上 socket.getfqdn() 阻塞几秒钟的问题
            hostname="MySMTPServer"
            # -----------------------------------
        )

    try:
        server = await loop.create_server(protocol_factory, host=SMTP_HOST, port=SMTP_PORT)
    except OSError as e:
        logger.error(f"启动失败，端口可能被占用或权限不足: {e}")
        return

    logger.info(f"="*50)
    logger.info(f"SMTP 服务已启动")
    logger.info(f"监听地址: {SMTP_HOST}:{SMTP_PORT}")
    logger.info(f"模式: Windows 极速响应模式 (已禁用 DNS 阻塞)")
    logger.info(f"="*50)

    report_task = asyncio.create_task(daily_report_task())

    try:
        if sys.platform == 'win32':
            while True:
                await asyncio.sleep(1)
        else:
            stop_event = asyncio.Event()
            loop.add_signal_handler(signal.SIGINT, lambda: stop_event.set())
            loop.add_signal_handler(signal.SIGTERM, lambda: stop_event.set())
            await stop_event.wait()

    except KeyboardInterrupt:
        logger.info("\n正在停止服务...")
    finally:
        server.close()
        await server.wait_closed()

        report_task.cancel()
        try:
            await report_task
        except asyncio.CancelledError:
            pass

        executor.shutdown(wait=True)
        logger.info("服务已安全退出")

if __name__ == '__main__':
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(main())
    except KeyboardInterrupt:
        pass
# Copyright (c) 2023-2024 [https://github.com/oenhu/smtp2webhook/]. All rights reserved.

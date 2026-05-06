from __future__ import annotations

import asyncio
import os
from dotenv import load_dotenv

from src.services.channel_delivery_service import ChannelDeliveryService

# 加载环境变量
load_dotenv()

async def test_dingtalk():
    print("=== 测试钉钉通道 ===")
    service = ChannelDeliveryService()
    webhook_url = os.getenv("DINGTALK_WEBHOOK_URL", "")
    
    if not webhook_url:
        print("请设置 DINGTALK_WEBHOOK_URL 环境变量")
        return
    
    try:
        result = await service.test_dingtalk(webhook_url)
        print(f"测试结果: {result}")
        
        # 测试发送报告
        send_result = await service.send_report(
            channel="dingtalk",
            webhook_url=webhook_url,
            title="测试报告",
            content="这是一条测试消息",
            report_url="http://example.com/report"
        )
        print(f"发送报告结果: {send_result}")
    except Exception as e:
        print(f"测试失败: {e}")

async def test_wechat():
    print("\n=== 测试企业微信通道 ===")
    service = ChannelDeliveryService()
    webhook_url = os.getenv("WECHAT_WEBHOOK_URL", "")
    
    if not webhook_url:
        print("请设置 WECHAT_WEBHOOK_URL 环境变量")
        return
    
    try:
        result = await service.test_wechat(webhook_url)
        print(f"测试结果: {result}")
        
        # 测试发送报告
        send_result = await service.send_report(
            channel="wechat",
            webhook_url=webhook_url,
            title="测试报告",
            content="这是一条测试消息",
            report_url="http://example.com/report"
        )
        print(f"发送报告结果: {send_result}")
    except Exception as e:
        print(f"测试失败: {e}")

async def test_email():
    print("\n=== 测试邮件通道 ===")
    service = ChannelDeliveryService()
    
    smtp_server = os.getenv("EMAIL_SMTP_SERVER", "")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    username = os.getenv("EMAIL_USERNAME", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    to_email = os.getenv("EMAIL_TO", "")
    from_email = os.getenv("EMAIL_FROM", username)
    
    if not all([smtp_server, username, password, to_email]):
        print("请设置邮件相关环境变量")
        return
    
    try:
        result = await service.test_email(smtp_server, smtp_port, username, password)
        print(f"测试结果: {result}")
        
        # 测试发送邮件
        send_result = await service.send_report(
            channel="email",
            to=to_email,
            from_email=from_email,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            username=username,
            password=password,
            title="测试报告",
            content="这是一条测试消息",
            report_url="http://example.com/report"
        )
        print(f"发送邮件结果: {send_result}")
    except Exception as e:
        print(f"测试失败: {e}")

async def main():
    await test_dingtalk()
    await test_wechat()
    await test_email()

if __name__ == "__main__":
    asyncio.run(main())

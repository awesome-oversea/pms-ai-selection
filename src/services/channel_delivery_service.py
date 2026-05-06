from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from src.config.settings import get_settings
from src.infrastructure.dingtalk_client import DingtalkClient
from src.infrastructure.email_client import EmailClient
from src.infrastructure.wechat_client import WechatClient


class ChannelCallbackVerificationError(Exception):
    def __init__(self, message: str, *, http_status: int = 403) -> None:
        super().__init__(message)
        self.http_status = http_status


class ChannelDeliveryService:
    def __init__(self,
                 dingtalk_client: DingtalkClient | None = None,
                 wechat_client: WechatClient | None = None,
                 email_client: EmailClient | None = None) -> None:
        self.dingtalk_client = dingtalk_client
        self.wechat_client = wechat_client
        self.email_client = email_client

    @staticmethod
    def _resolve_callback_credentials(channel: str) -> tuple[str | None, str | None]:
        security = get_settings().security
        if channel == "dingtalk":
            return security.dingtalk_callback_token, security.dingtalk_callback_secret
        if channel == "wechat":
            return security.wechat_callback_token, security.wechat_callback_secret
        raise ChannelCallbackVerificationError(f"Unsupported callback channel: {channel}", http_status=400)

    @staticmethod
    def build_callback_signature(
        *,
        channel: str,
        token: str,
        secret: str,
        timestamp: str,
        nonce: str,
    ) -> str:
        message = "\n".join([channel, token, timestamp, nonce]).encode("utf-8")
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify_callback_url(
        self,
        *,
        channel: str,
        timestamp: str,
        nonce: str,
        signature: str,
        challenge: str | None = None,
    ) -> dict[str, Any]:
        security = get_settings().security
        if not security.channel_callback_verification_enabled:
            return {
                "verified": True,
                "verification_mode": "disabled",
                "challenge": challenge,
            }

        token, secret = self._resolve_callback_credentials(channel)
        if not token or not secret:
            raise ChannelCallbackVerificationError(
                f"Callback verification credentials are not configured for {channel}",
                http_status=503,
            )

        try:
            request_ts = int(timestamp)
        except ValueError as exc:
            raise ChannelCallbackVerificationError("Invalid callback timestamp", http_status=400) from exc

        if abs(int(time.time()) - request_ts) > security.channel_callback_ttl_seconds:
            raise ChannelCallbackVerificationError("Callback timestamp expired", http_status=403)

        expected_signature = self.build_callback_signature(
            channel=channel,
            token=token,
            secret=secret,
            timestamp=timestamp,
            nonce=nonce,
        )
        if not hmac.compare_digest(expected_signature, signature):
            raise ChannelCallbackVerificationError("Invalid callback signature", http_status=403)

        return {
            "verified": True,
            "verification_mode": "hmac-sha256",
            "challenge": challenge,
            "channel": channel,
            "timestamp": timestamp,
        }

    async def test_dingtalk(self, webhook_url: str) -> dict[str, Any]:
        client = self.dingtalk_client or DingtalkClient(webhook_url=webhook_url)
        result = await client.test_connection()
        return {
            "channel": "dingtalk",
            "message_type": "connectivity_test",
            "audit_meta": {"template_used": "healthcheck"},
            **result,
        }

    async def test_wechat(self, webhook_url: str) -> dict[str, Any]:
        client = self.wechat_client or WechatClient(webhook_url=webhook_url)
        result = await client.test_connection()
        return {
            "channel": "wechat",
            "message_type": "connectivity_test",
            "audit_meta": {"template_used": "healthcheck"},
            **result,
        }

    async def test_email(self, smtp_server: str, smtp_port: int, username: str, password: str) -> dict[str, Any]:
        client = self.email_client or EmailClient(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            username=username,
            password=password
        )
        result = await client.test_connection()
        return {
            "channel": "email",
            "message_type": "connectivity_test",
            "audit_meta": {"template_used": "healthcheck"},
            **result,
        }

    async def send_report(self, *,
                         channel: str,
                         title: str,
                         content: str,
                         report_url: str | None = None,
                         **kwargs) -> dict[str, Any]:
        body = content if report_url is None else f"{content}\n\n下载链接: {report_url}"

        if channel == "dingtalk":
            webhook_url = kwargs.get("webhook_url")
            client = self.dingtalk_client or DingtalkClient(webhook_url=webhook_url)
            result = await client.send_text(title=title, content=body)
            return {
                "channel": "dingtalk",
                "message_type": "report_delivery",
                "template_used": "summary_with_link" if report_url else "summary_only",
                "delivered": True,
                "audit_meta": {"has_report_url": report_url is not None},
                "result": result,
            }
        elif channel == "wechat":
            webhook_url = kwargs.get("webhook_url")
            client = self.wechat_client or WechatClient(webhook_url=webhook_url)
            result = await client.send_text(title=title, content=body)
            return {
                "channel": "wechat",
                "message_type": "report_delivery",
                "template_used": "summary_with_link" if report_url else "summary_only",
                "delivered": True,
                "audit_meta": {"has_report_url": report_url is not None},
                "result": result,
            }
        elif channel == "email":
            to = kwargs.get("to")
            from_email = kwargs.get("from_email")
            smtp_server = kwargs.get("smtp_server")
            smtp_port = kwargs.get("smtp_port")
            username = kwargs.get("username")
            password = kwargs.get("password")

            client = self.email_client or EmailClient(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                username=username,
                password=password
            )

            result = await client.send_email(
                to=to,
                subject=title,
                content=body,
                from_email=from_email
            )

            return {
                "channel": "email",
                "message_type": "report_delivery",
                "template_used": "summary_with_link" if report_url else "summary_only",
                "delivered": True,
                "audit_meta": {"has_report_url": report_url is not None},
                "result": result,
            }
        else:
            return {
                "channel": channel,
                "message_type": "report_delivery",
                "delivered": False,
                "error": f"Unsupported channel: {channel}",
                "audit_meta": {"has_report_url": report_url is not None},
            }

    async def share_report_link(self, *, channel: str, webhook_url: str, report_title: str, report_summary: str, share_url: str) -> dict[str, Any]:
        summary = report_summary.strip() if report_summary.strip() else "报告已生成，可通过以下链接查看。"
        content = f"{summary}\n\n访问链接: {share_url}"
        return await self.send_report(
            channel=channel,
            title=report_title,
            content=content,
            report_url=share_url,
            webhook_url=webhook_url,
        )

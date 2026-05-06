from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib


class EmailClientError(Exception):
    def __init__(self, message: str, *, error_code: str, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class EmailClient:
    def __init__(self, *, smtp_server: str, smtp_port: int, username: str, password: str, timeout_seconds: float = 10.0) -> None:
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds

    async def test_connection(self) -> dict[str, Any]:
        try:
            async with aiosmtplib.SMTP(hostname=self.smtp_server, port=self.smtp_port, timeout=self.timeout_seconds) as smtp:
                await smtp.login(self.username, self.password)
            return {"status": "ok", "message": "Connection successful"}
        except aiosmtplib.SMTPException as e:
            raise EmailClientError(str(e), error_code="smtp_error", retryable=True)
        except Exception as e:
            raise EmailClientError(str(e), error_code="connection_error", retryable=True)

    async def send_email(self, *, to: str, subject: str, content: str, from_email: str | None = None) -> dict[str, Any]:
        msg = MIMEMultipart()
        msg["From"] = from_email or self.username
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(content, "plain", "utf-8"))

        try:
            async with aiosmtplib.SMTP(hostname=self.smtp_server, port=self.smtp_port, timeout=self.timeout_seconds) as smtp:
                await smtp.login(self.username, self.password)
                await smtp.send_message(msg)
            return {"status": "ok", "message": "Email sent successfully"}
        except aiosmtplib.SMTPException as e:
            raise EmailClientError(str(e), error_code="smtp_error", retryable=True)
        except Exception as e:
            raise EmailClientError(str(e), error_code="sending_error", retryable=True)

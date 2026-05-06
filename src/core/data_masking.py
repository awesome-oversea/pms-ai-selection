from __future__ import annotations

import os
import re
from typing import Any


class DataMasking:
    """数据脱敏工具类"""

    @staticmethod
    def mask_email(email: str) -> str:
        """脱敏邮箱地址"""
        if not email:
            return email

        pattern = r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        match = re.match(pattern, email)
        if not match:
            return email

        username, domain = match.groups()
        if len(username) <= 3:
            masked_username = username[0] + '*' * (len(username) - 1)
        else:
            masked_username = username[:3] + '*' * max(len(username) - 3, 3)

        return f"{masked_username}@{domain}"

    @staticmethod
    def mask_phone(phone: str) -> str:
        """脱敏手机号"""
        if not phone:
            return phone

        # 匹配中国手机号
        pattern = r'1[3-9]\d{9}'
        match = re.match(pattern, phone)
        if match:
            return phone[:3] + '****' + phone[-4:]

        # 匹配其他电话号码
        if len(phone) > 6:
            return phone[:3] + '****' + phone[-3:]

        return phone

    @staticmethod
    def mask_id_card(id_card: str) -> str:
        """脱敏身份证号"""
        if not id_card:
            return id_card

        if len(id_card) >= 15:
            return id_card[:3] + '********' + id_card[-4:]

        return id_card

    @staticmethod
    def mask_bank_card(bank_card: str) -> str:
        """脱敏银行卡号"""
        if not bank_card:
            return bank_card

        if len(bank_card) >= 16:
            return bank_card[:4] + ' **** **** ' + bank_card[-4:]

        return bank_card

    @staticmethod
    def mask_password(password: str) -> str:
        """脱敏密码"""
        if not password:
            return password

        return '******'

    @staticmethod
    def mask_db_url(db_url: str) -> str:
        """脱敏数据库连接字符串"""
        if not db_url:
            return db_url

        # 匹配数据库连接字符串
        pattern = r'(postgresql\+asyncpg://)([^:]+):([^@]+)@([^/]+)/(.*)'
        match = re.match(pattern, db_url)
        if match:
            scheme, username, password, host, db = match.groups()
            return f"{scheme}{username}:******@{host}/{db}"

        return db_url

    @staticmethod
    def mask_text(value: str) -> str:
        if not value:
            return value
        if len(value) <= 1:
            return "*"
        if len(value) == 2:
            return value[0] + "*"
        return value[0] + "*" * (len(value) - 2) + value[-1]

    @staticmethod
    def _default_sensitive_fields() -> list[str]:
        fields = [
            'password', 'passwd', 'pwd',
            'email', 'mail',
            'phone', 'mobile', 'tel',
            'id_card', 'idcard', 'identity', 'passport',
            'bank_card', 'bankcard', 'card',
            'token', 'secret', 'key',
            'db_url', 'database_url',
            'name', 'full_name', 'customer_name', 'employee_name', 'receiver',
            'address', 'wechat',
        ]
        extra = os.getenv("SEC_PII_FIELD_PATTERNS", "")
        fields.extend(item.strip().lower() for item in extra.split(",") if item.strip())
        return fields

    @staticmethod
    def _is_sensitive_key(key: str, sensitive_fields: list[str]) -> bool:
        key_lower = key.lower()
        return any(field and (key_lower == field or field in key_lower) for field in sensitive_fields)

    @staticmethod
    def mask_sensitive_data(data: Any, sensitive_fields: list[str] | None = None) -> Any:
        """递归脱敏敏感数据"""
        if sensitive_fields is None:
            sensitive_fields = DataMasking._default_sensitive_fields()
        else:
            sensitive_fields = [field.lower() for field in sensitive_fields]

        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                key_lower = key.lower()
                if DataMasking._is_sensitive_key(key, sensitive_fields):
                    if key_lower in ['email', 'mail'] or 'email' in key_lower:
                        result[key] = DataMasking.mask_email(str(value))
                    elif key_lower in ['phone', 'mobile', 'tel'] or 'phone' in key_lower or 'mobile' in key_lower:
                        result[key] = DataMasking.mask_phone(str(value))
                    elif key_lower in ['id_card', 'idcard', 'identity']:
                        result[key] = DataMasking.mask_id_card(str(value))
                    elif key_lower == 'passport' or 'passport' in key_lower:
                        result[key] = DataMasking.mask_text(str(value))
                    elif key_lower in ['bank_card', 'bankcard', 'card'] or 'bank_card' in key_lower:
                        result[key] = DataMasking.mask_bank_card(str(value))
                    elif key_lower in ['password', 'passwd', 'pwd'] or 'password' in key_lower:
                        result[key] = DataMasking.mask_password(str(value))
                    elif key_lower in ['db_url', 'database_url']:
                        result[key] = DataMasking.mask_db_url(str(value))
                    elif isinstance(value, (dict, list)):
                        result[key] = DataMasking.mask_sensitive_data(value, sensitive_fields)
                    else:
                        result[key] = DataMasking.mask_text(str(value))
                else:
                    result[key] = DataMasking.mask_sensitive_data(value, sensitive_fields)
            return result
        elif isinstance(data, list):
            return [DataMasking.mask_sensitive_data(item, sensitive_fields) for item in data]
        else:
            return data


def mask_sensitive_data(data: Any, sensitive_fields: list[str] | None = None) -> Any:
    """Backwards-compatible module-level wrapper for legacy imports."""
    return DataMasking.mask_sensitive_data(data, sensitive_fields)


__all__ = ["DataMasking", "mask_sensitive_data"]

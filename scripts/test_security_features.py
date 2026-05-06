from __future__ import annotations

from src.core.data_masking import DataMasking
from src.core.waf import is_ip_allowed


def test_data_masking():
    print("=== 测试数据脱敏功能 ===")
    
    # 测试邮箱脱敏
    email = "user@example.com"
    masked_email = DataMasking.mask_email(email)
    print(f"邮箱脱敏: {email} -> {masked_email}")
    
    # 测试手机号脱敏
    phone = "13812345678"
    masked_phone = DataMasking.mask_phone(phone)
    print(f"手机号脱敏: {phone} -> {masked_phone}")
    
    # 测试身份证号脱敏
    id_card = "110101199001011234"
    masked_id_card = DataMasking.mask_id_card(id_card)
    print(f"身份证号脱敏: {id_card} -> {masked_id_card}")
    
    # 测试银行卡号脱敏
    bank_card = "6222021234567890123"
    masked_bank_card = DataMasking.mask_bank_card(bank_card)
    print(f"银行卡号脱敏: {bank_card} -> {masked_bank_card}")
    
    # 测试密码脱敏
    password = "mypassword123"
    masked_password = DataMasking.mask_password(password)
    print(f"密码脱敏: {password} -> {masked_password}")
    
    # 测试数据库连接字符串脱敏
    db_url = "postgresql+asyncpg://user:password@localhost:5432/db"
    masked_db_url = DataMasking.mask_db_url(db_url)
    print(f"数据库连接字符串脱敏: {db_url} -> {masked_db_url}")
    
    # 测试递归脱敏
    test_data = {
        "user": {
            "name": "John",
            "email": "john@example.com",
            "phone": "13812345678",
            "password": "secret123",
            "id_card": "110101199001011234"
        },
        "database": {
            "url": "postgresql+asyncpg://user:password@localhost:5432/db"
        }
    }
    
    masked_data = DataMasking.mask_sensitive_data(test_data)
    print(f"递归脱敏: {test_data} -> {masked_data}")


def test_ip_whitelist():
    print("\n=== 测试IP白名单功能 ===")
    
    # 测试本地IP
    local_ip = "127.0.0.1"
    is_allowed = is_ip_allowed(local_ip)
    print(f"本地IP {local_ip} 是否允许: {is_allowed}")
    
    # 测试其他IP
    test_ip = "192.168.1.1"
    is_allowed = is_ip_allowed(test_ip)
    print(f"测试IP {test_ip} 是否允许: {is_allowed}")


def main():
    test_data_masking()
    test_ip_whitelist()

if __name__ == "__main__":
    main()

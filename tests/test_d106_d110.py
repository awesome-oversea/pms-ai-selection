"""D106-D110 单元测试: 安全加固与备份恢复"""


import pytest
from src.infrastructure.security_backup import (
    AuditLog,
    AuditLogger,
    BackupJob,
    BackupManager,
    BackupStatus,
    BackupType,
    Incident,
    IncidentManager,
    IncidentSeverity,
    IncidentStatus,
    LogLevel,
    RecoveryTest,
    RecoveryTester,
    SecurityCheck,
    SecurityLayer,
    SecurityManager,
    SecurityStatus,
)


class TestSecurityCheck:
    """测试安全检查"""

    def test_check_creation(self):
        check = SecurityCheck(
            check_id="SEC_001",
            layer=SecurityLayer.NETWORK,
            name="VPC隔离",
            description="VPC网络隔离配置",
        )
        assert check.check_id == "SEC_001"
        assert check.status == SecurityStatus.UNKNOWN

    def test_check_to_dict(self):
        check = SecurityCheck(
            check_id="SEC_001",
            layer=SecurityLayer.AUTHENTICATION,
            name="OAuth2",
            description="OAuth2认证",
            status=SecurityStatus.SECURE,
        )
        d = check.to_dict()
        assert d["status"] == "secure"


class TestAuditLog:
    """测试审计日志"""

    def test_log_creation(self):
        log = AuditLog(
            log_id="LOG_001",
            log_type="access",
            level=LogLevel.INFO,
            message="用户登录",
        )
        assert log.log_id == "LOG_001"
        assert log.retention_days == 30

    def test_log_to_dict(self):
        log = AuditLog(
            log_id="LOG_001",
            log_type="security",
            level=LogLevel.CRITICAL,
            message="异常登录",
            user_id="user123",
            retention_days=730,
        )
        d = log.to_dict()
        assert d["retention_days"] == 730


class TestBackupJob:
    """测试备份任务"""

    def test_job_creation(self):
        job = BackupJob(
            job_id="BACKUP_001",
            target="postgresql",
            backup_type=BackupType.FULL,
        )
        assert job.job_id == "BACKUP_001"
        assert job.status == BackupStatus.PENDING

    def test_job_to_dict(self):
        job = BackupJob(
            job_id="BACKUP_001",
            target="redis",
            backup_type=BackupType.SNAPSHOT,
            status=BackupStatus.COMPLETED,
            size_bytes=1000000,
        )
        d = job.to_dict()
        assert d["size_bytes"] == 1000000


class TestRecoveryTest:
    """测试恢复演练"""

    def test_test_creation(self):
        test = RecoveryTest(
            test_id="RECOVERY_001",
            scenario="PG主库故障",
            target_rto_minutes=5,
            target_rpo_minutes=60,
        )
        assert test.test_id == "RECOVERY_001"
        assert test.passed is False

    def test_test_to_dict(self):
        test = RecoveryTest(
            test_id="RECOVERY_001",
            scenario="Redis故障",
            target_rto_minutes=10,
            target_rpo_minutes=60,
            actual_rto_minutes=8.5,
            actual_rpo_minutes=30.0,
            passed=True,
        )
        d = test.to_dict()
        assert d["passed"] is True


class TestIncident:
    """测试应急事件"""

    def test_incident_creation(self):
        incident = Incident(
            incident_id="INC_001",
            title="数据库连接异常",
            description="主库无法连接",
            severity=IncidentSeverity.P0,
        )
        assert incident.incident_id == "INC_001"
        assert incident.status == IncidentStatus.DETECTED

    def test_incident_to_dict(self):
        incident = Incident(
            incident_id="INC_001",
            title="服务宕机",
            description="API服务不可用",
            severity=IncidentSeverity.P1,
            status=IncidentStatus.RESOLVED,
            root_cause="内存溢出",
            resolution="重启服务",
        )
        d = incident.to_dict()
        assert d["severity"] == "P1"


class TestSecurityManager:
    """测试安全管理器(D106)"""

    def setup_method(self):
        self.security = SecurityManager()

    @pytest.mark.asyncio
    async def test_run_check(self):
        check = await self.security.run_check(
            layer=SecurityLayer.NETWORK,
            name="VPC隔离",
            description="VPC网络隔离配置",
        )
        assert check.check_id.startswith("SEC_")
        assert check.status in [SecurityStatus.SECURE, SecurityStatus.WARNING, SecurityStatus.VULNERABLE]

    @pytest.mark.asyncio
    async def test_run_all_checks(self):
        checks = await self.security.run_all_checks()
        assert len(checks) == 8

    @pytest.mark.asyncio
    async def test_run_vulnerability_scan(self):
        result = await self.security.run_vulnerability_scan()
        assert "scan_id" in result
        assert "total_vulnerabilities" in result

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.security.run_all_checks()
        stats = self.security.get_stats()
        assert stats["total_checks"] == 8


class TestAuditLogger:
    """测试日志审计系统(D107)"""

    def setup_method(self):
        self.audit = AuditLogger()

    @pytest.mark.asyncio
    async def test_log(self):
        log = await self.audit.log(
            log_type="access",
            level=LogLevel.INFO,
            message="用户登录成功",
            user_id="user123",
            ip_address="192.168.1.1",
        )
        assert log.log_id.startswith("LOG_")

    @pytest.mark.asyncio
    async def test_search_logs(self):
        await self.audit.log("access", LogLevel.INFO, "日志1")
        await self.audit.log("security", LogLevel.WARNING, "日志2")
        results = await self.audit.search_logs(log_type="access")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.audit.log("access", LogLevel.INFO, "测试")
        stats = self.audit.get_stats()
        assert stats["total_logs"] == 1


class TestBackupManager:
    """测试备份管理器(D108)"""

    def setup_method(self):
        self.backup = BackupManager()

    @pytest.mark.asyncio
    async def test_create_backup_job(self):
        job = await self.backup.create_backup_job(
            target="postgresql",
            backup_type=BackupType.FULL,
        )
        assert job.job_id.startswith("BACKUP_")

    @pytest.mark.asyncio
    async def test_execute_backup(self):
        job = await self.backup.create_backup_job("redis", BackupType.SNAPSHOT)
        result = await self.backup.execute_backup(job.job_id)
        assert result.status in [BackupStatus.COMPLETED, BackupStatus.FAILED]

    @pytest.mark.asyncio
    async def test_run_scheduled_backups(self):
        jobs = await self.backup.run_scheduled_backups()
        assert len(jobs) == 3

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.backup.run_scheduled_backups()
        stats = self.backup.get_stats()
        assert stats["total_jobs"] == 3


class TestRecoveryTester:
    """测试恢复演练器(D109)"""

    def setup_method(self):
        self.recovery = RecoveryTester()

    @pytest.mark.asyncio
    async def test_run_test(self):
        test = await self.recovery.run_test(
            scenario="PG主库故障",
            target_rto_minutes=5,
            target_rpo_minutes=60,
        )
        assert test.test_id.startswith("RECOVERY_")
        assert test.actual_rto_minutes > 0

    @pytest.mark.asyncio
    async def test_run_all_tests(self):
        tests = await self.recovery.run_all_tests()
        assert len(tests) == 4

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.recovery.run_all_tests()
        stats = self.recovery.get_stats()
        assert stats["total_tests"] == 4


class TestIncidentManager:
    """测试应急响应管理器(D110)"""

    def setup_method(self):
        self.incident = IncidentManager()

    @pytest.mark.asyncio
    async def test_create_incident(self):
        incident = await self.incident.create_incident(
            title="数据库连接异常",
            description="主库无法连接",
            severity=IncidentSeverity.P0,
        )
        assert incident.incident_id.startswith("INC_")
        assert incident.severity == IncidentSeverity.P0

    @pytest.mark.asyncio
    async def test_update_incident(self):
        incident = await self.incident.create_incident(
            title="测试事件",
            description="描述",
            severity=IncidentSeverity.P1,
        )
        updated = await self.incident.update_incident(
            incident.incident_id,
            IncidentStatus.INVESTIGATING,
            assignee="admin",
        )
        assert updated.status == IncidentStatus.INVESTIGATING

    @pytest.mark.asyncio
    async def test_get_incident(self):
        created = await self.incident.create_incident(
            title="事件",
            description="描述",
            severity=IncidentSeverity.P2,
        )
        incident = await self.incident.get_incident(created.incident_id)
        assert incident.title == "事件"

    @pytest.mark.asyncio
    async def test_list_incidents(self):
        await self.incident.create_incident("事件1", "", IncidentSeverity.P0)
        await self.incident.create_incident("事件2", "", IncidentSeverity.P1)
        incidents = await self.incident.list_incidents(severity=IncidentSeverity.P0)
        assert len(incidents) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self):
        await self.incident.create_incident("事件", "", IncidentSeverity.P1)
        stats = self.incident.get_stats()
        assert stats["total_incidents"] == 1


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_security_backup_workflow(self):
        security = SecurityManager()
        audit = AuditLogger()
        backup = BackupManager()
        recovery = RecoveryTester()
        incident = IncidentManager()

        checks = await security.run_all_checks()
        vulnerable = [c for c in checks if c.status == SecurityStatus.VULNERABLE]

        if vulnerable:
            await audit.log(
                "security",
                LogLevel.WARNING,
                f"发现{len(vulnerable)}个安全问题",
            )

            await incident.create_incident(
                "安全漏洞",
                f"发现{len(vulnerable)}个安全漏洞",
                IncidentSeverity.P1,
            )

        jobs = await backup.run_scheduled_backups()
        tests = await recovery.run_all_tests()

        assert len(checks) == 8
        assert len(jobs) == 3
        assert len(tests) == 4


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))

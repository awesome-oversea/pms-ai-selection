# ETL Pipeline设计文档

> **项目名称**: 跨境电商AI选品系统（PMS增强版）
> **文档类型**: 数据处理管道设计文档
> **子任务**: D12 - ETL数据清洗管道
> **文档版本**: v1.0

---

## 1. 概述

ETL Pipeline是基于PyFlink的实时数据清洗管道，从Kafka消费原始采集数据，执行去重、格式归一化、异常值剔除等清洗操作，将高质量数据写入PostgreSQL和Qdrant。

| 项目 | 规格 |
|------|------|
| 框架 | PyFlink (Flink 1.17.1) |
| 数据源 | Kafka: amazon-data topic |
| 数据汇 | Kafka: amazon-data-cleaned topic → PG/Qdrant |
| 并行度 | 4 |
| 数据质量目标 | >95%准确率 |
| 处理吞吐目标 | >5000 events/s |

---

## 2. ETL处理流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Kafka   │ →  │  去重    │ →  │ 格式归一  │ →  │ 异常值   │ →  │ 数据汇   │
│  Source  │    │ ASIN+date│    │ 化处理    │    │ 剔除     │    │ PG/Qdrant│
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

---

## 3. 核心实现

### 3.1 DataCleaningETL主类

```python
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink

class DataCleaningETL:
    def __init__(self):
        self.env = StreamExecutionEnvironment.get_execution_environment()
        self.env.set_parallelism(4)

    def create_kafka_source(self):
        return KafkaSource.builder() \
            .set_bootstrap_servers("kafka:9092") \
            .set_topics("amazon-data") \
            .set_group_id("etl-consumer") \
            .set_starting_offsets(OffsetsInitializer.earliest()) \
            .build()

    def clean_data(self, row):
        cleaned = row.copy()
        # 价格异常值剔除
        if cleaned.price < 0 or cleaned.price > 99999:
            cleaned.price = None
        # 评分范围校验
        if cleaned.rating < 0 or cleaned.rating > 5:
            cleaned.rating = None
        # 标题清洗
        cleaned.title = cleaned.title.strip() if cleaned.title else ""
        return cleaned

    def run(self):
        source = self.create_kafka_source()
        sink = self.create_kafka_sink()
        stream = self.env.from_source(source, WatermarkStrategy.no_watermarks(), "Kafka Source")
        cleaned_stream = stream.process(self.clean_data)
        cleaned_stream.sink_to(sink)
        self.env.execute("Amazon Data ETL")
```

### 3.2 数据质量检查

```python
class DataQualityChecker:
    def __init__(self):
        self.rules = {
            "price": lambda x: x is None or (0 < x <= 99999),
            "rating": lambda x: x is None or (0 <= x <= 5),
            "title": lambda x: len(x) > 0 and len(x) <= 500,
            "asin": lambda x: len(x) == 10 and x.isalnum()
        }

    def check(self, data: dict) -> dict:
        result = {"valid": True, "errors": []}
        for field, rule in self.rules.items():
            value = data.get(field)
            if not rule(value):
                result["valid"] = False
                result["errors"].append({"field": field, "value": value})
        return result

    def check_batch(self, data_list: list) -> dict:
        results = {"total": len(data_list), "valid": 0, "invalid": 0}
        for data in data_list:
            if self.check(data)["valid"]:
                results["valid"] += 1
            else:
                results["invalid"] += 1
        return results
```

### 3.3 代码文件

完整实现代码: [src/services/etl.py](../../src/services/etl.py)

---

## 4. 清洗规则详述

| 规则 | 字段 | 条件 | 处理方式 |
|------|------|------|---------|
| 去重 | ASIN+date | 唯一键重复 | 只保留最新1条 |
| 价格归一化 | price | 统一USD货币/单位 | 汇率转换 |
| 评分归一化 | rating | 归一化到1-5 | 范围映射 |
| 价格异常剔除 | price | <0 或 >99999 | 设为NULL |
| 评分异常剔除 | rating | <0 或 >5 或非数字 | 设为NULL |
| 标题清洗 | title | 去除首尾空白 | strip() |
| ASIN校验 | asin | 长度=10, 字母数字 | 非法则丢弃 |

---

## 5. 验收检查清单

| 检查项 | 预期结果 | 状态 |
|--------|---------|------|
| 去重逻辑 | ASIN+date唯一键去重 | ☐ |
| 格式归一化 | price统一货币, rating归一化(1-5) | ☐ |
| 异常值剔除 | price<0或>99999, rating非法值 | ☐ |
| 数据质量>95% | 抽样100条人工核对 | ☐ |
| 处理吞吐>5000 events/s | 压测验证 | ☐ |

---

**文档状态**: ✅ 已完成

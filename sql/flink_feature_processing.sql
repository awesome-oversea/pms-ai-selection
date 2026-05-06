SET 'execution.runtime-mode' = 'batch';
SET 'pipeline.name' = 'pms-flink-feature-processing-demo';

CREATE TEMPORARY TABLE feature_input (
  product_id STRING,
  sales_7d INT,
  sales_30d INT,
  positive_reviews INT,
  total_reviews INT,
  inventory INT
) WITH (
  'connector' = 'filesystem',
  'path' = 'file:///tmp/pms-flink/feature/feature_input.csv',
  'format' = 'csv'
);

CREATE TEMPORARY TABLE feature_output (
  product_id STRING,
  sales_growth_rate DOUBLE,
  review_sentiment_score DOUBLE,
  demand_supply_ratio DOUBLE
) WITH (
  'connector' = 'filesystem',
  'path' = 'file:///tmp/pms-flink/feature/output',
  'format' = 'csv'
);

INSERT INTO feature_output
SELECT
  product_id,
  CAST(sales_7d AS DOUBLE) / CASE WHEN sales_30d = 0 THEN 1.0 ELSE CAST(sales_30d AS DOUBLE) END,
  CAST(positive_reviews AS DOUBLE) / CASE WHEN total_reviews = 0 THEN 1.0 ELSE CAST(total_reviews AS DOUBLE) END,
  CAST(sales_7d AS DOUBLE) / CASE WHEN inventory = 0 THEN 1.0 ELSE CAST(inventory AS DOUBLE) END
FROM feature_input;

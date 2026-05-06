SET 'execution.runtime-mode' = 'batch';
SET 'pipeline.name' = 'pms-flink-trendwide-demo';

CREATE TEMPORARY TABLE trend_input (
  keyword STRING,
  source_name STRING,
  trend_7d INT,
  trend_30d INT,
  peak_heat INT
) WITH (
  'connector' = 'filesystem',
  'path' = 'file:///tmp/pms-flink/trendwide/trendwide_input.csv',
  'format' = 'csv'
);

CREATE TEMPORARY TABLE trend_output (
  keyword STRING,
  source_name STRING,
  growth_7d_vs_30d DOUBLE,
  peak_heat INT,
  lifecycle_stage STRING
) WITH (
  'connector' = 'filesystem',
  'path' = 'file:///tmp/pms-flink/trendwide/output',
  'format' = 'csv'
);

INSERT INTO trend_output
SELECT
  keyword,
  source_name,
  CAST(trend_7d AS DOUBLE) / CASE WHEN trend_30d = 0 THEN 1.0 ELSE CAST(trend_30d AS DOUBLE) END,
  peak_heat,
  CASE
    WHEN peak_heat >= 80 THEN 'hot'
    WHEN trend_7d > trend_30d THEN 'rising'
    WHEN trend_7d = trend_30d THEN 'stable'
    ELSE 'cooling'
  END
FROM trend_input;

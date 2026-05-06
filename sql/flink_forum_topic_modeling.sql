SET 'execution.runtime-mode' = 'batch';
SET 'pipeline.name' = 'pms-flink-forum-topic-demo';

CREATE TEMPORARY TABLE forum_input (
  topic STRING,
  keyword STRING,
  mentions INT,
  replies INT
) WITH (
  'connector' = 'filesystem',
  'path' = 'file:///tmp/pms-flink/forum-topic/forum_topic_input.csv',
  'format' = 'csv'
);

CREATE TEMPORARY TABLE forum_output (
  topic STRING,
  keyword_count BIGINT,
  topic_heat BIGINT
) WITH (
  'connector' = 'filesystem',
  'path' = 'file:///tmp/pms-flink/forum-topic/output',
  'format' = 'csv'
);

INSERT INTO forum_output
SELECT
  topic,
  COUNT(DISTINCT keyword) AS keyword_count,
  SUM(CAST(mentions + replies AS BIGINT)) AS topic_heat
FROM forum_input
GROUP BY topic;

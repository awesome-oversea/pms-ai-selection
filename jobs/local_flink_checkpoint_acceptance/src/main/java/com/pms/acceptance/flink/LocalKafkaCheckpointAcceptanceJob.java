package com.pms.acceptance.flink;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.File;
import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.OpenContext;
import org.apache.flink.api.common.serialization.SimpleStringEncoder;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.connector.file.sink.FileSink;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.core.fs.Path;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.streaming.api.functions.sink.filesystem.rollingpolicies.OnCheckpointRollingPolicy;
import org.apache.flink.util.Collector;

public final class LocalKafkaCheckpointAcceptanceJob {
  private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();

  private LocalKafkaCheckpointAcceptanceJob() {}

  public static void main(String[] args) throws Exception {
    Map<String, String> params = parseArgs(args);
    String brokers = required(params, "brokers");
    String inputTopic = required(params, "input-topic");
    String outputPath = required(params, "output-path");
    String groupId = required(params, "group-id");
    String failMarkerPath = required(params, "fail-marker-path");

    StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
    env.setParallelism(1);
    env.enableCheckpointing(2_000L);
    env.getCheckpointConfig().setMinPauseBetweenCheckpoints(1_000L);
    env.getCheckpointConfig().setCheckpointTimeout(60_000L);
    env.getCheckpointConfig().setMaxConcurrentCheckpoints(1);

    KafkaSource<String> kafkaSource =
        KafkaSource.<String>builder()
            .setBootstrapServers(brokers)
            .setTopics(inputTopic)
            .setGroupId(groupId)
            .setStartingOffsets(OffsetsInitializer.earliest())
            .setValueOnlyDeserializer(new SimpleStringSchema())
            .setProperty("commit.offsets.on.checkpoint", "true")
            .build();

    FileSink<String> fileSink =
        FileSink.<String>forRowFormat(new Path(outputPath), new SimpleStringEncoder<>(StandardCharsets.UTF_8.name()))
            .withRollingPolicy(OnCheckpointRollingPolicy.build())
            .build();

    env.fromSource(kafkaSource, WatermarkStrategy.noWatermarks(), "acceptance-kafka-source")
        .keyBy(LocalKafkaCheckpointAcceptanceJob::extractProductId)
        .process(new ProjectionProcessFunction(failMarkerPath))
        .name("local-feature-projection")
        .sinkTo(fileSink)
        .name("projection-file-sink");

    env.execute("local-flink-kafka-checkpoint-acceptance");
  }

  private static String extractProductId(String raw) {
    try {
      JsonNode root = MAPPER.readTree(raw);
      String productId = text(root, "product_id");
      if (!productId.isBlank()) {
        return productId;
      }
      if (root.has("payload") && root.get("payload").isObject()) {
        JsonNode payload = root.get("payload");
        productId = text(payload, "product_id");
        if (!productId.isBlank()) {
          return productId;
        }
      }
    } catch (Exception ignored) {
      // Fallback to a deterministic key so malformed data still stays in one partition.
    }
    return "unknown-product";
  }

  private static Map<String, String> parseArgs(String[] args) {
    Map<String, String> values = new HashMap<>();
    for (int index = 0; index < args.length; index++) {
      String current = args[index];
      if (!current.startsWith("--")) {
        continue;
      }
      String key = current.substring(2);
      String value = index + 1 < args.length ? args[index + 1] : "";
      values.put(key, value);
      index += 1;
    }
    return values;
  }

  private static String required(Map<String, String> params, String key) {
    String value = params.getOrDefault(key, "").trim();
    if (value.isEmpty()) {
      throw new IllegalArgumentException("missing required argument --" + key);
    }
    return value;
  }

  private static String text(JsonNode node, String field) {
    JsonNode value = node.get(field);
    return value == null || value.isNull() ? "" : value.asText("");
  }

  private static int integer(JsonNode node, String field) {
    JsonNode value = node.get(field);
    return value == null || value.isNull() ? 0 : value.asInt(0);
  }

  private static double decimal(JsonNode node, String field) {
    JsonNode value = node.get(field);
    return value == null || value.isNull() ? 0.0D : value.asDouble(0.0D);
  }

  private static double normalizeSentiment(double rating) {
    double normalized = (rating - 3.0D) / 2.0D;
    return Math.max(-1.0D, Math.min(1.0D, normalized));
  }

  public static final class ProjectionProcessFunction
      extends KeyedProcessFunction<String, String, String> {
    private final String failMarkerPath;
    private transient ValueState<ProjectionState> stateHandle;

    ProjectionProcessFunction(String failMarkerPath) {
      this.failMarkerPath = failMarkerPath;
    }

    @Override
    public void open(OpenContext openContext) {
      ValueStateDescriptor<ProjectionState> descriptor =
          new ValueStateDescriptor<>("projection-state", Types.POJO(ProjectionState.class));
      stateHandle = getRuntimeContext().getState(descriptor);
    }

    @Override
    public void processElement(String value, Context context, Collector<String> out) throws Exception {
      JsonNode root = MAPPER.readTree(value);
      String eventType = text(root, "event_type");
      String productId = text(root, "product_id");
      JsonNode payload = root.has("payload") && root.get("payload").isObject() ? root.get("payload") : root;

      ProjectionState current = stateHandle.value();
      if (current == null) {
        current = new ProjectionState();
        current.productId = productId.isBlank() ? context.getCurrentKey() : productId;
      }

      if ("control.fail_once".equals(eventType)) {
        File marker = new File(failMarkerPath);
        if (!marker.exists()) {
          File parent = marker.getParentFile();
          if (parent != null) {
            Files.createDirectories(parent.toPath());
          }
          Files.writeString(marker.toPath(), "triggered", StandardCharsets.UTF_8);
          throw new RuntimeException("intentional checkpoint recovery trigger");
        }
        return;
      }

      if ("inventory.updated".equals(eventType)) {
        int inventoryUnits = integer(payload, "inventory_units");
        if (inventoryUnits <= 0) {
          inventoryUnits = integer(payload, "available_quantity");
        }
        current.inventoryUnits = inventoryUnits;
      } else if ("order.updated".equals(eventType)) {
        current.salesUnits += integer(payload, "units");
      } else if ("review.updated".equals(eventType)) {
        current.reviewCount += 1;
        current.sentimentTotal += normalizeSentiment(decimal(payload, "rating"));
      } else {
        return;
      }

      current.processedEventCount += 1;
      current.lastEventType = eventType;
      current.updatedAt = OffsetDateTime.now(ZoneOffset.UTC).toString();
      stateHandle.update(current);
      out.collect(current.toJson());
    }
  }

  public static final class ProjectionState implements Serializable {
    public String productId = "";
    public int processedEventCount = 0;
    public int salesUnits = 0;
    public int inventoryUnits = 0;
    public int reviewCount = 0;
    public double sentimentTotal = 0.0D;
    public String lastEventType = "";
    public String updatedAt = "";

    public ProjectionState() {}

    public String toJson() throws Exception {
      Map<String, Object> payload = new HashMap<>();
      payload.put("product_id", productId);
      payload.put("processed_event_count", processedEventCount);
      payload.put("sales_units", salesUnits);
      payload.put("inventory_units", inventoryUnits);
      payload.put(
          "demand_supply_ratio",
          inventoryUnits <= 0 ? (double) salesUnits : round((double) salesUnits / (double) inventoryUnits));
      payload.put("review_count", reviewCount);
      payload.put(
          "review_sentiment_score",
          reviewCount <= 0 ? 0.0D : round(sentimentTotal / (double) reviewCount));
      payload.put("last_event_type", lastEventType);
      payload.put("updated_at", updatedAt);
      return MAPPER.writeValueAsString(payload);
    }

    private static double round(double value) {
      return Math.round(value * 10_000.0D) / 10_000.0D;
    }
  }
}

package io.rpi.kafka.sample.producer;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.prometheus.PrometheusConfig;
import io.micrometer.prometheus.PrometheusMeterRegistry;
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.Random;
import java.util.concurrent.Future;
import com.sun.net.httpserver.HttpServer;

/**
 * Minimal Kafka Avro producer.
 *
 * <p>Usage: {@code java -jar kafka-java-producer-template.jar [topic] [schemaName]}</p>
 *
 * <ul>
 *   <li>Serializes {@link GenericRecord}s using Apicurio Avro serializer (ccompat wire format).</li>
 *   <li>Emits an OTel span per {@code send()} call.</li>
 *   <li>Exposes Prometheus metrics on port {@value #METRICS_PORT}.</li>
 * </ul>
 */
public final class ProducerApp {

    private static final Logger LOG = LoggerFactory.getLogger(ProducerApp.class);
    private static final int METRICS_PORT = 9302;

    private ProducerApp() {
    }

    public static void main(String[] args) throws Exception {
        String topic = args.length > 0 ? args[0] : System.getenv().getOrDefault("KAFKA_TOPIC", "market.trade.v1");
        String schemaName = args.length > 1 ? args[1] : System.getenv().getOrDefault("KAFKA_SCHEMA_NAME", "market_trade_v1");

        Properties props = ProducerConfig.forEnvironment();
        KafkaProducer<String, GenericRecord> producer = new KafkaProducer<>(props);

        Tracer tracer = GlobalOpenTelemetry.getTracer("kafka-java-producer");
        PrometheusMeterRegistry registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        Metrics.addRegistry(registry);
        Counter published = registry.counter("kafka_producer_messages_published_total", "topic", topic);
        startMetricsServer(registry);

        Schema schema = loadSchema(schemaName);
        Random random = new Random();

        LOG.info("starting produce loop topic={} schema={}", topic, schemaName);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                producer.flush();
                producer.close();
            } catch (Exception e) {
                LOG.warn("close failed", e);
            }
        }));

        while (!Thread.currentThread().isInterrupted()) {
            Span span = tracer.spanBuilder("kafka.produce").startSpan();
            try (Scope ignored = span.makeCurrent()) {
                GenericRecord record = new GenericData.Record(schema);
                long now = System.nanoTime();
                record.put("ts_ns", now);
                record.put("vt_symbol", pickSymbol(random));
                record.put("price", 100.0 + random.nextDouble() * 400.0);
                record.put("size", 1 + random.nextInt(100));
                record.put("exchange", "NASDAQ");
                record.put("received_ts_ns", now);

                ProducerRecord<String, GenericRecord> pr = new ProducerRecord<>(topic, (String) record.get("vt_symbol"), record);
                Future<RecordMetadata> future = producer.send(pr);
                RecordMetadata meta = future.get();
                span.setAttribute("messaging.destination.partition", meta.partition());
                span.setAttribute("messaging.kafka.offset", meta.offset());
                published.increment();
            } catch (Exception e) {
                LOG.error("produce failed", e);
                span.recordException(e);
            } finally {
                span.end();
            }
            Thread.sleep(100);
        }
    }

    private static String pickSymbol(Random r) {
        String[] symbols = {"AAPL.NASDAQ", "MSFT.NASDAQ", "SPY.NYSE"};
        return symbols[r.nextInt(symbols.length)];
    }

    private static Schema loadSchema(String name) {
        // In production you would resolve the schema from Apicurio; for the template
        // we embed a minimal market_trade_v1 record so the sample runs standalone.
        String schemaJson = "{\"type\":\"record\",\"name\":\"MarketTradeV1\",\"namespace\":\"aqp.streaming.market\","
                + "\"fields\":["
                + "{\"name\":\"ts_ns\",\"type\":\"long\"},"
                + "{\"name\":\"vt_symbol\",\"type\":\"string\"},"
                + "{\"name\":\"price\",\"type\":\"double\"},"
                + "{\"name\":\"size\",\"type\":\"int\"},"
                + "{\"name\":\"exchange\",\"type\":\"string\"},"
                + "{\"name\":\"received_ts_ns\",\"type\":\"long\"}"
                + "]}";
        return new Schema.Parser().parse(schemaJson);
    }

    private static void startMetricsServer(PrometheusMeterRegistry registry) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress(METRICS_PORT), 0);
        server.createContext("/metrics", exchange -> {
            byte[] body = registry.scrape().getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });
        server.setExecutor(null);
        server.start();
        LOG.info("Prometheus metrics on :{}/metrics", METRICS_PORT);
    }
}

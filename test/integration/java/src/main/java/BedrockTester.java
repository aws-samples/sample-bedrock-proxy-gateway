// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.core.SdkBytes;
import java.util.Base64;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeAsyncClient;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;
import software.amazon.awssdk.services.bedrockruntime.model.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import org.springframework.ai.bedrock.converse.BedrockProxyChatModel;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.chat.model.ChatResponse;

/**
 * Integration test for Bedrock Gateway APIs.
 *
 * Tests all supported Bedrock APIs (converse, invoke, streaming variants)
 * using both sync and async clients.
 *
 * Requires:
 *   - .env file with ENVIRONMENT, CLIENT_ID, CLIENT_SECRET environment variables
 *   - config.json beside the JAR with api_url/auth_url per environment
 *   - client.p12 keystore file for mTLS
 */
public class BedrockTester {

    /* ========== CONFIG / BOILERPLATE ========== */

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Path CONFIG_JSON = Path.of("../config.json");
    private static final Path CLIENT_KEYSTORE = Path.of("client.p12");
    private static final String KEYSTORE_PASSWORD = "";        // Default keystore password

    private final BedrockClient bedrockClient;
    // Make these package-private so they can be accessed by the shutdown method
    final BedrockRuntimeClient brSync;
    final BedrockRuntimeAsyncClient brAsync;
    private final List<String> inferenceModels;
    private final List<String> embeddingModels;
    private final List<String> imageSearchModels;

    /* ========== CTOR builds everything once ========== */
    public BedrockTester() throws Exception {
        // Load configuration
        var cfg = MAPPER.readTree(Files.readAllBytes(CONFIG_JSON));
        String env = System.getenv().getOrDefault("ENVIRONMENT", "local");
        String apiUrl = cfg.path("environments").path(env).path("api_url").asText();
        String authUrl = cfg.path("environments").path(env).path("auth_url").asText();

        // Load inference and embedding models separately
        this.inferenceModels = new ArrayList<>();
        this.embeddingModels = new ArrayList<>();
        var javaModels = cfg.path("models").path("java");
        javaModels.path("inference").forEach(n -> inferenceModels.add(n.asText()));
        javaModels.path("embedding").forEach(n -> embeddingModels.add(n.asText()));

        // Load image vision capable models
        this.imageSearchModels = new ArrayList<>();
        cfg.path("model_capabilities").path("image_vision").forEach(n -> imageSearchModels.add(n.asText()));

        // Create BedrockClient with mTLS
        this.bedrockClient = new BedrockClient(
                requiredEnv("CLIENT_ID"),
                requiredEnv("CLIENT_SECRET"),
                CLIENT_KEYSTORE,
                KEYSTORE_PASSWORD,
                "us-east-1",
                apiUrl,
                authUrl);

        // Get sync and async clients
        this.brSync = bedrockClient.getBedrockClient();
        this.brAsync = bedrockClient.getBedrockAsyncClient();
    }

    /* ========= UTILS ========= */

    private static String requiredEnv(String key) {
        String v = System.getenv(key);
        if (v == null || v.isBlank())
            throw new IllegalStateException("Missing env var: " + key);
        return v;
    }

    /* ========== TEST DRIVERS ========== */

    private boolean testInvoke(String modelId) {
        try {
            Map<String,Object> body = promptBody(modelId);
            InvokeModelRequest req = InvokeModelRequest.builder()
                    .modelId(modelId)
                    .contentType("application/json")
                    .accept("application/json")
                    .body(SdkBytes.fromUtf8String(MAPPER.writeValueAsString(body)))
                    .build();
            InvokeModelResponse resp = brSync.invokeModel(req);
            String responseText = new String(resp.body().asByteArray());
            System.out.printf(responseText);
            System.out.printf("  ↳ invoke OK (%d bytes)%n", resp.body().asByteArray().length);
            return true;
        } catch (Exception e) {
            System.err.println("  ↳ invoke FAILED: " + e.getMessage());
            return false;
        }
    }

    private boolean testInvokeStream(String modelId) {
        try {
            Map<String,Object> body = promptBody(modelId);
            InvokeModelWithResponseStreamRequest req =
                    InvokeModelWithResponseStreamRequest.builder()
                            .modelId(modelId)
                            .contentType("application/json")
                            .accept("*/*") // get whatever the model returns
                            .body(SdkBytes.fromUtf8String(MAPPER.writeValueAsString(body)))
                            .build();

            InvokeModelWithResponseStreamResponseHandler handler =
                    InvokeModelWithResponseStreamResponseHandler.builder()
                            .onEventStream(p -> p.subscribe(event -> {
                                if (event instanceof PayloadPart) {
                                    byte[] b = ((PayloadPart)event).bytes().asByteArray();
                                    System.out.print(new String(b));
                                }
                            }))
                            .onError(t -> System.err.println("  ↳ stream ERROR: " + t.getMessage()))
                            .build();

            brAsync.invokeModelWithResponseStream(req, handler).get();
            System.out.println();
            return true;
        } catch (Exception e) {
            System.err.println("  ↳ stream FAILED: " + e.getMessage());
            return false;
        }
    }

    private boolean testConverse(String modelId) {
        try {
            Message user = Message.builder()
                    .role(ConversationRole.USER)
                    .content(ContentBlock.fromText("Say hello"))
                    .build();
            ConverseRequest req = ConverseRequest.builder()
                    .modelId(modelId)
                    .messages(user)
                    .inferenceConfig(InferenceConfiguration.builder().maxTokens(32).temperature(0.5f).build())
                    .build();
            ConverseResponse resp = brSync.converse(req);
            String text = resp.output().message().content().get(0).text();
            System.out.println("  ↳ converse: " + text);
            return true;
        } catch (Exception e) {
            System.err.println("  ↳ converse FAILED: " + e.getMessage());
            return false;
        }
    }

    private boolean testConverseStream(String modelId) {
        try {
            Message user = Message.builder()
                    .role(ConversationRole.USER)
                    .content(ContentBlock.fromText("Describe mTLS in one sentence"))
                    .build();
            ConverseStreamRequest req = ConverseStreamRequest.builder()
                    .modelId(modelId)
                    .messages(user)
                    .inferenceConfig(InferenceConfiguration.builder().maxTokens(64).temperature(0.7f).build())
                    .build();

            ConverseStreamResponseHandler handler = ConverseStreamResponseHandler.builder()
                    .subscriber(ConverseStreamResponseHandler.Visitor.builder()
                            .onContentBlockDelta(chunk -> System.out.print(chunk.delta().text()))
                            .onMessageStop(stop -> System.out.println("\n  ↳ stop: " + stop.stopReason()))
                            .build())
                    .onError(err -> System.err.println("  ↳ converseStream ERROR: " + err.getMessage()))
                    .build();

            brAsync.converseStream(req, handler).get();
            return true;
        } catch (Exception e) {
            System.err.println("  ↳ converseStream FAILED: " + e.getMessage());
            return false;
        }
    }

    private boolean testImageVision(String modelId) {
        try {
            if (!imageSearchModels.contains(modelId)) {
                System.out.println("  ↳ imageSearch SKIP - Not supported for " + modelId);
                return false;
            }

            // Create a 100x100 light blue image with a red circle (matching Python logic)
            byte[] imageBytes = createTestImage();

            Message user = Message.builder()
                    .role(ConversationRole.USER)
                    .content(
                        ContentBlock.fromText("Describe this image briefly."),
                        ContentBlock.fromImage(ImageBlock.builder()
                            .format(ImageFormat.PNG)
                            .source(ImageSource.fromBytes(SdkBytes.fromByteArray(imageBytes)))
                            .build())
                    )
                    .build();

            ConverseRequest req = ConverseRequest.builder()
                    .modelId(modelId)
                    .messages(user)
                    .inferenceConfig(InferenceConfiguration.builder().maxTokens(100).build())
                    .build();

            ConverseResponse resp = brSync.converse(req);
            String text = resp.output().message().content().get(0).text();
            System.out.println("  ↳ imageSearch: " + text.substring(0, Math.min(50, text.length())) + "...");
            return true;
        } catch (Exception e) {
            System.err.println("  ↳ imageSearch FAILED: " + e.getMessage());
            return false;
        }
    }

    private byte[] createTestImage() throws Exception {
        // Create 100x100 light blue image with red circle (matching Python main.py)
        int width = 100, height = 100;
        int[] pixels = new int[width * height];

        // Fill with light blue background (RGB: 173, 216, 230)
        int lightBlue = (255 << 24) | (173 << 16) | (216 << 8) | 230;
        java.util.Arrays.fill(pixels, lightBlue);

        // Draw red circle in center (RGB: 255, 100, 100)
        int red = (255 << 24) | (255 << 16) | (100 << 8) | 100;
        int centerX = 50, centerY = 50, radius = 25;

        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int dx = x - centerX;
                int dy = y - centerY;
                if (dx * dx + dy * dy <= radius * radius) {
                    pixels[y * width + x] = red;
                }
            }
        }

        // Convert to PNG bytes
        java.awt.image.BufferedImage image = new java.awt.image.BufferedImage(width, height, java.awt.image.BufferedImage.TYPE_INT_ARGB);
        image.setRGB(0, 0, width, height, pixels, 0, width);

        java.io.ByteArrayOutputStream baos = new java.io.ByteArrayOutputStream();
        javax.imageio.ImageIO.write(image, "PNG", baos);
        return baos.toByteArray();
    }

    private boolean testReasoning(String modelId) {
        try {
            Message user = Message.builder()
                    .role(ConversationRole.USER)
                    .content(ContentBlock.fromText("Solve: If a train travels 120 miles in 2 hours, what is its average speed?"))
                    .build();
            ConverseRequest req = ConverseRequest.builder()
                    .modelId(modelId)
                    .messages(user)
                    .inferenceConfig(InferenceConfiguration.builder().maxTokens(200).temperature(0.3f).build())
                    .build();
            ConverseResponse resp = brSync.converse(req);
            String text = resp.output().message().content().get(0).text();
            System.out.println("  ↳ reasoning: " + text.substring(0, Math.min(50, text.length())) + "...");
            return true;
        } catch (Exception e) {
            System.err.println("  ↳ reasoning FAILED: " + e.getMessage());
            return false;
        }
    }

    private boolean testSpringAI(String modelId) {
        try {
            BedrockProxyChatModel chatModel = BedrockProxyChatModel.builder()
                    .bedrockRuntimeClient(brSync)
                    .bedrockRuntimeAsyncClient(brAsync)
                    .build();

            ChatOptions options = ChatOptions.builder()
                    .model(modelId)
                    .build();

            Prompt prompt = new Prompt("Can you name a few colours?", options);
            ChatResponse response = chatModel.call(prompt);
            String text = response.getResult().getOutput().getText();

            System.out.println("  ↳ spring-ai: " + text.substring(0, Math.min(50, text.length())) + "...");
            return true;
        } catch (Exception e) {
            System.err.println("  ↳ spring-ai FAILED: " + e.getMessage());
            return false;
        }
    }

    private boolean testEmbedding(String modelId) {
        try {
            Map<String,Object> body = new LinkedHashMap<>();
            if (modelId.contains("cohere")) {
                body.put("texts", List.of("Test embedding"));
                body.put("input_type", "search_document");
            } else if (modelId.contains("titan")) {
                body.put("inputText", "Test embedding");
            } else {
                body.put("inputText", "Test embedding");
                body.put("dimensions", 256);
            }

            InvokeModelRequest req = InvokeModelRequest.builder()
                    .modelId(modelId)
                    .contentType("application/json")
                    .accept("application/json")
                    .body(SdkBytes.fromUtf8String(MAPPER.writeValueAsString(body)))
                    .build();
            InvokeModelResponse resp = brSync.invokeModel(req);
            String responseText = new String(resp.body().asByteArray());

            if (responseText.contains("embedding") || responseText.contains("embeddings")) {
                System.out.println("  ↳ embedding OK");
                return true;
            } else {
                System.err.println("  ↳ embedding FAILED: No embedding in response");
                return false;
            }
        } catch (Exception e) {
            System.err.println("  ↳ embedding FAILED: " + e.getMessage());
            return false;
        }
    }

    /* ===== Test Result Class ===== */
    private static class TestResult {
        final String modelId;
        final String modelType;
        final Map<String, Boolean> results = new LinkedHashMap<>();

        TestResult(String modelId, String modelType) {
            this.modelId = modelId;
            this.modelType = modelType;

            if ("inference".equals(modelType)) {
                results.put("invoke", false);
                results.put("invoke_stream", false);
                results.put("converse", false);
                results.put("converse_stream", false);
                results.put("image_vision", false);
                results.put("reasoning", false);
                results.put("spring-ai", false);
            } else if ("embedding".equals(modelType)) {
                results.put("embedding", false);
            }
        }

        void setResult(String testType, boolean success) {
            results.put(testType, success);
        }

        boolean isSuccess() {
            return results.values().stream().allMatch(v -> v);
        }

        int getPassedCount() {
            return (int) results.values().stream().filter(v -> v).count();
        }

        int getTotalCount() {
            return results.size();
        }
    }

    /* ===== Main CLI ===== */
    public static void main(String[] args) throws Exception {
        BedrockTester t = new BedrockTester();
        List<TestResult> testResults = new ArrayList<>();
        int totalTests = 0;
        int passedTests = 0;

        try {
            // Test inference models
            for (String modelId : t.inferenceModels) {
                System.out.println("▶ Testing inference model: " + modelId);
                TestResult result = new TestResult(modelId, "inference");

                result.setResult("invoke", t.testInvoke(modelId));
                result.setResult("invoke_stream", t.testInvokeStream(modelId));
                result.setResult("converse", t.testConverse(modelId));
                result.setResult("converse_stream", t.testConverseStream(modelId));
                result.setResult("image_vision", t.testImageVision(modelId));
                result.setResult("reasoning", t.testReasoning(modelId));
                result.setResult("spring-ai", t.testSpringAI(modelId));

                testResults.add(result);
                totalTests += result.getTotalCount();
                passedTests += result.getPassedCount();
                System.out.println();
            }

            // Test embedding models
            for (String modelId : t.embeddingModels) {
                System.out.println("▶ Testing embedding model: " + modelId);
                TestResult result = new TestResult(modelId, "embedding");

                result.setResult("embedding", t.testEmbedding(modelId));

                testResults.add(result);
                totalTests += result.getTotalCount();
                passedTests += result.getPassedCount();
                System.out.println();
            }

            // Print summary table
            printResultsTable(testResults);

            // Print overall summary
            System.out.printf("Summary: %d/%d tests passed%n", passedTests, totalTests);

            // Exit with appropriate code
            if (passedTests < totalTests) System.exit(1);
        } finally {
            // Properly close AWS SDK clients to avoid thread lingering warnings
            shutdownClients(t);
        }
    }

    /**
     * Properly shutdown AWS SDK clients to prevent thread lingering warnings
     */
    private static void shutdownClients(BedrockTester tester) {
        try {
            // Close the sync client
            if (tester.brSync != null) {
                tester.brSync.close();
            }

            // Close the async client
            if (tester.brAsync != null) {
                tester.brAsync.close();
            }

            // Add a small delay to allow threads to terminate
            try {
                TimeUnit.SECONDS.sleep(1);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }

            // Force JVM to run garbage collection
            System.gc();

            // Add another small delay
            try {
                TimeUnit.SECONDS.sleep(1);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        } catch (Exception e) {
            System.err.println("Warning: Error during client shutdown: " + e.getMessage());
        }
    }

    /* ===== Results Table Formatter ===== */
    private static void printResultsTable(List<TestResult> results) {
        System.out.println("\n" + "=".repeat(110));
        System.out.println("☕ JAVA INTEGRATION TEST RESULTS");
        System.out.println("=".repeat(110));

        // Print header
        System.out.printf("%-35s | %-10s | %-50s | %-8s%n",
                "Model ID", "Type", "Tests", "Status");
        System.out.println("-".repeat(110));

        // Print each model's results
        for (TestResult result : results) {
            StringBuilder testsStr = new StringBuilder();
            for (Map.Entry<String, Boolean> entry : result.results.entrySet()) {
                if (testsStr.length() > 0) testsStr.append(", ");
                testsStr.append(entry.getKey()).append(":").append(formatStatus(entry.getValue()));
            }

            System.out.printf("%-35s | %-10s | %-50s | %-8s%n",
                    result.modelId,
                    result.modelType,
                    testsStr.toString(),
                    result.isSuccess() ? "✅ PASS" : "❌ FAIL");
        }

        System.out.println("=".repeat(80));

        // Print statistics
        int totalModels = results.size();
        int successfulModels = (int) results.stream().filter(TestResult::isSuccess).count();
        System.out.printf("📊 Models Tested: %d%n", totalModels);
        System.out.printf("✅ Successful Models: %d%n", successfulModels);

        int totalTests = results.stream().mapToInt(TestResult::getTotalCount).sum();
        int passedTests = results.stream().mapToInt(TestResult::getPassedCount).sum();
        System.out.printf("🧪 Total API Tests: %d%n", totalTests);
        System.out.printf("🎯 Successful Tests: %d%n", passedTests);

        double successRate = totalTests > 0 ? (passedTests * 100.0 / totalTests) : 0;
        System.out.printf("📈 Success Rate: %.1f%%%n", successRate);
        System.out.println("=".repeat(110));
    }

    private static String formatStatus(boolean success) {
        return success ? "✅" : "❌";
    }

    /* ====== Small helpers ===== */

    private static Map<String,Object> promptBody(String modelId) {
        Map<String,Object> body = new LinkedHashMap<>();
        if (modelId.startsWith("anthropic")) {
            body.put("anthropic_version","bedrock-2023-05-31");
            body.put("max_tokens",64);
            body.put("messages", List.of(Map.of("role","user","content","Hello")));
        } else if (modelId.contains("nova")) {
            body.put("messages", List.of(Map.of("role","user","content",List.of(Map.of("text","Hello")))));
            body.put("inferenceConfig", Map.of("max_new_tokens", 64));
        } else if (modelId.contains("llama")) {
            body.put("prompt","Hello");
            body.put("max_gen_len",64);
            body.put("temperature",0.1);
        } else if (modelId.contains("mistral")) {
            body.put("prompt","Hello");
            body.put("max_tokens",64);
            body.put("temperature",0.1);
        } else if (modelId.contains("cohere")) {
            body.put("message","Hello");
            body.put("max_tokens",64);
        } else if (modelId.contains("ai21")) {
            body.put("messages", List.of(Map.of("role","user","content","Hello")));
            body.put("max_tokens",64);
        } else {
            body.put("prompt","Hello");
            body.put("max_tokens",64);
        }
        return body;
    }
}

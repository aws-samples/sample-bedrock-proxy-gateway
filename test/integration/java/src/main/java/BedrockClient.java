import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.auth.credentials.AnonymousCredentialsProvider;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.core.interceptor.Context;
import software.amazon.awssdk.core.interceptor.ExecutionAttributes;
import software.amazon.awssdk.core.interceptor.ExecutionInterceptor;
import software.amazon.awssdk.http.FileStoreTlsKeyManagersProvider;
import software.amazon.awssdk.http.SdkHttpRequest;
import software.amazon.awssdk.http.SdkHttpClient;
import software.amazon.awssdk.http.apache.ApacheHttpClient;
import software.amazon.awssdk.http.async.SdkAsyncHttpClient;
import software.amazon.awssdk.http.nio.netty.NettyNioAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeAsyncClient;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.locks.ReentrantLock;
import java.util.logging.Logger;

/**
 * Gateway client for Bedrock API with authentication and mTLS support.
 */
public class BedrockClient {
    private static final Logger logger = Logger.getLogger(BedrockClient.class.getName());
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final String clientId;
    private final String clientSecret;
    private final Path mtlsKeystorePath;
    private final String mtlsKeystorePassword;
    private final String region;
    private final String bedrockRuntimeEndpointUrl;
    private final String oauthTokenUrl;

    // Private variables
    private final TokenManager tokenManager;
    private final BedrockRuntimeClient bedrockClient;
    private final BedrockRuntimeAsyncClient bedrockAsyncClient;

    /**
     * Creates a new Bedrock Gateway client with authentication and mTLS support.
     *
     * @param clientId Client ID for authentication
     * @param clientSecret Client secret for authentication
     * @param mtlsKeystorePath Path to PKCS12 keystore file (optional)
     * @param mtlsKeystorePassword Password for the keystore (optional)
     * @param region AWS region
     * @param bedrockRuntimeEndpointUrl Custom Bedrock endpoint URL
     * @param oauthTokenUrl OAuth token endpoint URL
     */
    public BedrockClient(
            String clientId,
            String clientSecret,
            Path mtlsKeystorePath,
            String mtlsKeystorePassword,
            String region,
            String bedrockRuntimeEndpointUrl,
            String oauthTokenUrl) {

        this.clientId = clientId;
        this.clientSecret = clientSecret;
        this.mtlsKeystorePath = mtlsKeystorePath;
        this.mtlsKeystorePassword = mtlsKeystorePassword;
        this.region = region != null ? region : "us-east-1";
        this.bedrockRuntimeEndpointUrl = bedrockRuntimeEndpointUrl;
        this.oauthTokenUrl = oauthTokenUrl;

        // Add logging for endpoints and mTLS parameters
        logger.info("Initializing Bedrock client with configuration:");
        logger.info("OAuth Token URL: " + this.oauthTokenUrl);
        logger.info("Bedrock Runtime Endpoint: " + this.bedrockRuntimeEndpointUrl);
        logger.info("AWS Region: " + this.region);
        logger.info("Client ID: " + this.clientId.substring(0, Math.min(8, this.clientId.length())) + "...");

        if (this.mtlsKeystorePath != null) {
            logger.info("mTLS Keystore Path: " + this.mtlsKeystorePath);
            logger.info("mTLS Keystore Type: PKCS12");
            logger.info("mTLS Keystore Password Length: " + (this.mtlsKeystorePassword != null ? this.mtlsKeystorePassword.length() : 0));
        } else {
            logger.info("mTLS not configured - no keystore provided");
        }
        // Initialize token manager
        this.tokenManager = new TokenManager(
                this.oauthTokenUrl,
                this.clientId,
                this.clientSecret,
                120); // 2 minute buffer before token refresh

        // Configure client with auth interceptor
        ClientOverrideConfiguration overrideConfig = ClientOverrideConfiguration.builder()
                .addExecutionInterceptor(new AuthInterceptor(tokenManager))
                .apiCallTimeout(Duration.ofSeconds(60))
                .build();

        // Create mTLS key manager provider if keystore is provided
        FileStoreTlsKeyManagersProvider keyManagersProvider = null;
        if (this.mtlsKeystorePath != null && this.mtlsKeystorePassword != null) {
            keyManagersProvider = FileStoreTlsKeyManagersProvider.create(
                    this.mtlsKeystorePath,
                    "PKCS12",
                    this.mtlsKeystorePassword
            );
            logger.info("Created mTLS key manager provider using PKCS12 keystore");
        }

        // 3. Build the Apache HTTP client with mTLS configured
        SdkHttpClient httpClient = ApacheHttpClient.builder()
                .tlsKeyManagersProvider(keyManagersProvider)
                .socketTimeout(Duration.ofSeconds(30))
                .connectionTimeout(Duration.ofSeconds(10))
                .build();

        // Build the async Netty HTTP client with mTLS configured
        SdkAsyncHttpClient asyncHttpClient = NettyNioAsyncHttpClient.builder()
                .tlsKeyManagersProvider(keyManagersProvider)
                .connectionTimeout(Duration.ofSeconds(10))
                .connectionAcquisitionTimeout(Duration.ofSeconds(30))
                .build();

        // Build synchronous client
        this.bedrockClient = BedrockRuntimeClient.builder()
                .region(Region.of(this.region))
                .endpointOverride(URI.create(this.bedrockRuntimeEndpointUrl))
                .httpClient(httpClient)
                /* .httpClient(UrlConnectionHttpClient.builder()
                        .tlsKeyManagersProvider(keyManagersProvider)
                        .connectionTimeout(Duration.ofSeconds(30))
                        .build()) */
                .overrideConfiguration(overrideConfig)
                .credentialsProvider(AnonymousCredentialsProvider.create())
                .build();

        // Build asynchronous client for streaming APIs
        this.bedrockAsyncClient = BedrockRuntimeAsyncClient.builder()
                .region(Region.of(this.region))
                .endpointOverride(URI.create(this.bedrockRuntimeEndpointUrl))
                .httpClient(asyncHttpClient)
                .overrideConfiguration(overrideConfig)
                .credentialsProvider(AnonymousCredentialsProvider.create())
                .build();

        logger.info("Bedrock client created and configured");
        logger.info("API URL: " + this.bedrockRuntimeEndpointUrl);
        logger.info("AWS Region: " + this.region);
    }

    /**
     * Gets the synchronous Bedrock client.
     *
     * @return Configured BedrockRuntimeClient
     */
    public BedrockRuntimeClient getBedrockClient() {
        return bedrockClient;
    }

    /**
     * Gets the asynchronous Bedrock client for streaming operations.
     *
     * @return Configured BedrockRuntimeAsyncClient
     */
    public BedrockRuntimeAsyncClient getBedrockAsyncClient() {
        return bedrockAsyncClient;
    }

    /**
     * Shuts down the HTTP clients to prevent thread leaks.
     */
    public void shutdown() {
        try {
            if (bedrockClient != null) {
                bedrockClient.close();
            }
            if (bedrockAsyncClient != null) {
                bedrockAsyncClient.close();
            }
        } catch (Exception e) {
            // Ignore shutdown errors
        }
    }

    /**
     * Gets the current authentication token.
     *
     * @return Current bearer token
     */
    public String getToken() {
        return tokenManager.getToken();
    }

    /**
     * Manages OAuth2 token lifecycle with automatic refresh.
     */
    private static class TokenManager {
        private final String tokenUrl;
        private final String clientId;
        private final String clientSecret;
        private final int bufferSeconds;
        private final HttpClient httpClient = HttpClient.newBuilder().build();
        private final ReentrantLock lock = new ReentrantLock();

        private String token = "";
        private Instant expiry = Instant.EPOCH;

        /**
         * Creates a new token manager.
         *
         * @param tokenUrl OAuth2 token endpoint URL
         * @param clientId Client ID
         * @param clientSecret Client secret
         * @param bufferSeconds Buffer time in seconds before token expiry to refresh
         */
        TokenManager(String tokenUrl, String clientId, String clientSecret, int bufferSeconds) {
            this.tokenUrl = tokenUrl;
            this.clientId = clientId;
            this.clientSecret = clientSecret;
            this.bufferSeconds = bufferSeconds;
        }

        /**
         * Gets a valid token, refreshing if necessary.
         *
         * @return Valid bearer token
         */
        public String getToken() {
            lock.lock();
            try {
                Instant now = Instant.now();
                Instant refreshTime = expiry.minusSeconds(bufferSeconds);
                logger.fine("Current time: " + now + ", Token expires: " + expiry + ", Refresh at: " + refreshTime);

                if (now.isAfter(refreshTime)) {
                    logger.fine("Token needs refresh");
                    fetchToken();
                } else {
                    logger.fine("Using existing token");
                }
                return token;
            } catch (Exception e) {
                logger.severe("Token fetch failed: " + e.getMessage());
                throw new RuntimeException("Failed to fetch JWT token: " + e, e);
            } finally {
                lock.unlock();
            }
        }

        /**
         * Fetches a new token from the OAuth authorization server.
         */
        private void fetchToken() {
            try {
                logger.info("Fetching token from: " + tokenUrl);
                logger.info("Client ID: " + clientId.substring(0, Math.min(8, clientId.length())) + "...");

                String payload = String.format(
                        "client_id=%s&client_secret=%s&grant_type=client_credentials",
                        clientId, clientSecret);

                HttpRequest request = HttpRequest.newBuilder(URI.create(tokenUrl))
                        .header("Content-Type", "application/x-www-form-urlencoded")
                        .POST(HttpRequest.BodyPublishers.ofString(payload))
                        .build();

                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                logger.info("Token response status: " + response.statusCode());

                if (response.statusCode() != 200) {
                    throw new IOException("OAuth token request failed: " + response.statusCode());
                }

                JsonNode data = MAPPER.readTree(response.body());
                token = data.path("access_token").asText();
                int expiresIn = data.path("expires_in").asInt(3600); // Default 1 hour
                expiry = Instant.now().plusSeconds(expiresIn);

                logger.info("Token expires in " + expiresIn + " seconds");
                logger.info("Token prefix: " + token.substring(0, Math.min(20, token.length())) + "...");
            } catch (Exception e) {
                logger.severe("Token fetch failed: " + e.getMessage());
                throw new RuntimeException("Failed to fetch OAuth token", e);
            }
        }
    }

    /**
     * Interceptor that adds the Authorization header to all requests.
     */
    private static class AuthInterceptor implements ExecutionInterceptor {
        private final TokenManager tokenManager;

        AuthInterceptor(TokenManager tokenManager) {
            this.tokenManager = tokenManager;
        }

        @Override
        public SdkHttpRequest modifyHttpRequest(Context.ModifyHttpRequest context, ExecutionAttributes executionAttributes) {
            String token = tokenManager.getToken();
            logger.fine("Adding Authorization header: " + token.substring(0, Math.min(30, token.length())) + "...");
            return context.httpRequest().toBuilder()
                    .putHeader("Authorization", "Bearer " + token)
                    .build();
        }
    }
}

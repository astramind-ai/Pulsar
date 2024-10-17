# 🚀 Pulsar OpenAI-Compatible Endpoints

## 📡 API Compatibility
Pulsar offers a subset of endpoints that are fully compatible with the OpenAI protocol, allowing for a replacement of OpenAI services.

### Compatible Endpoints:
- `/v1/chat/completions`
- `/v1/embeddings`
- `/tokenize`
- `/detokenize`

### Additional Features:
You can use these endpoints in combination with:
- `/model/load` to switch models
- `/lora/load` and `/lora/unload` to manage LoRA adapters

After loading a new model or LoRA, you can use its name in your requests to the compatible endpoints.

## 🔐 Authentication for OpenAI-Compatible Endpoints

By default:
- The server generates a new token for each session.
- It only accepts unauthorized requests from the same network for security.

## 🛠️ Proper Authentication Setup

1. Go to the config folder (where the `.env` file is located)
2. Send request to `/users/list` i.e. `curl -X GET "http://localhost:40000/users/list" -H "accept: application/json"`
3. Choose a user from the list and send a request to `/users/login` with the .env LOCAL_TOKEN as the bearer token. `curl -X POST "http://localhost:40000/token" -H "accept: application/json" -H "Authorization: Bearer [LOCAL_TOKEN]"`
3. Get the token from the response
4. Use this token in your requests:
   - Include it in the header for HTTP requests
   - Or in the client configuration if using the OpenAI SDK

## 🚫 Disabling Authentication (Use with Caution)

You can disable authentication for local requests by setting `allow_unsafe_local_requests` to `true` in the config file.

### Config File Location
Edit the `last.yaml` configuration file, typically found at:

- 🐧 Linux/Mac: `~/pulsar/configs`
- 🪟 Windows: `%userprofile%\pulsar\configs`

## ⚠️ Security Note
Disabling authentication may pose security risks. Only use this option in secure, controlled environments.

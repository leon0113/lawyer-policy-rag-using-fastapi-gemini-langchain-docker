# LLM API for RAG: Tokens.bd

## Scope

- Embeddings: keep using the existing Hugging Face embedding model. Do NOT change it.
  Tokens.bd has no embedding models on our plan.
- Generation: use the Tokens.bd API only to answer the user's question from the
  retrieved chunks.

## Flow

1. User question → embed with the SAME Hugging Face model used for indexing
2. Vector search → top-k chunks (start with k=4)
3. Build a prompt from the chunks + question → send to Tokens.bd
4. Return `choices[0].message.content` to the user

## API basics

- OpenAI-compatible API. Use the official `openai` SDK and change only the base URL.
- Base URL: `https://tokens.bd/v1`
- Endpoint: `POST /chat/completions`
- Auth header: `Authorization: Bearer <TOKENS_API_KEY>`
- Call the API from the server/backend only. It has no CORS, and the key must never reach the browser.

## Environment variables (.env, never hardcode)

TOKENS_API_KEY=tok_live_xxx
TOKENS_BASE_URL=https://tokens.bd/v1
CHAT_MODEL=deepseek-ai/deepseek-v4.1-flash-1017

Other models that work on this key: `claude-haiku-5-5` (fast, no reasoning),
`z-ai/glm-5.3-flash` (thinks a lot, slow).
Model IDs can change. The valid list comes from `GET /v1/models`.
Do NOT use `openai/gpt-5.6-sol` (very expensive) or `qwen/qwen-3.7-flash` (broken pricing).

## Request

{
"model": "<CHAT_MODEL>",
"messages": [
{ "role": "system", "content": "Answer ONLY from the provided context. If the answer is not in the context, say \"I don't know based on the documents.\" Keep answers concise." },
{ "role": "user", "content": "Context:\n[1] <chunk 1>\n[2] <chunk 2>\n\nQuestion: <user question>" }
],
"max_tokens": 1500,
"temperature": 0.2
}

## Response

Read `choices[0].message.content`.
Ignore `reasoning_content` / `reasoning` (the model's thinking, never shown to the user).
Log `usage` (prompt_tokens, completion_tokens) for cost tracking.

## Gotchas (important)

- Reasoning models count their thinking toward `max_tokens`. If `max_tokens` is low,
  `content` comes back `null` with `finish_reason: "length"`. Keep max_tokens >= 1000
  and treat null content + "length" as an error.
- Always send `Content-Type: application/json`.
- Branch on `error.code`, never on the error message.

## Errors

- 401 invalid/missing key → check env, don't retry
- 402 insufficient_credits → don't retry
- 403 model_not_allowed_on_key / 404 model_not_found → wrong model ID
- 429 rate_limited / concurrency_limit → retry after `Retry-After`
- 429 window_exhausted / model_limit_reached → plan limit hit, do NOT retry in a loop
- 5xx → retry with exponential backoff (max 3-4 attempts)
  The SDK already retries (maxRetries=2). Don't add a second retry loop on top.
  Log the `x-tokens-request-id` response header on errors.

## Minimal code

Python:
from openai import OpenAI
import os
client = OpenAI(base_url=os.environ["TOKENS_BASE_URL"], api_key=os.environ["TOKENS_API_KEY"])
res = client.chat.completions.create(model=os.environ["CHAT_MODEL"], messages=messages, max_tokens=1500, temperature=0.2)
c = res.choices[0]
if not c.message.content and c.finish_reason == "length":
raise RuntimeError("max_tokens too low (model spent it on reasoning)")
answer = c.message.content

TypeScript:
import OpenAI from "openai";
const client = new OpenAI({ baseURL: process.env.TOKENS_BASE_URL, apiKey: process.env.TOKENS_API_KEY });
const res = await client.chat.completions.create({ model: process.env.CHAT_MODEL!, messages, max_tokens: 1500, temperature: 0.2 });
const answer = res.choices[0].message.content ?? "";

## Acceptance check

A simple question that IS answered by the docs returns a grounded answer.
A question that is NOT in the docs returns "I don't know based on the documents."

## For this project we will use

```
{
"id": "google/gemini-3.8-flash",
"object": "model",
"created": 1791021861,
"owned_by": "tokens",
"permission": [],
"root": "google/gemini-3.8-flash",
"parent": null,
"name": "Gemini 3.8 Flash",
"context_length": 1000000,
"pricing": {
"input": 1.5,
"output": 7.5,
"cache_read": 0.2,
"cache_write": 0.2
},
"pricing_bdt": {
"input": 187.5,
"output": 937.5
}
},
```

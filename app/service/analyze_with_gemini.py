import json
import re
from openai import AsyncOpenAI
from config import TOKENS_API_KEY, TOKENS_BASE_URL, CHAT_MODEL
from service.prompt import CONTRACT_ANALYSIS_PROMPT
from models import AnalysisResult, ClauseAnalysis, RiskFlag

# Tokens.bd is OpenAI-compatible. The SDK already retries (max_retries=2),
# so don't add another retry loop on top.
client = AsyncOpenAI(
    base_url=TOKENS_BASE_URL,
    api_key=TOKENS_API_KEY or "missing",
    timeout=180.0,
)


def _extract_json(raw_text: str) -> dict:
    """Parse the model output as JSON, tolerating ```json fences or extra text around it."""
    raw_text = raw_text.strip()
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text).strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(raw_text[start:end + 1])


async def analyze_contract(contract_id: str, text_content: str):
    prompt = CONTRACT_ANALYSIS_PROMPT.format(contract_text=text_content[:15000])

    response = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16000,  # reasoning models spend part of this on thinking before the JSON answer
        temperature=0.2,
    )

    choice = response.choices[0]
    if not choice.message.content:
        # Reasoning models can spend the whole max_tokens budget on thinking.
        raise RuntimeError(f"Empty response from model (finish_reason={choice.finish_reason})")

    if response.usage:
        print(f"Tokens usage: prompt={response.usage.prompt_tokens} completion={response.usage.completion_tokens}")

    analysis_data = _extract_json(choice.message.content)

    key_clauses = [
        ClauseAnalysis(**clause)
        for clause in analysis_data.get("key_clauses", [])
    ]

    risk_flags = [
        RiskFlag(**risk)
        for risk in analysis_data.get("risk_flags", [])
    ]

    result = AnalysisResult(
        contract_id=contract_id,
        summary=analysis_data.get("summary", ""),
        contract_type=analysis_data.get("contract_type", "Unknown"),
        key_clauses=key_clauses,
        risk_flags=risk_flags,
        overall_risk_level=analysis_data.get("overall_risk_level", "low"),
        recommendations=analysis_data.get("recommendations", []),
    )
    return result

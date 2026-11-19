# Prompts for the contract AI.
# All prompts are filled with str.format(), so literal JSON braces are written as {{ }}.
# Field names in the CONTRACT_ANALYSIS_PROMPT JSON must match models.py
# (ClauseAnalysis, RiskFlag, AnalysisResult).

CONTRACT_ANALYSIS_PROMPT = """
You are an experienced contract lawyer reviewing a contract for a business reader who is not a lawyer.
Do not assume any particular country or legal system. Work out the governing law and jurisdiction ONLY
from what the contract itself says, and if it does not say, report that as a gap.

Analyze the contract text below and give a clear, practical, structured review.

CONTRACT TEXT:
{contract_text}

Return a JSON object with exactly this structure:
{{
    "summary": "2-3 sentences: what the contract is, who the parties are, the main obligations and the value or duration",
    "contract_type": "The type of contract (e.g. NDA, Service Agreement, Employment Contract, Lease)",
    "key_clauses": [
        {{
            "clause_title": "Name of the clause",
            "clause_text": "The clause text copied word for word from the contract",
            "explanation": "What this clause means in plain language, and which party it favors",
            "is_standard": true
        }}
    ],
    "risk_flags": [
        {{
            "risk_title": "Short title of the risk",
            "description": "What the risk is and who it affects",
            "risk_level": "low",
            "recommendation": "What to negotiate, change, or add",
            "clause_reference": "Section number or title, e.g. Section 6.2"
        }}
    ],
    "overall_risk_level": "low",
    "recommendations": [
        "Recommendation 1",
        "Recommendation 2"
    ]
}}

Field rules:
- "is_standard" is a JSON boolean: true if the clause is typical and balanced, false if it is unusual or one-sided.
- "risk_level" and "overall_risk_level" must each be exactly one of: "low", "medium", "high", "critical".
- "recommendations" are the 3-6 most important next steps, most important first.

Analysis rules:
- Base everything ONLY on the contract text. Never invent clauses, numbers, names, dates, or facts.
- Do not bring in assumptions about any country, party, or law that the contract does not state.
- If the contract refers to something that is not included (for example an exhibit or schedule), flag that as a gap.
- Identify the 5-12 most important clauses (payment, term, termination, liability, IP, confidentiality,
  indemnity, non-compete, renewal, dispute resolution, and similar). If a clause has subsections, quote the whole clause.
- Flag clauses that are one-sided, unusually harsh, ambiguous, or that give one party rights the other lacks.
- Flag missing protections that a contract of this type would normally contain.
- Check specific numbers and mechanics, such as interest rates, penalties, caps, notice periods, price increases,
  and automatic renewals, and state them exactly.
- Report each risk only once, and cite the section it comes from.
- Describe risks and fairness, not legal conclusions. Do not state whether a clause is legally enforceable or valid.
- Use simple language. Keep each field short.
- If the text is not a contract, set "contract_type" to "Not a contract", leave the lists empty,
  set "overall_risk_level" to "low", and explain why in "summary".
- Return ONLY the JSON object. No markdown, no code fences, no other text.
"""


CLAUSE_EXTRACTION_PROMPT = """
You are a legal document analyst. Extract the distinct clauses from the contract text below.

CONTRACT TEXT:
{contract_text}

Rules:
- Extract ONLY clauses that actually appear in the text. Never invent or infer clauses.
- "clause_text" must be copied word for word from the contract, not paraphrased.
- Use the contract's own section number and heading in "clause_title" when it has them (e.g. "6. Warranty and Liability").
- Keep clauses in the order they appear in the contract.
- If the text is not a contract, return an empty array.

Return a JSON array in exactly this structure:
[
    {{
        "clause_title": "Title",
        "clause_text": "Full text of the clause"
    }}
]

Return ONLY the JSON array. No markdown, no code fences, no other text.
"""


RISK_ASSESSMENT_PROMPT = """
You are a contract risk assessor. Review the contract clauses below and flag the risks.
Do not assume any country or legal system beyond what the clauses themselves state.

CLAUSES:
{clauses_text}

Rules:
- Base every risk ONLY on the clauses provided. Never invent facts.
- Flag clauses that are one-sided, unusually harsh, or ambiguous, and standard protections that are missing.
- State specific numbers and mechanics exactly (interest, caps, notice periods, price increases, renewals).
- Report each risk once, and describe fairness and exposure, not whether a clause is legally enforceable.
- Order the risks from most to least severe.

Return a JSON array. Each risk has exactly this structure:
{{
    "risk_title": "Short title",
    "description": "What makes this risky and who it affects",
    "risk_level": "low",
    "recommendation": "What to negotiate, change, or add",
    "clause_reference": "Section number or title"
}}

"risk_level" must be exactly one of: "low", "medium", "high", "critical".
If there are no risks, return an empty array.
Return ONLY the JSON array. No markdown, no code fences, no other text.
"""


SUMMARY_PROMPT = """
Summarize this contract in 3-4 sentences for a non-lawyer.
Include: what it is about, who the parties are, the key obligations, the money involved, and the duration.
Use only information from the contract. Do not guess anything that is not stated.

CONTRACT TEXT:
{contract_text}

Return only the summary text, no JSON.
"""

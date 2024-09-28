# openai_analysis.py
from typing import Dict, Any
from openai import OpenAI

PROMPT_TEMPLATES = {
    "executive_summary": (
        "Provide an insightful, concise executive summary "
        "and key highlights of the following Japanese financial "
        "disclosure text. Do not reply in Japanese. "
        "Be more concise than normal and interpret the data. "
        "Provide a very concise (<15 words) summary of what the "
        "company that filed the document does. "
        "Begin your analysis with the company's English name, "
        "and end with a very concise (<15 words) "
        "`Potential Impact on Share Price`, with rationale."
    ),
    "one_liner": (
        "Provide a one-liner (<50 words), english-language "
        "Executive Summary of the following Japanese financial "
        "disclosure text. Do not reply in Japanese. "
        "Begin your analysis with the company's English name, "
        "and end with an ultra concise (<10 words) "
        "`Strategy` takeaway, with rationale."
    ),
    # Add more templates as needed
}


def openai_analyze(filing_data: Dict[str, Any], prompt_type: str = "one_liner") -> str:
    """
    Analyze financial disclosure data using OpenAI API.

    :param filing_data: Dictionary containing filing data
    :param prompt_type: Type of prompt to use (default: "one_liner")
    :return: OpenAI API response
    """
    if prompt_type not in PROMPT_TEMPLATES:
        raise ValueError(f"Invalid prompt type: {prompt_type}")

    system_role = (
        "You are a helpful, shrewd Japan capital markets and investment "
        "banking analyst with an eye for M&A strategy and "
        "opportunities. You are analyzing data."
    )

    instructions = PROMPT_TEMPLATES[prompt_type]

    data_info = (
        f"This data is from a document of type "
        f"`{filing_data['document_type']}`, filed with the FSA by "
        f"`{filing_data['company_name_ja']}`, or "
        f"`{filing_data['company_name_en']}` in English. "
        f"Data follows:"
    )

    data = f"{filing_data['text_blocks']}"

    system_prompt = f"""
    {system_role}
    {instructions}
    {data_info}
    {data}
    """

    client = OpenAI()
    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": system_prompt}]
    )

    return completion.choices[0].message.content

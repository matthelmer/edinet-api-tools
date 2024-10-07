# openai_analysis.py
import os
from typing import Dict, Any
from openai import OpenAI

from config import OPENAI_API_KEY

PROMPT_TEMPLATES = {
    "executive_summary": (
        "Provide an insightful, concise executive summary "
        "and key highlights of the following Japanese financial "
        "disclosure text. Do not reply in Japanese. "
        "Be more concise than normal and interpret the data. "
        "Provide a very concise (<15 words) summary of what the "
        "company that filed the document does. "
        "Always begin your analysis with the company's English name, "
        "all caps, and end with a very concise (<15 words) "
        "`Potential Impact on Share Price`, with rationale."
    ),
    "one_liner": (
        "Provide a one-liner (<50 words), english-language "
        "Executive Summary of the following Japanese financial "
        "disclosure text. Do not reply in Japanese. "
        "Begin your response with the company's English name."
    ),
    "m_a_signal": (
        "Provide an ultra concise (<20 words), "
        "clear, `M&A Strategy` strategic assessment of the data, "
        "especially concering potential share price impact."
    ),
    # Add more templates as needed
}


def openai_completion(filing_data: Dict[str, Any],
                      prompt_type: str = "one_liner") -> str:
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

    client = OpenAI(api_key=OPENAI_API_KEY)
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}]
    )

    return completion.choices[0].message.content

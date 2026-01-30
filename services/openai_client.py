import os
import streamlit as st
from openai import OpenAI

def get_client() -> OpenAI:
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to Streamlit secrets or env var.")
    return OpenAI(api_key=api_key)

def generate_text(messages, model=None, temperature=0.4) -> str:
    """
    messages: list of {"role": "user"/"assistant"/"system", "content": "..."}
    """
    client = get_client()
    model = model or st.secrets.get("MODEL", "gpt-5.2")
    resp = client.responses.create(
        model=model,
        input=messages,
        temperature=temperature,
    )
    return resp.output_text

import json
import os
import asyncio
import logging
from typing import Any, AsyncGenerator, List, Dict
import google.generativeai as genai
from pydantic import BaseModel, Field

from src.database import db
from src.redis_client import get_redis

logger = logging.getLogger(__name__)

# Initialize Gemini API key
api_key = os.environ.get("GEMINI_API_KEY", "")
if api_key:
    genai.configure(api_key=api_key)

# Candidate models with automatic fallback
TEXT_MODEL_CANDIDATES = ["gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-flash-latest"]
EMBEDDING_CANDIDATES = ["models/gemini-embedding-001", "models/gemini-embedding-2"]

class TaskExtraction(BaseModel):
    description: str = Field(description="Description of the actionable task")
    assignee_name: str | None = Field(description="Name of the person assigned to the task, if mentioned")
    due_date: str | None = Field(description="Due date in YYYY-MM-DD format if mentioned, else null")

class ChatSummary(BaseModel):
    key_points: list[str] = Field(description="Main topics discussed")
    decisions: list[str] = Field(description="Any decisions made")
    action_items: list[str] = Field(description="Action items and who is responsible")

async def _generate_content_with_fallback(prompt: str, generation_config=None) -> str:
    """Try text model candidates until one succeeds."""
    last_err = None
    for model_name in TEXT_MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            if generation_config:
                resp = await model.generate_content_async(prompt, generation_config=generation_config)
            else:
                resp = await model.generate_content_async(prompt)
            return resp.text
        except Exception as e:
            last_err = e
            if "404" in str(e) or "not found" in str(e).lower():
                continue
            raise e
    raise last_err or Exception("All Gemini model candidates failed.")

class AIService:
    @staticmethod
    async def summarize_document(doc_id: str, version: int, content: str) -> str:
        """Summarize a document, caching by version in Redis."""
        redis = get_redis()
        cache_key = f"doc:summary:{doc_id}:v{version}"
        
        # Check cache
        cached = await redis.get(cache_key)
        if cached:
            return cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
        
        if not os.environ.get("GEMINI_API_KEY"):
            return "GEMINI_API_KEY is not set in backend .env file. Please add your key to enable AI summarization."

        try:
            prompt = f"Please provide a concise and professional summary of the following document content:\n\n{content}"
            summary = await _generate_content_with_fallback(prompt)
            
            # Cache for 30 days
            await redis.setex(cache_key, 2592000, summary)
            return summary
        except Exception as e:
            logger.error(f"Error in summarize_document: {e}")
            return f"Failed to generate summary: {str(e)}. Make sure your GEMINI_API_KEY is valid."

    @staticmethod
    async def summarize_chat(messages: list[dict]) -> dict:
        """Produce a structured summary of chat messages."""
        if not messages:
            return {"key_points": [], "decisions": [], "action_items": []}
            
        if not os.environ.get("GEMINI_API_KEY"):
            return {
                "key_points": ["GEMINI_API_KEY is missing from backend .env file."],
                "decisions": [],
                "action_items": []
            }

        chat_transcript = ""
        for msg in messages:
            author_name = msg.get("author_name", "Unknown")
            content = msg.get("content", "")
            chat_transcript += f"{author_name}: {content}\n"
            
        try:
            prompt = f"Summarize the following chat conversation into key points, decisions, and action items.\n\n{chat_transcript}"
            config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ChatSummary,
            )
            raw_json = await _generate_content_with_fallback(prompt, generation_config=config)
            return json.loads(raw_json)
        except Exception as e:
            logger.error(f"Error in summarize_chat: {e}")
            return {"key_points": [f"AI Error: {str(e)}"], "decisions": [], "action_items": []}

    @staticmethod
    async def generate_embedding(text: str) -> list[float]:
        """Generate embedding using Gemini embedding model with candidates fallback."""
        if not text.strip() or not os.environ.get("GEMINI_API_KEY"):
            return [0.0] * 768
            
        def _embed():
            for m_name in EMBEDDING_CANDIDATES:
                try:
                    result = genai.embed_content(
                        model=m_name,
                        content=text,
                        task_type="retrieval_document",
                        output_dimensionality=768
                    )
                    return result["embedding"]
                except Exception:
                    continue
            return [0.0] * 768
            
        return await asyncio.to_thread(_embed)

    @staticmethod
    async def stream_writing_assistant(text: str, instruction: str) -> AsyncGenerator[str, None]:
        """Stream back AI suggested edits based on selected text and instruction."""
        if not os.environ.get("GEMINI_API_KEY"):
            yield "GEMINI_API_KEY is not set in backend .env file. Please add your key to enable AI Writing Assistant."
            return

        try:
            prompt = f"Act as a professional writing assistant. Based on the following instruction: '{instruction}', rewrite or continue the following text. Only return the revised text, no conversational filler.\n\nText: {text}"
            
            # Try streaming with candidate models
            model_to_use = None
            for m_name in TEXT_MODEL_CANDIDATES:
                try:
                    m = genai.GenerativeModel(m_name)
                    res = await m.generate_content_async(prompt, stream=True)
                    async for chunk in res:
                        if chunk.text:
                            yield chunk.text
                    return
                except Exception:
                    continue
            yield "Failed to generate stream response. Check API Key."
        except Exception as e:
            yield f"Error: {str(e)}"

    @staticmethod
    async def extract_tasks(content: str) -> list[dict]:
        """Extract actionable tasks from unstructured text into structured Task objects."""
        if not os.environ.get("GEMINI_API_KEY"):
            return []

        try:
            prompt = f"Extract all actionable tasks from the following text. If there are none, return an empty list.\n\nText: {content}"
            config = genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=list[TaskExtraction],
            )
            raw_json = await _generate_content_with_fallback(prompt, generation_config=config)
            return json.loads(raw_json)
        except Exception as e:
            logger.error(f"Error in extract_tasks: {e}")
            return []

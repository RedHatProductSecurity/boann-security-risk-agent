from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional
import os
import logging
from fastapi.responses import StreamingResponse
import asyncio
import json
import uuid

from llama_stack_client import LlamaStackClient
from llama_stack_client import Agent, AgentEventLogger

# Import system prompt from config module
from src.config import SYSTEM_PROMPT


# Import centralized logging configuration
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

# Security
security = HTTPBearer()
BOANN_API_KEY = os.getenv("BOANN_API_KEY")
if not BOANN_API_KEY:
    raise ValueError("BOANN_API_KEY environment variable must be set")

VECTOR_DB_ID = os.getenv("VECTOR_DB_ID", "boann-vector-db-id")


# Pydantic models
class DocumentQuery(BaseModel):
    query: str = Field(..., description="The query to search for")
    stream: Optional[bool] = Field(True, description="Whether to stream the response")


def correct_pgvector_score(score):
    """
    NOTE: This function is a workaround until https://github.com/llamastack/llama-stack/issues/3213 is fixed(or clarifled)

    Correct pgvector scores that are coming from LlamaStack pgvector provider's current implementation.

    For pgvector cosine distance, the proper similarity should be:
    cosine_similarity = 1 - cosine_distance

    But llama-stack uses: similarity = 1 / distance
    (e.g. https://github.com/llamastack/llama-stack/blob/main/llama_stack/providers/remote/vector_io/pgvector/pgvector.py#L136)

    To reverse this and get the proper normalized cosine similarity:
    - Original distance = 1 / score
    - Proper similarity = 1 - distance = 1 - (1 / score)
    - Normalized to [0, 1]: (similarity + 1) / 2

    Args:
        score: The raw score from llama-stack (using 1/distance formula)

    Returns:
        Corrected and normalized cosine similarity score between 0 and 1
    """
    if score == "N/A" or score is None:
        return score

    try:
        # Convert score to float if it's not already
        score_float = float(score)

        # Handle edge cases
        if score_float == float("inf"):
            logger.info("Infinity score detected (perfect match), converting to 1.0")
            return 1.0  # Perfect similarity (distance = 0) -> normalized to 1.0

        if score_float <= 0:
            return 0.0  # Maximum dissimilarity -> normalized to 0.0

        # Reverse the 1/distance formula to get original distance
        original_distance = 1.0 / score_float

        # Convert distance to proper cosine similarity: similarity = 1 - distance
        corrected_similarity = 1.0 - original_distance

        # Clamp to valid cosine similarity range [-1, 1]
        clamped_similarity = max(-1.0, min(1.0, corrected_similarity))

        # Normalize from [-1, 1] to [0, 1] range
        # Formula: normalized = (similarity + 1) / 2
        normalized_score = (clamped_similarity + 1.0) / 2.0

        # Log score correction if applied
        if score != "N/A" and normalized_score != score:
            logger.info(f"Score corrected for pgvector: {score} -> {normalized_score}")

        return normalized_score

    except (ValueError, ZeroDivisionError):
        return score  # Return original if conversion fails


# API Router
def get_public_router():
    router = APIRouter()

    def _get_vector_provider_id(client: LlamaStackClient) -> Optional[str]:
        """Get the vector provider ID from available providers"""
        for provider in client.providers.list():
            if provider.api == "vector_io":
                return getattr(provider, "provider_id", None)
        return None

    def verify_api_key(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> str:
        if credentials.credentials != BOANN_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return credentials.credentials

    async def create_sse_stream(agent_output, chunk_metadata_list):
        """Create a proper Server-Sent Events stream with JSON format"""
        try:
            # Process the agent output based on its type
            import inspect

            if inspect.iscoroutine(agent_output):
                agent_output = await agent_output

            # Check if it's an async generator
            if hasattr(agent_output, "__aiter__"):
                async for chunk in agent_output:
                    content = None

                    # Check for step progress with delta text (streaming tokens)
                    if (
                        hasattr(chunk, "event")
                        and hasattr(chunk.event, "payload")
                        and hasattr(chunk.event.payload, "delta")
                        and hasattr(chunk.event.payload.delta, "text")
                    ):
                        content = chunk.event.payload.delta.text

                    # Check for turn complete message
                    elif (
                        hasattr(chunk, "event")
                        and hasattr(chunk.event, "payload")
                        and hasattr(chunk.event.payload, "turn")
                    ):
                        turn = chunk.event.payload.turn
                        if hasattr(turn, "output_message") and hasattr(
                            turn.output_message, "content"
                        ):
                            content = turn.output_message.content

                    # Send content if we found any
                    if content:
                        json_data = {"type": "token", "content": content}
                        yield f"data: {json.dumps(json_data)}\n\n"

            elif hasattr(agent_output, "__iter__"):
                # Process regular generator
                for chunk in agent_output:
                    content = None

                    # Check for step progress with delta text (streaming tokens)
                    if (
                        hasattr(chunk, "event")
                        and hasattr(chunk.event, "payload")
                        and hasattr(chunk.event.payload, "delta")
                        and hasattr(chunk.event.payload.delta, "text")
                    ):
                        content = chunk.event.payload.delta.text

                    # Check for turn complete message
                    elif (
                        hasattr(chunk, "event")
                        and hasattr(chunk.event, "payload")
                        and hasattr(chunk.event.payload, "turn")
                    ):
                        turn = chunk.event.payload.turn
                        if hasattr(turn, "output_message") and hasattr(
                            turn.output_message, "content"
                        ):
                            content = turn.output_message.content

                    # Send content if we found any
                    if content:
                        json_data = {"type": "token", "content": content}
                        yield f"data: {json.dumps(json_data)}\n\n"

                    # Add a small async sleep to allow other coroutines to run
                    await asyncio.sleep(0.001)

            # Send chunk metadata before completion signal
            if chunk_metadata_list:
                metadata_data = {
                    "type": "metadata",
                    "metadata": {
                        "rag_chunks": chunk_metadata_list,
                        "total_chunks": len(chunk_metadata_list),
                    },
                }
                yield f"data: {json.dumps(metadata_data)}\n\n"

            # Send completion signal
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Error in streaming: {e}")
            # Send error as SSE
            error_data = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
            yield "data: [DONE]\n\n"

    @router.get("/health")
    async def health_endpoint():
        return {
            "status": "healthy",
            "service": "public",
            "endpoints": ["query", "health"],
        }

    @router.post("/query")
    async def query(
        query: DocumentQuery, request: Request, api_key: str = Depends(verify_api_key)
    ):
        """Streaming RAG query endpoint that returns results as they become available."""

        client = getattr(request.app.state, "llama_client", None)

        # After printing chunk content/metadata, send the chunks as context to the LLM
        # List available models
        if os.getenv("INFERENCE_MODEL"):
            model_id = os.getenv("INFERENCE_MODEL")
        else:
            models = client.models.list()
            llm = next(m for m in models if m.model_type == "llm")
            model_id = llm.identifier

        context = ""
        chunk_metadata_list = []
        if os.getenv("ENABLE_RAG", "false").lower() == "true":
            logger.debug("RAG is enabled")
            vector_db_id = VECTOR_DB_ID
            # Query for similar documents from pgvector db

            query_text = query.query
            logger.info(f"Querying for: {query_text}")

            logger.debug(client.vector_io)

            vector_provider = _get_vector_provider_id(client)
            logger.info(f"vector_provider: {vector_provider}")

            # Prepare query parameters based on vector provider
            query_params = {}
            if vector_provider:
                query_params = {
                    "max_chunks": os.getenv("MAX_CHUNKS", 10),
                    "score_threshold": os.getenv("SCORE_THRESHOLDS", 0.7),
                }

            results = client.vector_io.query(
                vector_db_id=vector_db_id, query=query_text, params=query_params
            )
            logger.info("vector_io results:")

            # Collect chunk metadata and print each chunk with its corresponding score
            for i, chunk in enumerate(results.chunks):
                score = results.scores[i] if i < len(results.scores) else "N/A"

                # Collect chunk metadata with score
                # Apply score correction for pgvector
                vector_db_provider = os.getenv("VECTOR_DB_PROVIDER", "").lower()

                if vector_db_provider == "pgvector":
                    corrected_score = correct_pgvector_score(score)
                else:
                    corrected_score = score

                logger.info(f"Chunk {i + 1}:")
                logger.info(
                    f"Content: {chunk.content[:200]}{'...' if len(chunk.content) > 200 else ''}"
                )
                logger.debug(f"original score from vector_io: {score}")
                logger.info(f"Score: {corrected_score}")
                logger.info(f"Metadata: {chunk.metadata}")
                logger.info("-" * 40)

                chunk_info = {
                    "chunk_index": i + 1,
                    "score": corrected_score,
                    "source_file_name": chunk.metadata.get("file_name", ""),
                }
                chunk_metadata_list.append(chunk_info)

            # Build context from retrieved chunks
            context = "\n\n".join(chunk.content for chunk in results.chunks)
            if not context:
                context = "No relevant documents found."

        # Get system prompt - reload .env file for runtime environment variable changes
        from dotenv import load_dotenv

        load_dotenv(override=True)  # Reload .env file and override existing values

        # Check if system prompt override is enabled
        override_enabled = (
            os.getenv("BOANN_OVERRIDE_SYSTEM_PROMPT", "false").lower() == "true"
        )
        if override_enabled:
            system_prompt = os.getenv("BOANN_SYSTEM_PROMPT", SYSTEM_PROMPT)
        else:
            system_prompt = SYSTEM_PROMPT

        logging.debug(f"System prompt: {system_prompt}")

        # Create the RAG agent
        agent = Agent(
            client,
            model=model_id,
            instructions=system_prompt,
        )
        session_id = agent.create_session(session_name=f"s{uuid.uuid4().hex}")

        user_question = query.query
        logger.debug("\nSending to LLM:")
        logger.debug(f"User question: {user_question}")
        logger.debug(f"Context: {context[:100]}{'...' if len(context) > 100 else ''}")

        output = agent.create_turn(
            messages=[
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {user_question}",
                }
            ],
            session_id=session_id,
            stream=query.stream,
        )

        if query.stream:
            logger.debug("streaming")
            return StreamingResponse(
                create_sse_stream(output, chunk_metadata_list),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )
        else:
            logger.debug("non streaming")
            try:
                # Get the final response content
                response_content = ""
                for event in AgentEventLogger().log(output):
                    if event is not None and hasattr(event, "content"):
                        response_content += event.content

                if not response_content:
                    # Fallback to output_message if available
                    if hasattr(output, "output_message") and hasattr(
                        output.output_message, "content"
                    ):
                        response_content = output.output_message.content
                    else:
                        response_content = "No response generated."

                return {
                    "content": response_content,
                    "metadata": {
                        "rag_chunks": chunk_metadata_list,
                        "total_chunks": len(chunk_metadata_list),
                    },
                }
            except Exception as e:
                logger.error(f"Error in non-streaming response: {e}")
                return {"content": "Sorry, there was an error processing your request."}

    return router

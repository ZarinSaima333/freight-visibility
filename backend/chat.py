"""Question endpoint with a single bounded correction attempt."""

import logging
from typing import Annotated

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from . import llm
from .chat_sql import UnsafeQuery, run_query, validate_sql

router = APIRouter(prefix='/api')
logger = logging.getLogger('uvicorn.error')
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AskRequest(BaseModel):
    question: Question
    history: list[Question] = Field(default_factory=list, max_length=6)


@router.get('/ask/status')
def ask_status() -> dict:
    return {'mock_mode': llm.mock_mode()}


@router.post('/ask')
def ask(request: AskRequest) -> dict:
    correction = ''
    fallback = False
    for _ in range(2):
        try:
            try:
                generated = llm.generate_sql(request.question, request.history, correction)
            except llm.UnsupportedQuestion:
                raise
            except Exception as exc:
                logger.warning("Gemini generation failed (%s).", type(exc).__name__)
                try:
                    generated = llm.mock_sql(request.question)
                except llm.UnsupportedQuestion as unsupported:
                    raise HTTPException(503, 'The question service is temporarily unavailable. Please try again later.') from unsupported
                fallback = True
            sql = validate_sql(generated)
            columns, rows = run_query(sql)
        except llm.UnsupportedQuestion as exc:
            raise HTTPException(400, str(exc)) from exc
        except UnsafeQuery as exc:
            correction = str(exc)
        except psycopg.Error as exc:
            # Send only the primary diagnostic, never connection details or result rows.
            if isinstance(exc, psycopg.OperationalError) and not exc.sqlstate:
                raise HTTPException(503, 'The shipment database is temporarily unavailable.') from exc
            correction = (exc.diag.message_primary or 'The database could not run that query.')[:300]
        except HTTPException:
            raise
        else:
            return dict(answer=llm.answer_from_rows(request.question, columns, rows, use_gemini=not fallback),
                        sql=sql, columns=columns, rows=rows, mock_mode=llm.mock_mode(), fallback=fallback)
        if fallback or llm.mock_mode():
            break
    raise HTTPException(422, 'I could not turn that into a shipment query. Try rephrasing it or choosing an example.')

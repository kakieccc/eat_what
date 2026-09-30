import json
from typing import TypeVar
from urllib.parse import urlsplit

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import APIError
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.models import Model

T = TypeVar("T", bound=Model)


class OpenAICompatibleLlm:
    def __init__(self, settings: Settings):
        self.model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            temperature=settings.llm_temperature,
            extra_body={"thinking": {"type": "disabled"}}
            if urlsplit(settings.llm_base_url).hostname == "api.deepseek.com"
            else None,
        )

    async def structured(self, schema: type[T], prompt: str, data: object) -> T:
        try:
            template = ChatPromptTemplate.from_messages([("system", prompt), ("human", "{data}")])
            chain = template | self.model.with_structured_output(schema, method="function_calling")
            result = await chain.ainvoke({"data": json.dumps(data, ensure_ascii=False)})
            return schema.model_validate(result)
        except (ValidationError, ValueError, OutputParserException):
            raise AppError("LLM_INVALID_OUTPUT", "模型输出未通过校验", 502) from None
        except (APIError, TimeoutError):
            raise AppError("LLM_UNAVAILABLE", "模型服务暂时不可用", 502, True) from None

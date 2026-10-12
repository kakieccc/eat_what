import json
from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.models import Model

T = TypeVar("T", bound=Model)


class OpenAICompatibleLlm:
    def __init__(self, settings: Settings, client: AsyncOpenAI):
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.client = client

    async def structured(self, schema: type[T], prompt: str, data: object) -> T:
        try:
            response = await self.client.responses.parse(
                model=self.model,
                instructions=prompt,
                input=json.dumps(data, ensure_ascii=False),
                reasoning={"effort": "none"},
                temperature=self.temperature,
                text_format=schema,
            )
            if response.status == "failed":
                raise AppError("LLM_UNAVAILABLE", "模型服务暂时不可用", 502, True)
            parsed = response.output_parsed
            if response.status != "completed" or parsed is None:
                raise AppError("LLM_INVALID_OUTPUT", "模型未返回完整结果", 502)
            return parsed
        except (ValidationError, ValueError):
            raise AppError("LLM_INVALID_OUTPUT", "模型输出未通过校验", 502) from None
        except (APIError, TimeoutError):
            raise AppError("LLM_UNAVAILABLE", "模型服务暂时不可用", 502, True) from None

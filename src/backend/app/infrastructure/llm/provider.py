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
        self.reasoning_effort = settings.llm_reasoning_effort
        self.temperature = settings.llm_temperature
        self.client = client

    async def structured(self, schema: type[T], prompt: str, data: object) -> T:
        try:
            response = await self.client.responses.create(
                model=self.model,
                instructions=prompt,
                input=json.dumps(data, ensure_ascii=False),
                reasoning={"effort": self.reasoning_effort},
                temperature=self.temperature,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                    }
                },
            )
            if response.status == "failed":
                raise AppError("LLM_UNAVAILABLE", "模型服务暂时不可用", 502, True)
            if response.status != "completed" or not response.output_text.strip():
                raise AppError("LLM_INVALID_OUTPUT", "模型未返回完整结果", 502)
            return schema.model_validate_json(response.output_text)
        except (ValidationError, ValueError):
            raise AppError("LLM_INVALID_OUTPUT", "模型输出未通过校验", 502) from None
        except (APIError, TimeoutError):
            raise AppError("LLM_UNAVAILABLE", "模型服务暂时不可用", 502, True) from None

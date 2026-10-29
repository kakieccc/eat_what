import json
import logging
from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.models import Model

T = TypeVar("T", bound=Model)
log = logging.getLogger("food.llm")


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
                log.warning("Structured output rejected: schema=%s stage=response type=incomplete", schema.__name__)
                raise AppError("LLM_INVALID_OUTPUT", "模型未返回完整结果", 502)
            return parsed
        except ValidationError as error:
            description = schema.model_json_schema()
            known_fields = set(schema.model_fields)
            for definition in (description, *description.get("$defs", {}).values()):
                known_fields.update(definition.get("properties", {}))
            failures = [
                {
                    "path": [
                        part if isinstance(part, int) or part in known_fields else "field"
                        for part in item["loc"]
                    ],
                    "type": item["type"],
                }
                for item in error.errors(include_input=False, include_context=False, include_url=False)
            ]
            log.warning("Structured output rejected: schema=%s stage=validation errors=%s",
                        schema.__name__, json.dumps(failures))
            raise AppError("LLM_INVALID_OUTPUT", "模型输出未通过校验", 502) from None
        except ValueError as error:
            log.warning("Structured output rejected: schema=%s stage=parse type=%s",
                        schema.__name__, type(error).__name__)
            raise AppError("LLM_INVALID_OUTPUT", "模型输出未通过校验", 502) from None
        except (APIError, TimeoutError):
            raise AppError("LLM_UNAVAILABLE", "模型服务暂时不可用", 502, True) from None

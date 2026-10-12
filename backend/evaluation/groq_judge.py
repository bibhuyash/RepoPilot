"""Explicit Groq judge for DeepEval's schema-aware metrics."""

from pydantic import BaseModel
from deepeval.models import DeepEvalBaseLLM

from app.config import groq_model
from app.llm import get_llm


class GroqJudge(DeepEvalBaseLLM):
    def __init__(self) -> None:
        self.client = get_llm()
        super().__init__(model=groq_model())

    def load_model(self):
        return self.client

    def get_model_name(self) -> str:
        return groq_model()

    def _model(self, schema: type[BaseModel] | None):
        return self.client.with_structured_output(schema, method="json_schema") if schema else self.client

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):
        result = self._model(schema).invoke(prompt)
        return result if schema else result.content

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):
        result = await self._model(schema).ainvoke(prompt)
        return result if schema else result.content

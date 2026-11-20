"""개념 설명은 AI 분류 프롬프트에만 들어가고 키워드 분류에는 쓰지 않는다."""

import pytest

from pipeline.tagger import tag_body
from pipeline.topics import CONCEPTS
from scripts.ai_classify import PROMPT_V1, PROMPT_V2, PROMPT_VERSION, system_prompt


def test_모든_개념에_기준_예시_출처_이웃_개념과의_차이가_있다():
    for concept in CONCEPTS:
        description = concept.description
        assert description is not None, concept.id
        assert all([description.definition, description.example, description.example_source,
                    description.contrast]), concept.id


def test_지금_프롬프트_버전은_설명을_넣은_v2다():
    assert PROMPT_VERSION == PROMPT_V2


def test_v1_프롬프트는_개념_id와_이름만_준다():
    prompt = system_prompt(PROMPT_V1)

    assert "- naming: 네이밍\n" in prompt
    assert "기준:" not in prompt


def test_v2_프롬프트는_개념마다_기준_예시_차이를_주고_출처는_넣지_않는다():
    prompt = system_prompt(PROMPT_V2)
    naming = next(concept for concept in CONCEPTS if concept.id == "naming")

    assert f"  기준: {naming.description.definition}" in prompt
    assert f"  예: {naming.description.example}" in prompt
    assert f"  헷갈리는 개념: {naming.description.contrast}" in prompt
    assert naming.description.example_source not in prompt


def test_모르는_프롬프트_버전은_막는다():
    with pytest.raises(ValueError):
        system_prompt("v9")


def test_설명은_키워드_분류에_쓰지_않는다():
    # 키워드가 없는 개념은 자기 설명 문장을 본문으로 줘도 키워드로는 붙지 않는다.
    for concept in (concept for concept in CONCEPTS if not concept.keywords):
        body = f"{concept.description.definition} {concept.description.example}"

        assert concept.id not in tag_body(body, "java-lotto"), concept.id

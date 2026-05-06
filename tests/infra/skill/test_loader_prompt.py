import pytest

from src.infra.skill.loader import build_skills_prompt


@pytest.mark.asyncio
async def test_build_skills_prompt_requires_transfer_before_execution() -> None:
    prompt = await build_skills_prompt(
        [{"name": "demo-skill", "description": "Run a demo script."}]
    )

    assert "transfer them out of `/skills/` into the sandbox workspace" in prompt
    assert "Use `transfer_file` or `transfer_path` to move skill files into the workspace" in prompt

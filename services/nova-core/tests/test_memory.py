"""Tests for memory tools (remember/forget/list_memories)."""
import pytest

from app.tools.base import TOOLS


@pytest.mark.asyncio
async def test_memory_tools_registered():
    """All three memory tools must be registered in TOOLS."""
    assert "remember" in TOOLS
    assert "forget" in TOOLS
    assert "list_memories" in TOOLS


class TestRememberTool:
    def setup_method(self):
        self.tool = TOOLS.get("remember")

    def test_schema_parameters(self):
        """remember must accept scope with private/household enum."""
        assert self.tool is not None, "remember tool not registered"
        props = self.tool.parameters["properties"]
        assert "content" in props
        assert props["content"]["type"] == "string"
        assert "scope" in props
        assert props["scope"]["enum"] == ["private", "household"]
        assert props["scope"]["type"] == "string"

    def test_schema_required(self):
        assert self.tool is not None
        assert "content" in self.tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_validation_missing_content(self):
        self.tool = TOOLS.get("remember")
        assert self.tool is not None
        res = await self.tool.run({}, user="Ruben")
        assert "validation error" in res

    @pytest.mark.asyncio
    async def test_validation_invalid_scope(self):
        self.tool = TOOLS.get("remember")
        assert self.tool is not None
        res = await self.tool.run({"content": "test", "scope": "public"}, user="Ruben")
        assert "validation error" in res

    @pytest.mark.asyncio
    async def test_validation_unknown_arg(self):
        self.tool = TOOLS.get("remember")
        assert self.tool is not None
        res = await self.tool.run({"content": "test", "unknown_arg": "x"}, user="Ruben")
        assert "validation error" in res


class TestForgetTool:
    def setup_method(self):
        self.tool = TOOLS.get("forget")

    def test_schema_parameters(self):
        assert self.tool is not None, "forget tool not registered"
        props = self.tool.parameters["properties"]
        assert "content_pattern" in props
        assert props["content_pattern"]["type"] == "string"
        assert "scope" in props
        assert props["scope"]["enum"] == ["private", "household"]

    def test_schema_required(self):
        assert self.tool is not None
        assert "content_pattern" in self.tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_validation_missing_content_pattern(self):
        self.tool = TOOLS.get("forget")
        assert self.tool is not None
        res = await self.tool.run({}, user="Ruben")
        assert "validation error" in res

    @pytest.mark.asyncio
    async def test_validation_invalid_scope(self):
        self.tool = TOOLS.get("forget")
        assert self.tool is not None
        res = await self.tool.run(
            {"content_pattern": "test", "scope": "invalid"}, user="Ruben"
        )
        assert "validation error" in res


class TestListMemoriesTool:
    def setup_method(self):
        self.tool = TOOLS.get("list_memories")

    def test_schema_parameters(self):
        assert self.tool is not None, "list_memories tool not registered"
        props = self.tool.parameters["properties"]
        assert "scope" in props
        assert props["scope"]["enum"] == ["private", "household"]
        # scope is optional
        assert "scope" not in self.tool.parameters.get("required", [])

    @pytest.mark.asyncio
    async def test_validation_invalid_scope(self):
        self.tool = TOOLS.get("list_memories")
        assert self.tool is not None
        res = await self.tool.run({"scope": "invalid"}, user="Ruben")
        assert "validation error" in res

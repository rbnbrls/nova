import pytest
from app.tools.base import tool, TOOLS


@pytest.mark.asyncio
async def test_tool_registration_and_execution():
    try:
        @tool(
            name="test_dummy_tool",
            description="A dummy test tool.",
            parameters={
                "type": "object",
                "properties": {
                    "val": {"type": "string"},
                    "num": {"type": "integer"},
                },
                "required": ["val"],
            }
        )
        async def dummy_tool(val: str, num: int = 0) -> str:
            return f"val={val}, num={num}"

        assert "test_dummy_tool" in TOOLS
        t = TOOLS["test_dummy_tool"]

        # 1. Test valid execution
        res = await t.run({"val": "hello", "num": 42}, user="Ruben")
        assert res == "val=hello, num=42"

        # 2. Test missing required field
        res = await t.run({"num": 42}, user="Ruben")
        assert "validation error" in res
        assert "'val' is a required property" in res

        # 3. Test mismatched types
        res = await t.run({"val": "hello", "num": "not-an-int"}, user="Ruben")
        assert "validation error" in res

        # 4. Test unknown arguments
        res = await t.run({"val": "hello", "unknown_arg": "extra"}, user="Ruben")
        assert "validation error" in res
        assert "unknown_arg" in res

    finally:
        TOOLS.pop("test_dummy_tool", None)

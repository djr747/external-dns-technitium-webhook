import ast
from pathlib import Path


def _is_class_scoped_fixture(decorator: ast.expr) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "fixture"
        and any(
            keyword.arg == "scope"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "class"
            for keyword in decorator.keywords
        )
    )


def test_class_scoped_integration_fixtures_are_classmethods() -> None:
    source = (Path(__file__).parents[1] / "integration" / "test_webhook_integration.py").read_text()
    tree = ast.parse(source)
    fixtures = [
        method
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for method in node.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_class_scoped_fixture(decorator) for decorator in method.decorator_list)
    ]
    assert fixtures
    for fixture in fixtures:
        assert any(
            isinstance(decorator, ast.Name) and decorator.id == "classmethod"
            for decorator in fixture.decorator_list
        )
        assert fixture.args.args[0].arg == "cls"

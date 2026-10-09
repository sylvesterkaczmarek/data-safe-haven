"""Regression coverage for globally unique SRE storage names."""

import ast
import re
from pathlib import Path

import pytest

from data_safe_haven.functions import unique_storage_account_name

PURPOSES = ("desiredstate", "sensitivedata", "configdata", "userdata")


@pytest.mark.parametrize("purpose", PURPOSES)
def test_similar_stacks_have_different_names(purpose):
    left = unique_storage_account_name("shm-prod5-sre-dsg1234", purpose)
    right = unique_storage_account_name("shm-prod5-sre-dsg9876", purpose)
    assert left != right


@pytest.mark.parametrize("purpose", PURPOSES)
def test_storage_names_match_azure_constraints(purpose):
    for stack in ("shm-prod5-sre-dsg1234", "shm-very-long-name-sre-long", "a"):
        name = unique_storage_account_name(stack, purpose)
        assert re.fullmatch(r"[a-z0-9]{3,24}", name)


def test_all_purposes_use_separate_names():
    names = [
        unique_storage_account_name("shm-prod5-sre-dsg1234", purpose)
        for purpose in PURPOSES
    ]
    assert len(set(names)) == len(PURPOSES)


def test_name_generation_is_stable():
    name = unique_storage_account_name("shm-prod5-sre-dsg1234", "configdata")
    assert name == unique_storage_account_name("shm-prod5-sre-dsg1234", "configdata")


@pytest.mark.parametrize("stack,purpose", [("", "desiredstate"), ("shm-a", "")])
def test_empty_inputs_are_rejected(stack, purpose):
    with pytest.raises(ValueError):
        unique_storage_account_name(stack, purpose)


PROJECT_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "filename,count",
    [
        ("data_safe_haven/infrastructure/programs/sre/desired_state.py", 1),
        ("data_safe_haven/infrastructure/programs/sre/data.py", 3),
    ],
)
def test_deployed_storage_names_use_full_stack_identity(filename, count):
    source = (PROJECT_ROOT / filename).read_text()
    nodes = ast.walk(ast.parse(source))
    calls = [
        node
        for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "unique_storage_account_name"
    ]
    assert len(calls) == count


@pytest.mark.parametrize(
    "filename,count",
    [
        (
            "data_safe_haven/infrastructure/components/composite/nfsv3_storage_account.py",
            1,
        ),
        ("data_safe_haven/infrastructure/programs/sre/data.py", 2),
    ],
)
def test_pulumi_preserves_names_in_existing_stacks(filename, count):
    source = (PROJECT_ROOT / filename).read_text()
    nodes = ast.walk(ast.parse(source))
    matches = [
        kw
        for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ResourceOptions"
        for kw in node.keywords
        if kw.arg == "ignore_changes"
        and isinstance(kw.value, ast.List)
        and len(kw.value.elts) == 1
        and isinstance(kw.value.elts[0], ast.Constant)
        and kw.value.elts[0].value == "account_name"
    ]
    assert len(matches) == count

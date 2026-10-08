"""Allow distinct storage names for SREs sharing a short legacy name prefix."""

import pytest
from pydantic import ValidationError

from data_safe_haven.config import SREConfig
from data_safe_haven.functions import alphanumeric, sha256hash, truncate_tokens
from data_safe_haven.infrastructure.programs.sre.desired_state import (
    desired_state_storage_account_name,
)

NAME_1 = "shm-prod5-sre-dsg1234"
NAME_2 = "shm-prod5-sre-dsg9876"
COMPONENT = "sre_desired_state"


def test_default_name_retains_previous_formula():
    for stack in (NAME_1, NAME_2, "shm-acme-sre-sandbox"):
        old = alphanumeric(
            f"{''.join(truncate_tokens(stack.split('-'), 11))}"
            f"desiredstate{sha256hash(COMPONENT)}"
        )[:24]
        assert desired_state_storage_account_name(stack, COMPONENT) == old


def test_similarly_named_sres_can_select_distinct_azure_names():
    # Issue #2370: both names may collapse to a shared 24-character prefix.
    a = desired_state_storage_account_name(NAME_1, COMPONENT, "shmprod5dsg1234ds")
    b = desired_state_storage_account_name(NAME_2, COMPONENT, "shmprod5dsg9876ds")
    assert a != b
    assert a == "shmprod5dsg1234ds"
    assert b == "shmprod5dsg9876ds"


def test_override_has_priority_over_legacy_generated_name():
    assert (
        desired_state_storage_account_name(NAME_1, COMPONENT, "myuniquedshaccount999")
        == "myuniquedshaccount999"
    )


def test_old_configs_still_load_without_an_override(sre_config):
    old = sre_config.model_dump(mode="json")
    old["sre"].pop("desired_state_storage_account_name", None)
    restored = SREConfig.model_validate(old)
    assert restored.sre.desired_state_storage_account_name is None
    assert "desired_state_storage_account_name" not in restored.sre.model_dump()


def test_optional_override_roundtrips_through_yaml(sre_config):
    sre_config.sre.desired_state_storage_account_name = "uniqueacmestatestorage1"
    assert (
        SREConfig.from_yaml(sre_config.to_yaml()).sre.desired_state_storage_account_name
        == "uniqueacmestatestorage1"
    )


@pytest.mark.parametrize(
    "name",
    [
        "",
        "aa",
        "a" * 25,
        "UPPERCASE",
        "contains-dash",
        "contains_underscore",
        "contains space",
        "unicodeé",
    ],
)
def test_invalid_storage_account_names_rejected(sre_config, name):
    with pytest.raises(ValidationError, match="desired_state_storage_account_name"):
        sre_config.sre.desired_state_storage_account_name = name

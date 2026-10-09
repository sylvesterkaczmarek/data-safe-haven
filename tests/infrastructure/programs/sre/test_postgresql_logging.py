from typing import Any

import pulumi
import pytest
from pytest_mock import MockerFixture

from data_safe_haven.config.config_sections import ConfigSectionMonitoring
from data_safe_haven.infrastructure.components.composite.postgresql_database import (
    PostgresqlDatabaseComponent,
    PostgresqlDatabaseProps,
)

WORKSPACE_ID = (
    "/subscriptions/example/resourceGroups/example/providers/"
    "Microsoft.OperationalInsights/workspaces/example-log"
)


def postgresql_props(
    *, enabled: bool, workspace: str | None
) -> PostgresqlDatabaseProps:
    return PostgresqlDatabaseProps(
        database_names=[],
        database_password="not-a-secret",
        database_resource_group_name="test-resource-group",
        database_server_name="test-postgresql",
        database_subnet_id="/subscriptions/test/subnets/example",
        database_username="postgresadmin",
        disable_secure_transport=False,
        location="uksouth",
        log_analytics_workspace_id=workspace,
        postgresql_logs_enabled=enabled,
    )


class TestPostgresqlServerLogs:
    def test_default_is_opted_out(self) -> None:
        config = ConfigSectionMonitoring()
        assert config.postgresql_logs_enabled is False
        assert ConfigSectionMonitoring(
            postgresql_logs_enabled=True
        ).postgresql_logs_enabled

    def test_enabled_requires_workspace_id(self) -> None:
        with pytest.raises(ValueError, match="workspace ID is required"):
            postgresql_props(enabled=True, workspace=None)

    @pulumi.runtime.test
    def test_opt_out_does_not_create_diagnostic_setting(
        self, mocker: MockerFixture
    ) -> Any:
        create = mocker.patch(
            "data_safe_haven.infrastructure.components.composite."
            "postgresql_database.monitor.DiagnosticSetting"
        )
        component = PostgresqlDatabaseComponent(
            "test_pg_logs_off", postgresql_props(enabled=False, workspace=WORKSPACE_ID)
        )
        create.assert_not_called()
        assert component.diagnostic_setting is None

    @pulumi.runtime.test
    def test_opt_in_collects_server_logs_with_dedicated_table(
        self, mocker: MockerFixture
    ) -> Any:
        create = mocker.patch(
            "data_safe_haven.infrastructure.components.composite."
            "postgresql_database.monitor.DiagnosticSetting"
        )
        component = PostgresqlDatabaseComponent(
            "test_pg_logs_on", postgresql_props(enabled=True, workspace=WORKSPACE_ID)
        )
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        assert kwargs["name"] == "postgresql-server-logs"
        assert kwargs["workspace_id"] == WORKSPACE_ID
        assert kwargs["resource_uri"] == component.db_server.id
        assert kwargs["log_analytics_destination_type"] == "Dedicated"
        assert len(kwargs["logs"]) == 1
        log = kwargs["logs"][0]
        assert log.category == "PostgreSQLLogs"
        assert log.enabled is True
        assert component.diagnostic_setting is create.return_value

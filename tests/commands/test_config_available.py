from data_safe_haven.commands.config import config_command_group
from data_safe_haven.config import ContextManager, DSHPulumiConfig
from data_safe_haven.external import AzureSdk


def test_available_without_pulumi_config(context_manager, mocker, runner):
    """List uploaded SRE configs before the first SRE has been deployed."""
    mocker.patch.object(ContextManager, "from_file", return_value=context_manager)
    mocker.patch.object(AzureSdk, "list_blobs", return_value=["sre-sandbox.yaml"])
    mocker.patch.object(DSHPulumiConfig, "remote_exists", return_value=False)
    mock_from_remote = mocker.patch.object(DSHPulumiConfig, "from_remote")

    result = runner.invoke(config_command_group, ["available"])

    assert result.exit_code == 0
    assert "Available SRE configurations" in result.stdout
    assert "sandbox" in result.stdout
    mock_from_remote.assert_not_called()

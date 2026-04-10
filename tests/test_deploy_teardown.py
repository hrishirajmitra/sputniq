import pytest
from unittest.mock import MagicMock, patch
from sputniq.ops.deploy import teardown_app

@patch('sputniq.ops.deploy.docker.from_env')
def test_teardown_app_removes_containers(mock_docker_env):
    mock_client = MagicMock()
    mock_docker_env.return_value = mock_client
    
    mock_container_1 = MagicMock()
    mock_container_1.name = "sputniq-agent-1234"
    mock_container_2 = MagicMock()
    mock_container_2.name = "sputniq-tool-1234"
    
    # Mock finding 2 containers with the run_id label
    mock_client.containers.list.return_value = [mock_container_1, mock_container_2]
    
    removed = teardown_app("1234")
    
    assert removed == 2
    mock_container_1.remove.assert_called_once_with(force=True)
    mock_container_2.remove.assert_called_once_with(force=True)
    mock_client.containers.list.assert_called_once_with(all=True, filters={"label": "sputniq.run_id=1234"})


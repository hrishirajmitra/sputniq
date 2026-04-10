import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from docker.errors import BuildError, APIError

from sputniq.ops.builder import ImageBuilder

@pytest.fixture
def mock_docker_client():
    with patch("sputniq.ops.builder.docker.from_env") as mock_from_env:
        mock_client = MagicMock()
        mock_images = MagicMock()
        mock_client.images = mock_images
        mock_from_env.return_value = mock_client
        yield mock_client

@pytest.fixture
def fake_service_dir(tmp_path):
    d = tmp_path / "my_service"
    d.mkdir()
    d.joinpath("Dockerfile").write_text("FROM python:3.11\nCMD ['echo', 'hi']")
    return d

def test_image_builder_success(mock_docker_client, fake_service_dir):
    builder = ImageBuilder()
    
    mock_image = MagicMock()
    mock_image.short_id = "abc1234"
    mock_docker_client.images.build.return_value = (mock_image, [{"stream": "Step 1/2"}])
    
    builder.build_service(fake_service_dir, tag="my_service:latest")
    
    mock_docker_client.images.build.assert_called_once_with(
        path=str(fake_service_dir),
        tag="my_service:latest",
        rm=True
    )

def test_image_builder_missing_dockerfile(tmp_path):
    d = tmp_path / "empty_dir"
    d.mkdir()
    
    with patch("sputniq.ops.builder.docker.from_env"):
        builder = ImageBuilder()
        with pytest.raises(FileNotFoundError, match="No Dockerfile found"):
            builder.build_service(d, tag="my_service:latest")

def test_image_builder_build_error(mock_docker_client, fake_service_dir):
    mock_docker_client.images.build.side_effect = BuildError(
        reason="Syntax Error",
        build_log=[{"stream": "COPY failed: missing file\n"}]
    )
    
    builder = ImageBuilder()
    with pytest.raises(BuildError):
        builder.build_service(fake_service_dir, tag="fail_service:latest")

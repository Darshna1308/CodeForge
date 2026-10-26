import shutil
import subprocess

import pytest


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", "codeforge-sandbox:latest"], capture_output=True)
    return r.returncode == 0


requires_docker = pytest.mark.skipif(not docker_available(), reason="docker + codeforge-sandbox image required")

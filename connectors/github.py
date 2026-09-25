from typing import Any

from .base import Connector


class GitHubConnector(Connector):
    name = "github"
    description = "GitHub repository star count"
    capabilities = ["github_stars"]

    parameters = {
        "owner": {"type": "string", "required": True, "description": "GitHub repo owner/org"},
        "repo": {"type": "string", "required": True, "description": "GitHub repo name"},
    }

    value_field = "stars"
    min_interval_seconds = 60
    default_interval_seconds = 300

    def build_request(self, parameters: dict[str, Any]) -> dict[str, Any]:
        owner = parameters["owner"]
        repo = parameters["repo"]
        return {
            "method": "GET",
            "url": f"https://api.github.com/repos/{owner}/{repo}",
            "params": {},
        }

    def extract_value(self, response_json: dict[str, Any], parameters: dict[str, Any]) -> float:
        if "stargazers_count" not in response_json:
            raise ValueError(
                f"GitHub response missing stargazers_count — "
                f"check {parameters.get('owner')}/{parameters.get('repo')} exists"
            )
        return float(response_json["stargazers_count"])

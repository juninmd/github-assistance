from unittest.mock import MagicMock

from src.agents.repo_manager import RepositoryManager


def _repo(full_name: str):
    repo = MagicMock()
    repo.full_name = full_name
    repo.owner.login = full_name.split("/", 1)[0]
    return repo


def test_get_allowed_repositories_filters_to_target_owner():
    github = MagicMock()
    github.get_user_repos.return_value = [
        _repo("juninmd/allowed"),
        _repo("other/blocked"),
    ]
    allowlist = MagicMock()
    allowlist.list_repositories.return_value = ["juninmd/listed", "other/listed"]
    allowlist.is_allowed.side_effect = lambda repo: repo == "juninmd/allowed"
    manager = RepositoryManager(github, allowlist, "juninmd", MagicMock())

    assert manager.get_allowed_repositories(enforce_allowlist=False) == [
        "juninmd/allowed",
        "juninmd/listed",
    ]
    assert manager.get_allowed_repositories(enforce_allowlist=True) == [
        "juninmd/allowed",
        "juninmd/listed",
    ]


def test_can_work_on_blocks_other_owner_even_without_allowlist_enforcement():
    allowlist = MagicMock()
    allowlist.is_allowed.return_value = True
    manager = RepositoryManager(MagicMock(), allowlist, "juninmd", MagicMock())

    assert manager.can_work_on("juninmd/repo", enforce_allowlist=False) is True
    assert manager.can_work_on("other/repo", enforce_allowlist=False) is False


def test_get_info_does_not_fetch_other_owner_repo():
    github = MagicMock()
    log = MagicMock()
    manager = RepositoryManager(github, MagicMock(), "juninmd", log)

    assert manager.get_info("other/repo") is None
    github.get_repo.assert_not_called()
    log.assert_called_once()

import unittest
from unittest.mock import MagicMock, patch

import src.scripts as scripts


class TestScriptsCoverage(unittest.TestCase):
    @patch("src.scripts.Settings")
    @patch("src.scripts.run_agent")
    @patch("src.scripts.run_all")
    def test_all_entry_points(self, mock_run_all, mock_run_agent, mock_settings):
        mock_settings_inst = MagicMock()
        mock_settings.from_env.return_value = mock_settings_inst

        # Call all entry point functions
        scripts.product_manager()
        mock_run_agent.assert_called_with("product-manager", mock_settings_inst)

        scripts.interface_developer()
        mock_run_agent.assert_called_with("interface-developer", mock_settings_inst)

        scripts.senior_developer()
        mock_run_agent.assert_called_with("senior-developer", mock_settings_inst)

        scripts.pr_assistant()
        mock_run_agent.assert_called_with("pr-assistant", mock_settings_inst)

        scripts.security_scanner()
        mock_run_agent.assert_called_with("security-scanner", mock_settings_inst)

        scripts.ci_health()
        mock_run_agent.assert_called_with("ci-health", mock_settings_inst)

        scripts.pr_sla()
        mock_run_agent.assert_called_with("pr-sla", mock_settings_inst)

        scripts.jules_tracker()
        mock_run_agent.assert_called_with("jules-tracker", mock_settings_inst)

        scripts.jules_cleaner()
        mock_run_agent.assert_called_with("jules-cleaner", mock_settings_inst)

        scripts.secret_remover()
        mock_run_agent.assert_called_with("secret-remover", mock_settings_inst)

        scripts.project_creator()
        mock_run_agent.assert_called_with("project-creator", mock_settings_inst)

        scripts.conflict_resolver()
        mock_run_agent.assert_called_with("conflict-resolver", mock_settings_inst)

        scripts.code_reviewer()
        mock_run_agent.assert_called_with("code-reviewer", mock_settings_inst)

        scripts.branch_cleaner()
        mock_run_agent.assert_called_with("branch-cleaner", mock_settings_inst)

        scripts.intelligence_standardizer()
        mock_run_agent.assert_called_with("intelligence-standardizer", mock_settings_inst)

        scripts.readme_curator()
        mock_run_agent.assert_called_with("readme-curator", mock_settings_inst)

        scripts.all_agents()
        mock_run_all.assert_called_with(mock_settings_inst)

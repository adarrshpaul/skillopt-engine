import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from skill_procurer import SkillProcurer

class TestSkillProcurer(unittest.TestCase):

    def setUp(self):
        self.procurer = SkillProcurer(skills_dir="test_skills")

    def tearDown(self):
        import shutil
        if os.path.exists("test_skills"):
            shutil.rmtree("test_skills")

    def test_analyze_missing_skills(self):
        task_graph = [
            {"step_id": 1, "description": "Initialize a Stripe checkout session."},
            {"step_id": 2, "description": "Push the results to AWS S3."}
        ]
        missing = self.procurer.analyze_missing_skills(task_graph)
        self.assertIn("stripe", missing)
        self.assertIn("aws", missing)
        self.assertNotIn("github", missing)

    def test_detect_credentials_env_var(self):
        mock_content = '''
        You must supply the API key via os.environ.get("STRIPE_SECRET_KEY")
        '''
        creds = self.procurer.detect_credentials(mock_content)
        self.assertIn("STRIPE_SECRET_KEY", creds)

    def test_detect_credentials_bearer(self):
        mock_content = '''
        Ensure you send headers: Authorization: Bearer <GITHUB_TOKEN>
        '''
        creds = self.procurer.detect_credentials(mock_content)
        self.assertIn("GITHUB_TOKEN", creds)

    def test_detect_credentials_required_auth(self):
        mock_content = '''
        Required Auth: AWS_ACCESS_KEY
        '''
        creds = self.procurer.detect_credentials(mock_content)
        self.assertIn("AWS_ACCESS_KEY", creds)

    def test_get_skill_content(self):
        # Create a mock skill file
        os.makedirs("test_skills", exist_ok=True)
        with open("test_skills/stripe_skill.md", "w") as f:
            f.write("mock stripe skill")
            
        content = self.procurer.get_skill_content("Use stripe to pay")
        self.assertIn("mock stripe skill", content)
        self.assertIn("Stripe Webhook/API", content)

if __name__ == '__main__':
    unittest.main()

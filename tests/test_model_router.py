import unittest
import model_router

class TestModelRouter(unittest.TestCase):
    def test_default_roles_exist(self):
        roles = ["planner", "coder", "reviewer", "fallback", "optimizer"]
        for r in roles:
            endpoint = model_router.get(r)
            self.assertIsNotNone(endpoint.model)
            self.assertIsNotNone(endpoint.engine)
            self.assertIsNotNone(endpoint.url)

    def test_planner_defaults(self):
        self.assertEqual(model_router.get_engine("planner"), "openrouter")
        self.assertEqual(model_router.get_model("planner"), "nvidia/nemotron-3-ultra-550b-a55b:free")

    def test_coder_defaults(self):
        self.assertEqual(model_router.get_engine("coder"), "openrouter")
        self.assertEqual(model_router.get_model("coder"), "poolside/laguna-s-2.1:free")

    def test_reviewer_defaults(self):
        self.assertEqual(model_router.get_engine("reviewer"), "openrouter")
        self.assertEqual(model_router.get_model("reviewer"), "nvidia/nemotron-3-super-120b-a12b:free")

    def test_fallback_defaults(self):
        self.assertEqual(model_router.get_engine("fallback"), "mlx")
        self.assertEqual(model_router.get_model("fallback"), "mlx-community/Nanbeige4.1-3B-heretic-4bit")
        self.assertIn(":8801", model_router.get_url("fallback"))

    def test_dynamic_register(self):
        custom = model_router.ModelEndpoint(
            model="custom-model",
            engine="litellm",
            url="http://localhost:9000/v1",
            role_description="Custom test role"
        )
        model_router.register("custom", custom)
        self.assertEqual(model_router.get_model("custom"), "custom-model")
        self.assertEqual(model_router.get_engine("custom"), "litellm")

if __name__ == "__main__":
    unittest.main()

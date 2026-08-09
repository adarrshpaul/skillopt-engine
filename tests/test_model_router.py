import unittest
import model_router

class TestModelRouter(unittest.TestCase):
    def test_ornith_routes_to_coder_port(self):
        url = model_router.get_url("coder")
        self.assertIn(":8800", url)
        self.assertEqual(model_router.get_model("coder"), "AtomicChat/Ornith-9B-MLX-6bit")

    def test_ling_routes_to_planner_port(self):
        url = model_router.get_url("planner")
        self.assertIn(":8801", url)
        self.assertEqual(model_router.get_model("planner"), "mlx-community/Ling-mini-2.0-4bit")

    def test_reviewer_uses_ling(self):
        model = model_router.get_model("reviewer")
        url = model_router.get_url("reviewer")
        self.assertIn("Ling", model)
        self.assertIn(":8801", url)

    def test_fallback_uses_ornith(self):
        model = model_router.get_model("fallback")
        url = model_router.get_url("fallback")
        self.assertIn("ornith", model.lower())
        self.assertIn(":8800", url)

    def test_no_role_shares_wrong_port(self):
        self.assertNotIn(":8801", model_router.get_url("coder"))
        self.assertNotIn(":8801", model_router.get_url("fallback"))
        self.assertNotIn(":8800", model_router.get_url("planner"))
        self.assertNotIn(":8800", model_router.get_url("reviewer"))

if __name__ == "__main__":
    unittest.main()

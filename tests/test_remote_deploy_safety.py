import unittest
from pathlib import Path


class RemoteDeploySafetyTest(unittest.TestCase):
    def test_images_build_before_active_containers_are_recreated(self) -> None:
        source = (Path(__file__).parents[1] / "deploy" / "remote_deploy.py").read_text(encoding="utf-8")

        build = "$COMPOSE -f docker-compose.prod.yml build"
        recreate = "$COMPOSE -f docker-compose.prod.yml up -d --force-recreate --remove-orphans"
        self.assertIn(build, source)
        self.assertIn(recreate, source)
        self.assertLess(source.index(build), source.index(recreate))
        self.assertNotIn("docker rm -f trade-review-frontend trade-review-api", source)
        self.assertNotIn("up -d --build", source)


if __name__ == "__main__":
    unittest.main()

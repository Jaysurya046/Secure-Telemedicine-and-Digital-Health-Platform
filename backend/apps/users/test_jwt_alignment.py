"""
Tests for Step 2E: JWT signing configuration alignment across Django and Realtime services.
Verifies that:
1. A Django access token verifies through the realtime authentication middleware
   when Django and JWT secrets have distinct test values.
2. A token signed with an invalid/different key is rejected by the realtime authentication middleware.
3. Missing or blank JWT configuration behaves consistently across both Django and Realtime.
4. Settings resolution is completely isolated from real local .env files (via python-decouple isolation).
5. A regression test proves that a synthetic local .env cannot contaminate settings resolution.
6. Docker Compose environment forwarding contains DJANGO_SECRET_KEY and JWT_SECRET_KEY
   for all Django and Realtime services.
"""
import os
import json
import shutil
import subprocess
import sys
import tempfile
import yaml
from pathlib import Path
from django.test import SimpleTestCase
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.backends import TokenBackend


class JWTConfigurationAlignmentTests(SimpleTestCase):
    """
    Cross-service verification ensuring Django and Realtime services share
    the exact same effective JWT key under all configuration conditions.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo_root = Path(__file__).resolve().parent.parent.parent.parent
        cls.realtime_dir = cls.repo_root / 'realtime-service'
        cls.backend_dir = cls.repo_root / 'backend'
        cls.node_available = shutil.which('node') is not None

    def _create_django_token(self, signing_key: str, user_id: str = 'user-test-uuid-123',
                             role: str = 'patient', email: str = 'testpatient@example.com') -> str:
        """
        Creates a valid Django SimpleJWT access token payload and signs it
        using SimpleJWT's TokenBackend with the specified signing key.
        """
        token = AccessToken()
        token['user_id'] = user_id
        token['role'] = role
        token['email'] = email
        backend = TokenBackend(algorithm='HS256', signing_key=signing_key)
        return backend.encode(token.payload)

    def _verify_token_with_realtime_middleware(self, token: str, env_vars: dict) -> dict:
        """
        Invokes realtime-service authenticateSocket via Node.js subprocess
        with specified environment variables. Returns result dictionary.
        Does not dump sensitive environment variables or secrets.
        """
        self.assertTrue(self.node_available, "Node.js executable is required for cross-service verification")

        node_script = """
        import { authenticateSocket, getJwtSecret } from './src/auth/middleware.js';

        const token = process.env.TEST_AUTH_TOKEN;
        const socket = {
            handshake: {
                auth: { token },
                headers: {}
            }
        };

        authenticateSocket(socket, (err) => {
            if (err) {
                console.log(JSON.stringify({
                    success: false,
                    error: err.message,
                    resolvedSecret: getJwtSecret()
                }));
            } else {
                console.log(JSON.stringify({
                    success: true,
                    user: socket.user,
                    resolvedSecret: getJwtSecret()
                }));
            }
        });
        """

        full_env = os.environ.copy()
        # Clear any ambient secret keys before applying synthetic test env
        full_env.pop('DJANGO_SECRET_KEY', None)
        full_env.pop('JWT_SECRET_KEY', None)
        full_env.update(env_vars)
        full_env['TEST_AUTH_TOKEN'] = token

        proc = subprocess.run(
            ['node', '--input-type=module', '-e', node_script],
            cwd=str(self.realtime_dir),
            capture_output=True,
            text=True,
            env=full_env,
            timeout=10
        )

        self.assertEqual(
            proc.returncode, 0,
            f"Node subprocess failed with exit code {proc.returncode}"
        )
        return json.loads(proc.stdout.strip())

    def _resolve_django_settings_key(
        self,
        env_vars: dict,
        synthetic_search_path: str | None = None
    ) -> tuple[str, str]:
        """
        Loads backend/config/settings.py in a clean, isolated subprocess to verify
        the exact resolved SECRET_KEY and SIMPLE_JWT['SIGNING_KEY'].

        Isolation guarantees:
        1. Ambient DJANGO_SECRET_KEY and JWT_SECRET_KEY are purged from the subprocess environment.
        2. python-decouple is initialized with decouple.RepositoryEmpty(), completely isolating
           the settings resolution from any real developer .env file on disk.
        3. No resolved secret values are printed in failure messages or diagnostic errors.
        """
        full_env = os.environ.copy()
        full_env.pop('DJANGO_SECRET_KEY', None)
        full_env.pop('JWT_SECRET_KEY', None)
        full_env.update(env_vars)

        code_lines = [
            "import sys",
            "sys.path.insert(0, 'backend')",
            "import decouple",
        ]
        if synthetic_search_path:
            # Set search path to test synthetic local .env directory
            code_lines.append(f"decouple.config.search_path = {repr(synthetic_search_path)}")

        # Enforce RepositoryEmpty so real local .env files cannot contaminate resolution
        code_lines.extend([
            "decouple.config.config = decouple.Config(decouple.RepositoryEmpty())",
            "import os",
            "os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'",
            "from django.conf import settings",
            "import json",
            "print(json.dumps({'SECRET_KEY': settings.SECRET_KEY, 'JWT_SIGNING_KEY': settings.SIMPLE_JWT['SIGNING_KEY']}))",
        ])
        code = "; ".join(code_lines)

        proc = subprocess.run(
            [sys.executable, '-c', code],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            env=full_env,
            timeout=10
        )
        self.assertEqual(
            proc.returncode, 0,
            f"Django settings resolution subprocess exited with error code {proc.returncode}"
        )
        data = json.loads(proc.stdout.strip())
        return data['SECRET_KEY'], data['JWT_SIGNING_KEY']

    def test_django_token_verifies_with_distinct_django_and_jwt_secrets(self):
        """
        1. When DJANGO_SECRET_KEY and JWT_SECRET_KEY have distinct values,
        Django signs with JWT_SECRET_KEY and Realtime verifies with JWT_SECRET_KEY.
        """
        synthetic_django_secret = "synthetic-test-django-secret-key-11111"
        synthetic_jwt_secret = "synthetic-test-jwt-secret-key-22222"

        # Generate a Django token signed with synthetic_jwt_secret
        token_str = self._create_django_token(
            signing_key=synthetic_jwt_secret,
            user_id='user-test-uuid-123',
            role='patient',
            email='testpatient@example.com'
        )

        # Verify through Realtime middleware configured with the same environment
        realtime_env = {
            'DJANGO_SECRET_KEY': synthetic_django_secret,
            'JWT_SECRET_KEY': synthetic_jwt_secret,
        }
        result = self._verify_token_with_realtime_middleware(token_str, realtime_env)

        self.assertTrue(result['success'], f"Token verification failed: {result.get('error')}")
        self.assertEqual(result['user']['id'], 'user-test-uuid-123')
        self.assertEqual(result['user']['role'], 'patient')
        self.assertEqual(result['user']['email'], 'testpatient@example.com')
        # Diagnostic avoids printing raw secret values
        self.assertTrue(
            result.get('resolvedSecret') == synthetic_jwt_secret,
            "Realtime middleware did not resolve to the configured synthetic JWT secret"
        )

    def test_token_signed_with_different_key_is_rejected(self):
        """
        2. A token signed with a different key is rejected by the realtime authentication code.
        """
        synthetic_jwt_secret = "synthetic-test-jwt-secret-key-22222"
        wrong_key = "attacker-unauthorized-signing-key-99999"

        token_str = self._create_django_token(
            signing_key=wrong_key,
            user_id='user-test-uuid-123',
            role='patient',
            email='attacker@example.com'
        )

        realtime_env = {
            'DJANGO_SECRET_KEY': "some-django-secret",
            'JWT_SECRET_KEY': synthetic_jwt_secret,
        }
        result = self._verify_token_with_realtime_middleware(token_str, realtime_env)

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Unauthorized socket connection')

    def test_missing_or_blank_jwt_secret_falls_back_consistently(self):
        """
        3. When JWT_SECRET_KEY is omitted, empty, or whitespace,
        both services consistently fall back to DJANGO_SECRET_KEY.
        """
        synthetic_django_secret = "synthetic-fallback-django-secret-33333"

        for idx, blank_jwt_val in enumerate([None, "", "   "]):
            token_str = self._create_django_token(
                signing_key=synthetic_django_secret,
                user_id='user-fallback-456',
                role='doctor',
                email='fallbackdoctor@example.com'
            )

            realtime_env = {
                'DJANGO_SECRET_KEY': synthetic_django_secret,
            }
            if blank_jwt_val is not None:
                realtime_env['JWT_SECRET_KEY'] = blank_jwt_val

            result = self._verify_token_with_realtime_middleware(token_str, realtime_env)

            self.assertTrue(
                result['success'],
                f"Verification failed for missing/blank JWT case index {idx}"
            )
            self.assertEqual(result['user']['id'], 'user-fallback-456')
            self.assertEqual(result['user']['role'], 'doctor')
            self.assertTrue(
                result.get('resolvedSecret') == synthetic_django_secret,
                f"Realtime middleware did not resolve to synthetic fallback secret for case index {idx}"
            )

    def test_both_secrets_missing_falls_back_to_default_insecure_key(self):
        """
        When neither JWT_SECRET_KEY nor DJANGO_SECRET_KEY is provided,
        both services consistently fall back to the default development key.
        """
        default_insecure_key = 'django-insecure-change-this-in-production'

        token_str = self._create_django_token(
            signing_key=default_insecure_key,
            user_id='default-user-789',
            role='patient',
            email='default@example.com'
        )

        realtime_env = {
            'DJANGO_SECRET_KEY': '',
            'JWT_SECRET_KEY': '',
        }
        result = self._verify_token_with_realtime_middleware(token_str, realtime_env)

        self.assertTrue(result['success'])
        self.assertTrue(
            result.get('resolvedSecret') == default_insecure_key,
            "Realtime middleware did not resolve to default development key when both secrets missing"
        )

    def test_settings_resolution_parity_between_django_and_node(self):
        """
        Directly checks that Django settings and Node getJwtSecret resolve
        identical keys under various combinations of environment variables.
        Failure diagnostics never expose the resolved secret strings.
        """
        test_cases = [
            # (django_val, jwt_val, expected_key)
            ("django-key-1", "jwt-key-1", "jwt-key-1"),
            ("django-key-2", "", "django-key-2"),
            ("django-key-3", "   ", "django-key-3"),
            ("django-key-4", None, "django-key-4"),
            ("", "", "django-insecure-change-this-in-production"),
            ("   ", "   ", "django-insecure-change-this-in-production"),
            (None, None, "django-insecure-change-this-in-production"),
        ]

        for idx, (d_val, j_val, expected) in enumerate(test_cases):
            env = {}
            if d_val is not None:
                env['DJANGO_SECRET_KEY'] = d_val
            if j_val is not None:
                env['JWT_SECRET_KEY'] = j_val

            # Check Django (isolated from any disk .env)
            _, django_jwt_key = self._resolve_django_settings_key(env)
            self.assertTrue(
                django_jwt_key == expected,
                f"Django JWT signing key mismatch for case index {idx} "
                f"(django_provided={d_val is not None}, jwt_provided={j_val is not None})"
            )

            # Check Node
            node_script = "import { getJwtSecret } from './src/auth/middleware.js'; console.log(getJwtSecret());"
            node_env = os.environ.copy()
            node_env.pop('DJANGO_SECRET_KEY', None)
            node_env.pop('JWT_SECRET_KEY', None)
            node_env.update(env)

            proc = subprocess.run(
                ['node', '--input-type=module', '-e', node_script],
                cwd=str(self.realtime_dir),
                capture_output=True,
                text=True,
                env=node_env
            )
            self.assertEqual(
                proc.returncode, 0,
                f"Node getJwtSecret script failed with code {proc.returncode}"
            )
            node_key = proc.stdout.strip()
            self.assertTrue(
                node_key == expected,
                f"Node JWT secret mismatch for case index {idx} "
                f"(django_provided={d_val is not None}, jwt_provided={j_val is not None})"
            )

    def test_synthetic_local_dotenv_cannot_contaminate_resolution(self):
        """
        Regression test: Proves that a synthetic local .env file cannot contaminate
        settings resolution, even when present in the decouple search path.
        Preserves real developer credentials without touching or reading any local .env file.
        """
        contaminant_django = "contaminant-synthetic-django-key-99999"
        contaminant_jwt = "contaminant-synthetic-jwt-key-88888"
        default_fallback = "django-insecure-change-this-in-production"

        with tempfile.TemporaryDirectory() as tmpdir:
            synthetic_dotenv = Path(tmpdir) / ".env"
            with open(synthetic_dotenv, "w", encoding="utf-8") as f:
                f.write(f"DJANGO_SECRET_KEY={contaminant_django}\nJWT_SECRET_KEY={contaminant_jwt}\n")

            # 1. Verify that without decouple isolation, python-decouple WOULD load the contaminant
            unisolated_code = (
                "import sys; sys.path.insert(0, 'backend'); "
                "import decouple; "
                f"decouple.config.search_path = {repr(tmpdir)}; "
                "import os; os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'; "
                "from django.conf import settings; import json; "
                "print(json.dumps({'SECRET_KEY': settings.SECRET_KEY, 'JWT_SIGNING_KEY': settings.SIMPLE_JWT['SIGNING_KEY']}))"
            )
            proc_uniso = subprocess.run(
                [sys.executable, "-c", unisolated_code],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                env={k: v for k, v in os.environ.items() if k not in ('DJANGO_SECRET_KEY', 'JWT_SECRET_KEY')}
            )
            self.assertEqual(proc_uniso.returncode, 0)
            uniso_data = json.loads(proc_uniso.stdout.strip())
            self.assertTrue(
                uniso_data['SECRET_KEY'] == contaminant_django,
                "Sanity check: unisolated decouple should load synthetic .env when search_path points to it"
            )

            # 2. Verify that WITH our isolated settings resolution, the contaminant .env is completely ignored
            # Case A: Missing keys in env_vars must resolve to default fallback, not the contaminant in .env
            resolved_django, resolved_jwt = self._resolve_django_settings_key(
                env_vars={},
                synthetic_search_path=tmpdir
            )
            self.assertFalse(
                resolved_django == contaminant_django,
                "Contamination detected: Django SECRET_KEY loaded contaminant from synthetic .env"
            )
            self.assertFalse(
                resolved_jwt == contaminant_jwt,
                "Contamination detected: Django JWT_SIGNING_KEY loaded contaminant from synthetic .env"
            )
            self.assertTrue(
                resolved_django == default_fallback,
                "Isolated Django SECRET_KEY did not resolve to default development fallback"
            )
            self.assertTrue(
                resolved_jwt == default_fallback,
                "Isolated Django JWT_SIGNING_KEY did not resolve to default development fallback"
            )

            # Case B: Explicit synthetic env vars take precedence and are not contaminated by .env
            explicit_django = "synthetic-explicit-django-secret"
            explicit_jwt = "synthetic-explicit-jwt-secret"
            resolved_django_exp, resolved_jwt_exp = self._resolve_django_settings_key(
                env_vars={'DJANGO_SECRET_KEY': explicit_django, 'JWT_SECRET_KEY': explicit_jwt},
                synthetic_search_path=tmpdir
            )
            self.assertTrue(
                resolved_django_exp == explicit_django,
                "Explicit DJANGO_SECRET_KEY mismatch under synthetic .env search path"
            )
            self.assertTrue(
                resolved_jwt_exp == explicit_jwt,
                "Explicit JWT_SECRET_KEY mismatch under synthetic .env search path"
            )

    def test_docker_compose_environment_wiring(self):
        """
        Validates that docker-compose.yml properly wires DJANGO_SECRET_KEY and JWT_SECRET_KEY
        to backend, celery_worker, celery_beat, and realtime services.
        """
        compose_path = self.repo_root / 'docker-compose.yml'
        self.assertTrue(compose_path.exists(), "docker-compose.yml not found")

        with open(compose_path, 'r', encoding='utf-8') as f:
            compose_cfg = yaml.safe_load(f)

        services = compose_cfg.get('services', {})
        expected_services = ['backend', 'celery_worker', 'celery_beat', 'realtime']

        for svc_name in expected_services:
            self.assertIn(svc_name, services, f"Service '{svc_name}' missing from docker-compose.yml")
            env_list = services[svc_name].get('environment', [])

            env_dict = {}
            if isinstance(env_list, list):
                for item in env_list:
                    if '=' in item:
                        k, v = item.split('=', 1)
                        env_dict[k] = v
            elif isinstance(env_list, dict):
                env_dict = env_list

            self.assertIn(
                'DJANGO_SECRET_KEY', env_dict,
                f"Service '{svc_name}' missing DJANGO_SECRET_KEY forwarding in docker-compose.yml"
            )
            self.assertIn(
                'JWT_SECRET_KEY', env_dict,
                f"Service '{svc_name}' missing JWT_SECRET_KEY forwarding in docker-compose.yml"
            )
            self.assertEqual(
                env_dict['DJANGO_SECRET_KEY'],
                '${DJANGO_SECRET_KEY:-django-insecure-change-this-in-production}'
            )
            self.assertEqual(
                env_dict['JWT_SECRET_KEY'],
                '${JWT_SECRET_KEY:-}'
            )

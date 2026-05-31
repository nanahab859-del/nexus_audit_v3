"""Tests for plugins.security.django_settings_plugin module."""

import pytest
from plugins.security.django_settings_plugin import DjangoSettingsPlugin
from core.events import EventBus
from core.models import Severity


@pytest.fixture
def plugin():
    """Create a DjangoSettingsPlugin instance."""
    return DjangoSettingsPlugin()


@pytest.fixture
async def event_bus():
    """Create an EventBus instance."""
    return EventBus()


@pytest.mark.asyncio
async def test_django_settings_plugin_metadata(plugin):
    """Test plugin metadata."""
    assert plugin.name == "django_settings"
    assert "python" in plugin.languages
    assert plugin.requires_ai is False


@pytest.mark.asyncio
async def test_find_settings_file_not_django(tmp_path, plugin):
    """Test that non-Django projects return None."""
    settings_path = plugin._find_settings_file(tmp_path)
    assert settings_path is None


@pytest.mark.asyncio
async def test_find_settings_file_root_level(tmp_path, plugin):
    """Test finding settings.py at root level."""
    # Create manage.py and settings.py
    (tmp_path / "manage.py").touch()
    (tmp_path / "settings.py").touch()

    settings_path = plugin._find_settings_file(tmp_path)
    assert settings_path is not None
    assert settings_path.name == "settings.py"


@pytest.mark.asyncio
async def test_find_settings_file_config_dir(tmp_path, plugin):
    """Test finding settings.py in config directory."""
    # Create manage.py and config/settings.py
    (tmp_path / "manage.py").touch()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.py").touch()

    settings_path = plugin._find_settings_file(tmp_path)
    assert settings_path is not None
    assert "config" in str(settings_path)


@pytest.mark.asyncio
async def test_parse_settings_basic(tmp_path, plugin):
    """Test parsing basic settings."""
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("""
SECRET_KEY = 'django-insecure-test-key-1234567890'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
""")

    settings_dict = plugin._parse_settings(settings_file)

    assert "SECRET_KEY" in settings_dict
    assert settings_dict["DEBUG"] is True
    assert "localhost" in settings_dict["ALLOWED_HOSTS"]


@pytest.mark.asyncio
async def test_parse_settings_complex(tmp_path, plugin):
    """Test parsing settings with complex expressions (should skip them)."""
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("""
SECRET_KEY = 'test'
DEBUG = os.getenv('DEBUG', False)  # Complex expression
ALLOWED_HOSTS = []
""")

    settings_dict = plugin._parse_settings(settings_file)

    # Simple values should be parsed
    assert "SECRET_KEY" in settings_dict
    assert "DEBUG" not in settings_dict  # Complex expression skipped
    assert "ALLOWED_HOSTS" in settings_dict


@pytest.mark.asyncio
async def test_check_secret_key_missing(tmp_path, plugin):
    """Test finding missing SECRET_KEY."""
    findings = plugin._check_secret_key(tmp_path / "settings.py", {})

    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL
    assert "SECRET_KEY" in findings[0].title


@pytest.mark.asyncio
async def test_check_secret_key_weak(tmp_path, plugin):
    """Test finding weak SECRET_KEY."""
    findings = plugin._check_secret_key(tmp_path / "settings.py", {
        "SECRET_KEY": "short"
    })

    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH


@pytest.mark.asyncio
async def test_check_secret_key_strong(tmp_path, plugin):
    """Test that strong SECRET_KEY passes."""
    findings = plugin._check_secret_key(tmp_path / "settings.py", {
        "SECRET_KEY": "a" * 50  # 50 character key
    })

    assert len(findings) == 0


@pytest.mark.asyncio
async def test_check_debug_mode_enabled(tmp_path, plugin):
    """Test finding DEBUG=True."""
    findings = plugin._check_debug_mode(tmp_path / "settings.py", {
        "DEBUG": True
    })

    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert "DEBUG" in findings[0].title


@pytest.mark.asyncio
async def test_check_debug_mode_disabled(tmp_path, plugin):
    """Test that DEBUG=False passes."""
    findings = plugin._check_debug_mode(tmp_path / "settings.py", {
        "DEBUG": False
    })

    assert len(findings) == 0


@pytest.mark.asyncio
async def test_check_allowed_hosts_empty(tmp_path, plugin):
    """Test finding empty ALLOWED_HOSTS."""
    findings = plugin._check_allowed_hosts(tmp_path / "settings.py", {
        "ALLOWED_HOSTS": []
    })

    assert len(findings) == 1
    assert "ALLOWED_HOSTS" in findings[0].title


@pytest.mark.asyncio
async def test_check_allowed_hosts_wildcard(tmp_path, plugin):
    """Test finding wildcard ALLOWED_HOSTS."""
    findings = plugin._check_allowed_hosts(tmp_path / "settings.py", {
        "ALLOWED_HOSTS": ["*"]
    })

    assert len(findings) == 1
    assert "wildcard" in findings[0].title.lower()


@pytest.mark.asyncio
async def test_check_allowed_hosts_valid(tmp_path, plugin):
    """Test that valid ALLOWED_HOSTS passes."""
    findings = plugin._check_allowed_hosts(tmp_path / "settings.py", {
        "ALLOWED_HOSTS": ["example.com", "www.example.com"]
    })

    assert len(findings) == 0


@pytest.mark.asyncio
async def test_check_secure_ssl_redirect_disabled(tmp_path, plugin):
    """Test finding SECURE_SSL_REDIRECT not set."""
    findings = plugin._check_secure_ssl_redirect(tmp_path / "settings.py", {})

    assert len(findings) == 1
    assert "SECURE_SSL_REDIRECT" in findings[0].title


@pytest.mark.asyncio
async def test_check_secure_ssl_redirect_enabled(tmp_path, plugin):
    """Test that SECURE_SSL_REDIRECT=True passes."""
    findings = plugin._check_secure_ssl_redirect(tmp_path / "settings.py", {
        "SECURE_SSL_REDIRECT": True
    })

    assert len(findings) == 0


@pytest.mark.asyncio
async def test_scan_no_django_project(tmp_path, event_bus):
    """Test scan on non-Django project."""
    plugin = DjangoSettingsPlugin()
    findings = await plugin.scan(tmp_path, {}, event_bus)

    # Should return empty list for non-Django project
    assert findings == []


@pytest.mark.asyncio
async def test_scan_django_insecure(tmp_path, event_bus):
    """Test scan on insecure Django project."""
    # Create minimal Django project
    (tmp_path / "manage.py").touch()
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("""
SECRET_KEY = 'insecure'
DEBUG = True
ALLOWED_HOSTS = []
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
""")

    plugin = DjangoSettingsPlugin()
    findings = await plugin.scan(tmp_path, {}, event_bus)

    # Should find multiple security issues
    assert len(findings) > 0
    # Should find HIGH severity issues
    assert any(f.severity == Severity.HIGH for f in findings)


@pytest.mark.asyncio
async def test_scan_django_secure(tmp_path, event_bus):
    """Test scan on secure Django project."""
    # Create minimal Django project with secure settings
    (tmp_path / "manage.py").touch()
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("""
SECRET_KEY = 'django-insecure-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
DEBUG = False
ALLOWED_HOSTS = ['example.com']
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True
""")

    plugin = DjangoSettingsPlugin()
    findings = await plugin.scan(tmp_path, {}, event_bus)

    # Secure settings should have few or no findings
    # (might have some LOW severity ones, but no CRITICAL or HIGH)
    critical_high = [f for f in findings if f.severity in {Severity.CRITICAL, Severity.HIGH}]
    assert len(critical_high) == 0

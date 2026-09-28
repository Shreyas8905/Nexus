from app.config import Settings, get_settings


def test_default_settings():
    settings = Settings()
    assert settings.app_env == "development"
    assert "placeholder" in settings.jwt_secret


def test_get_settings_loader():
    settings = get_settings()
    assert settings is not None
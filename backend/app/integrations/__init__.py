from app.integrations.base import IntegrationProvider

_registry: dict[str, IntegrationProvider] = {}


def register_provider(provider: IntegrationProvider) -> IntegrationProvider:
    """Register a provider instance. Can be used as a decorator on provider classes."""
    _registry[provider.name] = provider
    return provider


def get_provider(name: str) -> IntegrationProvider:
    """Get a registered provider by name. Raises KeyError if not found."""
    if name not in _registry:
        raise KeyError(f"Unknown integration provider: {name!r}. Available: {list(_registry.keys())}")
    return _registry[name]


def list_providers() -> list[IntegrationProvider]:
    """Return all registered providers."""
    return list(_registry.values())

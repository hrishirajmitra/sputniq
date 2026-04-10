"""Custom errors for configuration processing."""

class ConfigError(Exception):
    """Base class for configuration errors."""
    pass

class ConfigLoadError(ConfigError):
    """Raised when the config file cannot be loaded or parsed."""
    pass

class ReferenceError(ConfigError):
    """Raised when an entity references a non-existent ID."""
    pass

class CyclicDependencyError(ConfigError):
    """Raised when a circular reference is found in workflows."""
    pass

class ValidationError(ConfigError):
    """Raised when the configuration content is invalid."""
    pass


class BuildValidationError(ValidationError):
    """Raised when build-time code analysis fails."""
    pass

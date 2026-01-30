"""
Custom exceptions for Pokemon Gen 3 module.

Provides specific exception types for better error handling and debugging
instead of catching generic Exception everywhere.
"""


class PokemonGen3Error(Exception):
    """Base exception for Pokemon Gen 3 module."""
    pass


class StateDetectorError(PokemonGen3Error):
    """Error during game state detection."""
    pass


class PointerInvalidError(StateDetectorError):
    """
    Raised when save block pointers are invalid.

    This typically happens at title screen before game is loaded,
    or during DMA operations that shift memory.
    """
    pass


class MemoryReadError(StateDetectorError):
    """
    Raised when memory read fails.

    Could indicate connection issues with mGBA-http or
    invalid memory address.
    """
    pass


class BattleHandlerError(PokemonGen3Error):
    """Error during battle handling."""
    pass


class IntroHandlerError(PokemonGen3Error):
    """Error during intro sequence handling."""
    pass


class DataManagerError(PokemonGen3Error):
    """Error loading or accessing game data."""
    pass


class ObjectiveDetectorError(PokemonGen3Error):
    """Error during objective completion detection."""
    pass

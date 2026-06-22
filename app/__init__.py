"""Natural-language-to-SQL assistant over a sample hospital/clinic database.

The package is intentionally split so that the security-critical and
retrieval logic (``validator``, ``retrieval``, ``embeddings``,
``mock_responses``) have **no heavy third-party dependencies** and can be
imported and unit-tested on their own, without Chainlit, ChromaDB, torch or a
database connection.
"""

__all__ = ["__version__"]
__version__ = "1.0.0"

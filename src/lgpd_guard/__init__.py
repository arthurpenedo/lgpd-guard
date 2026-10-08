"""lgpd-guard: detecta e pseudonimiza dados pessoais brasileiros antes de mandar texto para um LLM."""

from .detector import Detector
from .entidades import TIPOS, Entidade
from .pseudonimizador import Cofre, Pseudonimizador

__version__ = "0.1.0"
__all__ = ["TIPOS", "Cofre", "Detector", "Entidade", "Pseudonimizador"]

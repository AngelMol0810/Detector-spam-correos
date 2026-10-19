"""
clases/bandeja.py
Módulo con la definición de la clase Bandeja.
"""

from clases.reglas import Correo


class Bandeja:
    """Almacena los correos y responde consultas."""

    def __init__(self):
        self.__correos = []

    @property
    def correos(self):
        return list(self.__correos)

    def agregar(self, correo):
        """Agrega un correo. Solo acepta objetos Correo."""
        if not isinstance(correo, Correo):
            raise TypeError("Solo se pueden agregar objetos Correo")
        self.__correos.append(correo)

    def listar_spam(self):
        return [c for c in self.__correos if c.es_spam]

    def listar_normales(self):
        return [c for c in self.__correos if not c.es_spam]

    def resumen(self):
        """Devuelve un diccionario con las estadísticas de la bandeja."""
        total = len(self.__correos)
        spam = len(self.listar_spam())
        return {
            "total": total,
            "spam": spam,
            "normales": total - spam,
            "porcentaje_spam": round(spam / total * 100, 1) if total else 0.0,
        }

    def __len__(self):
        return len(self.__correos)
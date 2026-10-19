"""
clases/bandeja.py
Módulo con la definición de la clase Bandeja.
"""

from clases.correo import Correo


class Bandeja:
    """Administra una lista de correos procesados."""

    def __init__(self):
        self.__correos = []

    @property
    def correos(self):
        return list(self.__correos)

    def agregar(self, correo):
        if not isinstance(correo, Correo):
            raise TypeError("Solo se pueden agregar objetos Correo")
        self.__correos.append(correo)

    def listar_spam(self):
        return [c for c in self.__correos if c.es_spam]

    def listar_normales(self):
        return [c for c in self.__correos if not c.es_spam]

    def resumen(self):
        total = len(self.__correos)
        spam = len(self.listar_spam())
        normales = total - spam
        return f"Total: {total} | Spam: {spam} | Normales: {normales}"

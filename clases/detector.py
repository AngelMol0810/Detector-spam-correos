"""
clases/detectorspam.py
Módulo con la definición de la clase DetectorSpam.
"""

from clases.correo import Correo
from clases.reglas import Regla


class DetectorSpam:
    """Contiene una lista de reglas y decide si un correo es spam."""

    def __init__(self, umbral=5):
        self.__reglas = []
        self.__umbral = umbral

    @property
    def umbral(self):
        return self.__umbral

    @umbral.setter
    def umbral(self, valor):
        if valor <= 0:
            raise ValueError("El umbral debe ser mayor que 0")
        self.__umbral = valor

    @property
    def reglas(self):
        return list(self.__reglas)

    def agregar_regla(self, regla):
        """Agrega una regla. Cualquier objeto que herede de Regla sirve."""
        if not isinstance(regla, Regla):
            raise TypeError("Solo se pueden agregar objetos Regla")
        self.__reglas.append(regla)

    def analizar(self, correo):
        """Evalúa el correo con todas las reglas y lo marca si supera el umbral."""
        correo.limpiar_motivos()
        total = 0
        for regla in self.__reglas:
            puntaje, motivo = regla.evaluar(correo)
            total += puntaje
            if motivo:
                correo.agregar_motivo(motivo)

        correo.puntaje = total
        if total >= self.__umbral:
            correo.marcar_como_spam()
        else:
            correo.marcar_como_normal()
        return correo.es_spam

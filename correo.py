import re


class Correo:
    """Un correo con sus datos y el resultado del análisis de spam.

    Los atributos son privados (encapsulamiento). Se leen mediante propiedades
    y el puntaje se valida en su setter.
    """

    def __init__(self, remitente, asunto, cuerpo):
        self.__remitente = remitente
        self.__asunto = asunto
        self.__cuerpo = cuerpo
        self.__puntaje = 0
        self.__es_spam = False
        self.__motivos = []

    @property
    def remitente(self):
        return self.__remitente

    @property
    def asunto(self):
        return self.__asunto

    @property
    def cuerpo(self):
        return self.__cuerpo

    @property
    def puntaje(self):
        return self.__puntaje

    @puntaje.setter
    def puntaje(self, valor):
        if valor < 0:
            raise ValueError("El puntaje no puede ser negativo")
        self.__puntaje = valor

    @property
    def es_spam(self):
        return self.__es_spam

    @property
    def motivos(self):
        # Devuelve una copia para no exponer la lista interna
        return list(self.__motivos)

    def agregar_motivo(self, motivo):
        """Registra por qué una regla sospechó de este correo."""
        self.__motivos.append(motivo)

    def limpiar_motivos(self):
        """Borra los motivos de un análisis anterior."""
        self.__motivos.clear()

    def marcar_como_spam(self):
        self.__es_spam = True

    def marcar_como_normal(self):
        self.__es_spam = False

    def __str__(self):
        estado = "SPAM" if self.__es_spam else "NORMAL"
        return f"[{estado}] ({self.__puntaje} pts) {self.__remitente} - {self.__asunto}"

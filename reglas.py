import re
import unicodedata
from abc import ABC, abstractmethod


def normalizar(texto):
    """Pasa a minúsculas y quita tildes, para que 'PREMIÓ' y 'premio' coincidan."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


class Regla(ABC):
    """Clase base abstracta: cada regla aporta puntos de sospecha a un correo.

    Es abstracta porque no tiene sentido crear una 'Regla' genérica: solo se
    usan sus hijas. Cada hija DEBE implementar ``evaluar`` (polimorfismo).
    """

    def __init__(self, nombre, peso):
        if peso <= 0:
            raise ValueError("El peso de una regla debe ser positivo")
        self.__nombre = nombre
        self.__peso = peso

    @property
    def nombre(self):
        return self.__nombre

    @property
    def peso(self):
        return self.__peso

    def _reportar(self, correo, detalle):
        """Registra en el correo por qué esta regla sospechó de él."""
        correo.agregar_motivo(f"{self.nombre}: {detalle}")

    @abstractmethod
    def evaluar(self, correo):
        """Recibe un Correo y devuelve los puntos que aporta (0 si no se cumple)."""

    def __str__(self):
        return f"{self.nombre} (peso {self.peso})"


class ReglaPalabrasClave(Regla):
    """Suma ``peso`` por cada palabra sospechosa distinta (acepta plurales)."""

    PALABRAS_POR_DEFECTO = ("gratis", "premio", "urgente", "ganaste", "oferta")

    def __init__(self, palabras=None, peso=2):
        super().__init__("Palabras clave", peso)
        self.__palabras = tuple(palabras or self.PALABRAS_POR_DEFECTO)

    def evaluar(self, correo):
        texto = normalizar(f"{correo.asunto} {correo.cuerpo}")
        encontradas = [
            p for p in self.__palabras
            if re.search(rf"\b{re.escape(normalizar(p))}\w*", texto)
        ]
        if not encontradas:
            return 0
        self._reportar(correo, f"contiene {', '.join(encontradas)}")
        return len(encontradas) * self.peso


class ReglaRemitente(Regla):
    """El dominio del remitente está en una lista negra (incluye subdominios)."""

    LISTA_NEGRA_POR_DEFECTO = ("promo-ya.com", "ganadores.net", "gratis.xyz")

    def __init__(self, lista_negra=None, peso=5):
        super().__init__("Remitente sospechoso", peso)
        self.__lista_negra = tuple(d.lower() for d in (lista_negra or self.LISTA_NEGRA_POR_DEFECTO))

    def evaluar(self, correo):
        dominio = correo.remitente.split("@")[-1].lower()
        for bloqueado in self.__lista_negra:
            # igual al dominio, o subdominio (mail.promo-ya.com); NO 'xpromo-ya.com'
            if dominio == bloqueado or dominio.endswith("." + bloqueado):
                self._reportar(correo, f"remitente en lista negra ({bloqueado})")
                return self.peso
        return 0


class ReglaEnlaces(Regla):
    """El cuerpo del correo tiene demasiados enlaces."""

    def __init__(self, max_enlaces=2, peso=2):
        super().__init__("Enlaces", peso)
        self.__max_enlaces = max_enlaces

    def evaluar(self, correo):
        enlaces = re.findall(r"https?://\S+", correo.cuerpo, flags=re.IGNORECASE)
        if len(enlaces) > self.__max_enlaces:
            self._reportar(correo, f"tiene {len(enlaces)} enlaces")
            return self.peso
        return 0


class ReglaMayusculas(Regla):
    """El asunto está en mayúsculas o tiene muchos signos de exclamación."""

    def __init__(self, peso=3):
        super().__init__("Mayúsculas y exclamaciones", peso)

    def evaluar(self, correo):
        asunto = correo.asunto
        letras = [c for c in asunto if c.isalpha()]
        motivos = []
        if len(letras) > 3 and asunto.isupper():
            motivos.append("asunto en mayúsculas")
        if asunto.count("!") >= 3:
            motivos.append("muchos signos de exclamación")
        if not motivos:
            return 0
        self._reportar(correo, ", ".join(motivos))
        return self.peso

import math
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

    @abstractmethod
    def evaluar(self, correo):
        """Recibe un Correo y devuelve la tupla (puntaje, motivo).

        Si la regla no se cumple devuelve (0, "").
        """

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
            return 0, ""
        return len(encontradas) * self.peso, f"{self.nombre}: contiene {', '.join(encontradas)}"


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
                return self.peso, f"{self.nombre}: remitente en lista negra ({bloqueado})"
        return 0, ""


class ReglaEnlaces(Regla):
    """El cuerpo del correo tiene demasiados enlaces."""

    def __init__(self, max_enlaces=2, peso=2):
        super().__init__("Enlaces", peso)
        self.__max_enlaces = max_enlaces

    def evaluar(self, correo):
        enlaces = re.findall(r"https?://\S+", correo.cuerpo, flags=re.IGNORECASE)
        if len(enlaces) > self.__max_enlaces:
            return self.peso, f"{self.nombre}: tiene {len(enlaces)} enlaces"
        return 0, ""


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
            return 0, ""
        return self.peso, f"{self.nombre}: {', '.join(motivos)}"


class ReglaNaiveBayes(Regla):
    """Regla opcional que APRENDE de ejemplos (Naive Bayes multinomial básico).

    Antes de entrenar (o si solo vio spam o solo normales) no opina: devuelve
    (0, ""). Una vez entrenada, si la probabilidad de spam del correo es
    mayor o igual que ``umbral_prob``, suma ``peso`` puntos como cualquier
    otra regla.
    """

    def __init__(self, peso=3, umbral_prob=0.5, alfa=1.0):
        super().__init__("Naive Bayes", peso)
        if not 0 < umbral_prob < 1:
            raise ValueError("umbral_prob debe estar entre 0 y 1")
        if alfa <= 0:
            raise ValueError("alfa debe ser mayor que 0")
        self.__umbral_prob = umbral_prob
        self.__alfa = alfa                           # suavizado de Laplace
        self.__n_correos = {True: 0, False: 0}       # correos vistos por clase
        self.__total_palabras = {True: 0, False: 0}  # palabras vistas por clase
        self.__frecuencias = {True: {}, False: {}}   # palabra -> veces, por clase
        self.__vocabulario = set()

    @property
    def entrenada(self):
        """True si ya vio al menos un correo spam y uno normal."""
        return self.__n_correos[True] > 0 and self.__n_correos[False] > 0

    def __palabras(self, correo):
        texto = normalizar(f"{correo.asunto} {correo.cuerpo}")
        return [p for p in re.findall(r"[a-z0-9]+", texto) if len(p) >= 3]

    def entrenar(self, ejemplos):
        """Aprende de una lista de pares (correo, es_spam). Se puede llamar varias veces."""
        for correo, es_spam in ejemplos:
            clase = bool(es_spam)
            self.__n_correos[clase] += 1
            for palabra in self.__palabras(correo):
                self.__frecuencias[clase][palabra] = self.__frecuencias[clase].get(palabra, 0) + 1
                self.__total_palabras[clase] += 1
                self.__vocabulario.add(palabra)

    def probabilidad_spam(self, correo):
        """Devuelve P(spam | correo) entre 0 y 1 (0.5 si aún no está entrenada)."""
        if not self.entrenada:
            return 0.5
        total_correos = self.__n_correos[True] + self.__n_correos[False]
        tamano_vocabulario = len(self.__vocabulario)
        log_prob = {}
        for clase in (True, False):
            lp = math.log(self.__n_correos[clase] / total_correos)
            denominador = self.__total_palabras[clase] + self.__alfa * tamano_vocabulario
            for palabra in self.__palabras(correo):
                if palabra in self.__vocabulario:
                    veces = self.__frecuencias[clase].get(palabra, 0)
                    lp += math.log((veces + self.__alfa) / denominador)
            log_prob[clase] = lp
        diferencia = max(-700, min(700, log_prob[False] - log_prob[True]))
        return 1 / (1 + math.exp(diferencia))

    def evaluar(self, correo):
        if not self.entrenada:
            return 0, ""
        prob = self.probabilidad_spam(correo)
        if prob >= self.__umbral_prob:
            return self.peso, f"{self.nombre}: probabilidad de spam {prob:.0%}"
        return 0, ""

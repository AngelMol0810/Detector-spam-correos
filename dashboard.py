import os
import sys
import math
import re
import unicodedata
from abc import ABC, abstractmethod
import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.express as px
import pandas as pd

# Se agrega la carpeta 'clases' a la ruta de búsqueda de Python
# Así correo.py, reglas.py, detector.py y bandeja.py se encuentran entre sí sin errores
RUTA_CLASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clases")
if RUTA_CLASES not in sys.path:
    sys.path.insert(0, RUTA_CLASES)


# =========================================================================
# 1. IMPORTACIÓN SEGURA
# =========================================================================
try:
    from correo import Correo
    from reglas import (
        Regla,
        ReglaPalabrasClave,
        ReglaRemitente,
        ReglaEnlaces,
        ReglaMayusculas,
        ReglaNaiveBayes,
    )
    from detector import DetectorSpam
    from bandeja import Bandeja
except ImportError:
    from correo import Correo

    def normalizar(texto):
        descompuesto = unicodedata.normalize("NFD", texto.lower())
        return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")

    class Regla(ABC):
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
            pass

        def __str__(self):
            return f"{self.nombre} (peso {self.peso})"

    class ReglaPalabrasClave(Regla):
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
        LISTA_NEGRA_POR_DEFECTO = ("promo-ya.com", "ganadores.net", "gratis.xyz")

        def __init__(self, lista_negra=None, peso=5):
            super().__init__("Remitente sospechoso", peso)
            self.__lista_negra = tuple(d.lower() for d in (lista_negra or self.LISTA_NEGRA_POR_DEFECTO))

        def evaluar(self, correo):
            dominio = correo.remitente.split("@")[-1].lower()
            for bloqueado in self.__lista_negra:
                if dominio == bloqueado or dominio.endswith("." + bloqueado):
                    return self.peso, f"{self.nombre}: remitente en lista negra ({bloqueado})"
            return 0, ""

    class ReglaEnlaces(Regla):
        def __init__(self, max_enlaces=2, peso=2):
            super().__init__("Enlaces", peso)
            self.__max_enlaces = max_enlaces

        def evaluar(self, correo):
            enlaces = re.findall(r"https?://\S+", correo.cuerpo, flags=re.IGNORECASE)
            if len(enlaces) > self.__max_enlaces:
                return self.peso, f"{self.nombre}: tiene {len(enlaces)} enlaces"
            return 0, ""

    class ReglaMayusculas(Regla):
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
        def __init__(self, peso=3, umbral_prob=0.5, alfa=1.0):
            super().__init__("Naive Bayes", peso)
            if not 0 < umbral_prob < 1:
                raise ValueError("umbral_prob debe estar entre 0 y 1")
            if alfa <= 0:
                raise ValueError("alfa debe ser mayor que 0")
            self.__umbral_prob = umbral_prob
            self.__alfa = alfa
            self.__n_correos = {True: 0, False: 0}
            self.__total_palabras = {True: 0, False: 0}
            self.__frecuencias = {True: {}, False: {}}
            self.__vocabulario = set()

        @property
        def entrenada(self):
            return self.__n_correos[True] > 0 and self.__n_correos[False] > 0

        def __palabras(self, correo):
            texto = normalizar(f"{correo.asunto} {correo.cuerpo}")
            return [p for p in re.findall(r"[a-z0-9]+", texto) if len(p) >= 3]

        def entrenar(self, ejemplos):
            for correo, es_spam in ejemplos:
                clase = bool(es_spam)
                self.__n_correos[clase] += 1
                for palabra in self.__palabras(correo):
                    self.__frecuencias[clase][palabra] = self.__frecuencias[clase].get(palabra, 0) + 1
                    self.__total_palabras[clase] += 1
                    self.__vocabulario.add(palabra)

        def probabilidad_spam(self, correo):
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

    class DetectorSpam:
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
            if not isinstance(regla, Regla):
                raise TypeError("Solo se pueden agregar objetos Regla")
            self.__reglas.append(regla)

        def analizar(self, correo):
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

    class Bandeja:
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
            return {
                "total": total,
                "spam": spam,
                "normales": total - spam,
                "porcentaje_spam": round(spam / total * 100, 1) if total else 0.0,
            }

        def __len__(self):
            return len(self.__correos)


# =========================================================================
# 2. INICIALIZACIÓN DE OBJETOS Y DATOS
# =========================================================================
def ejemplos_de_entrenamiento():
    spam = [
        ("promos@ofertas-ya.com", "Gana dinero rápido", "Haz clic ahora y gana dinero rápido sin esfuerzo"),
        ("sorteo@ganadores.net", "Felicidades, ganaste el sorteo", "Reclama ahora tu premio del sorteo exclusivo"),
        ("ventas@descuentos.com", "Oferta limitada", "Descuento exclusivo compra ya la oferta limitada"),
        ("seguridad@banco-falso.com", "Tu cuenta fue bloqueada", "Verifica urgente tu cuenta bloqueada haz clic"),
        ("prestamos@credito-facil.com", "Préstamo inmediato", "Préstamo inmediato sin requisitos solicita ahora"),
        ("info@gratis.xyz", "Suscríbete gratis", "Promoción gratis suscríbete ahora y gana un premio"),
    ]
    normales = [
        ("profe@lamolina.edu.pe", "Revisión del informe", "Adjunto la rúbrica de evaluación del informe del curso"),
        ("jefe@empresa.pe", "Reunión de coordinación", "La reunión del equipo será mañana para revisar el avance"),
        ("secretaria@lamolina.edu.pe", "Horario de laboratorio", "Te comparto el horario del laboratorio de programación"),
        ("amigo@correo.com", "Avance del trabajo grupal", "Terminé mi parte del trabajo grupal, revisa el código"),
        ("notas@lamolina.edu.pe", "Notas del curso", "Ya están publicadas las notas de la práctica del curso"),
        ("familia@correo.com", "Cena del domingo", "Nos vemos el domingo en casa para almorzar en familia"),
    ]
    return ([(Correo(*datos), True) for datos in spam]
            + [(Correo(*datos), False) for datos in normales])


detector = DetectorSpam(umbral=5)
bayes = ReglaNaiveBayes(peso=3, umbral_prob=0.6)
for regla in (ReglaPalabrasClave(), ReglaRemitente(), ReglaEnlaces(), ReglaMayusculas(), bayes):
    detector.agregar_regla(regla)
bayes.entrenar(ejemplos_de_entrenamiento())

bandeja = Bandeja()


correos_ejemplo = [
    Correo("ventas@promo-ya.com", "¡¡¡GANASTE UN PREMIO GRATIS!!!",
           "Haz clic: http://a.co http://b.co http://c.co"),
    Correo("info@ganadores.net", "URGENTE: reclama tu premio",
           "Has sido seleccionado. Reclama aquí: http://premio.co/a http://premio.co/b"),
    Correo("profe.vargas@lamolina.edu.pe", "Revisión del informe",
           "Adjunto la rúbrica de evaluación del trabajo grupal."),
    Correo("compa@correo.com", "Reunión del grupo 5",
           "Nos vemos mañana para avanzar con el informe de POO."),
    Correo("soporte@tienda.com", "Oferta de temporada",
           "Descuento en tu próxima compra."),
    Correo("secretaria@lamolina.edu.pe", "URGENTE: confirma tu asistencia",
           "Necesitamos confirmar tu asistencia a la reunión de coordinación."),
    Correo("boletin@mail.promo-ya.com", "Boletín semanal",
           "Resumen de novedades de la semana."),
    Correo("hola@xpromo-ya.com", "Boletín semanal",
           "Resumen de novedades de la semana."),
    Correo("ventas@tiendaperu.com", "Ofertas gratis esta semana",
           "Visita nuestra tienda: http://tienda.pe"),
]

for c in correos_ejemplo:
    bandeja.agregar(c)
    detector.analizar(c)


def obtener_lista_correos():
    """Compatible tanto con bandeja.correos (Primer Archivo) como bandeja.todos()."""
    return bandeja.correos if hasattr(bandeja, "correos") else bandeja.todos()


def obtener_texto_resumen():
    """Compatible tanto si resumen() devuelve dict (Primer Archivo) como si devuelve str."""
    r = bandeja.resumen()
    if isinstance(r, dict):
        return f"Total: {r['total']} | Spam: {r['spam']} | Normales: {r['normales']} | % spam: {r['porcentaje_spam']}%"
    return str(r)


def construir_dataframe():
    registros = []
    for c in obtener_lista_correos():
        registros.append({
            "Remitente": c.remitente,
            "Asunto": c.asunto,
            "Puntaje": c.puntaje,
            "Estado": "SPAM" if c.es_spam else "NORMAL",
            "Motivos": " | ".join(c.motivos) if c.motivos else "Ninguno"
        })
    return pd.DataFrame(registros)


# =========================================================================
# 3. INTERFAZ DEL DASHBOARD EN DASH
# =========================================================================
app = dash.Dash(__name__)

app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif', 'maxWidth': '1100px', 'margin': 'auto', 'padding': '20px'}, children=[
    html.H1("Simulador de Detector de Spam - Grupo 5", style={'textAlign': 'center', 'color': '#1f3a52'}),
    html.P(id='texto-resumen', style={'textAlign': 'center', 'fontSize': '18px', 'fontWeight': 'bold', 'color': '#2c3e50'}),
    html.Hr(),

    html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}, children=[
        html.Div(style={'flex': '2', 'backgroundColor': '#f4f6f7', 'padding': '15px', 'borderRadius': '8px'}, children=[
            html.H3("1. Agregar y Analizar Correo"),
            html.Label("Remitente:"),
            dcc.Input(id='in-remitente', type='text', placeholder='ej. premios@promo-ya.com', style={'width': '98%', 'marginBottom': '8px', 'padding': '6px'}),
            html.Label("Asunto:"),
            dcc.Input(id='in-asunto', type='text', placeholder='ej. ¡¡¡OFERTA URGENTE!!!', style={'width': '98%', 'marginBottom': '8px', 'padding': '6px'}),
            html.Label("Cuerpo:"),
            dcc.Textarea(id='in-cuerpo', placeholder='Escribe el mensaje...', style={'width': '98%', 'height': '60px', 'marginBottom': '8px', 'padding': '6px'}),
            html.Button("Analizar Correo", id='btn-agregar', n_clicks=0,
                        style={'backgroundColor': '#2980b9', 'color': 'white', 'padding': '8px 16px', 'border': 'none', 'borderRadius': '4px', 'cursor': 'pointer'}),
            html.Div(id='alerta-nuevo', style={'marginTop': '10px', 'fontWeight': 'bold'})
        ]),

        html.Div(style={'flex': '1', 'backgroundColor': '#eef2f5', 'padding': '15px', 'borderRadius': '8px'}, children=[
            html.H3("2. Calibrar Umbral"),
            html.P("Cambia el umbral para re-analizar toda la bandeja automáticamente:"),
            dcc.Slider(id='slider-umbral', min=1, max=15, step=1, value=5,
                       marks={i: str(i) for i in range(1, 16, 2)}),
            html.Div(id='info-umbral', style={'marginTop': '15px', 'fontWeight': 'bold', 'color': '#c0392b'})
        ])
    ]),

    html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}, children=[
        html.Div(style={'flex': '1'}, children=[dcc.Graph(id='graf-pastel')]),
        html.Div(style={'flex': '1'}, children=[dcc.Graph(id='graf-barras')])
    ]),

    html.H3("Bandeja de Correos Analizados"),
    html.Div(id='contenedor-tabla')
])


@app.callback(
    [Output('graf-pastel', 'figure'),
     Output('graf-barras', 'figure'),
     Output('contenedor-tabla', 'children'),
     Output('texto-resumen', 'children'),
     Output('alerta-nuevo', 'children'),
     Output('info-umbral', 'children')],
    [Input('btn-agregar', 'n_clicks'),
     Input('slider-umbral', 'value')],
    [State('in-remitente', 'value'),
     State('in-asunto', 'value'),
     State('in-cuerpo', 'value')]
)
def actualizar_vista(n_clicks, nuevo_umbral, remitente, asunto, cuerpo):
    ctx = dash.callback_context
    disparador = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    mensaje_nuevo = ""

    detector.umbral = nuevo_umbral
    for c in obtener_lista_correos():
        detector.analizar(c)

    if disparador == 'btn-agregar' and remitente and asunto and cuerpo:
        if "@" not in remitente:
            mensaje_nuevo = "⚠️ Remitente inválido: debe contener '@'."
        else:
            nuevo = Correo(remitente, asunto, cuerpo)
            detector.analizar(nuevo)
            bandeja.agregar(nuevo)
            estado = "SPAM 🚨" if nuevo.es_spam else "NORMAL ✅"
            mensaje_nuevo = f"Correo agregado: {estado} ({nuevo.puntaje} pts)"

    df = construir_dataframe()

    fig_pie = px.pie(df, names='Estado', title='Distribución: Spam vs Normales',
                     color='Estado', color_discrete_map={'SPAM': '#e74c3c', 'NORMAL': '#2ecc71'})

    fig_bar = px.bar(df, x='Remitente', y='Puntaje', color='Estado',
                     hover_data=['Asunto', 'Motivos'],
                     title='Puntaje de Sospecha por Correo',
                     color_discrete_map={'SPAM': '#e74c3c', 'NORMAL': '#2ecc71'})
    fig_bar.add_hline(y=detector.umbral, line_dash="dash", line_color="black",
                      annotation_text=f"Umbral ({detector.umbral})")

    tabla = dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[{'name': col, 'id': col} for col in df.columns],
        style_cell={'textAlign': 'left', 'padding': '8px', 'whiteSpace': 'normal', 'height': 'auto'},
        style_header={'backgroundColor': '#1f3a52', 'color': 'white', 'fontWeight': 'bold'},
        style_data_conditional=[
            {'if': {'filter_query': '{Estado} = "SPAM"'}, 'backgroundColor': '#fadbd8', 'color': '#78281f'}
        ]
    )

    return (
        fig_pie,
        fig_bar,
        tabla,
        obtener_texto_resumen(),
        mensaje_nuevo,
        f"Umbral actual activo: {detector.umbral} puntos"
    )


if __name__ == '__main__':
    app.run(debug=True)
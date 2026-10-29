"""Utilidades compartidas por los scripts de la ficha del boletín.

Los importadores (`importar_fichas_docx.py`, `importar_morfometria.py`) y el
editor local (`editor_boletin.py`) leen y escriben `data/boletin.json`, que no
se toca desde `automatizar_volcanes.py`.
"""

import io
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RUTA_BOLETIN = RAIZ / "data" / "boletin.json"
RUTA_VOLCANES = RAIZ / "data" / "volcanes.geojson"

# Nombres de las fuentes (clave normalizada) que no coinciden con volcanes.geojson.
ALIAS = {
    "mellitoalto": "melito_alto",
    "molinillo": "volcan_vereda_molinillo",
}

TEXTO_MORFOLOGIA = (
    "Los volcanes de lodo del Caribe colombiano —incluida la región de Urabá— se "
    "manifiestan geomorfológicamente como “cerros en forma de domo de morfología "
    "colinada, de laderas convexas y cima plana o en artesa”, formados por la "
    "acumulación de lodos de erupciones previas y por deformación tectónica asociada "
    "al diapirismo de lodos (Servicio Geológico Colombiano, 2017, “Volcanismo de lodo "
    "del Caribe central colombiano”, DOI 10.32685/9789585978201). Esta descripción es "
    "general para el conjunto de volcanes de la región."
)

GENERAL_BASE = {
    "numero_boletin": "XXXXXXX",
    "red_social": "@DagranAntioquia",
    "morfologia": TEXTO_MORFOLOGIA,
    "morfologia_sin_datos": (
        "No se encontró en las fuentes consultadas una caracterización morfológica de "
        "campo (altura del domo, forma y diámetro del cráter, pendiente) específica y "
        "verificada para este volcán en particular."
    ),
    "nota_monitoreo": (
        "El Servicio Geológico Colombiano (SGC) ha declarado que, por la cantidad (más de "
        "100 volcanes de lodo identificados en el Caribe colombiano) y la dispersión de "
        "estos cuerpos, no es viable establecer un sistema de monitoreo individual para "
        "cada uno; el seguimiento es reactivo (inspecciones puntuales tras eventos "
        "reportados) y depende en buena medida del reporte comunitario de anomalías."
    ),
    "entidad_vigilancia": (
        "SAMA (caracterización y priorización, con EAFIT y Corpourabá); a nivel nacional, "
        "el SGC es la entidad técnica de referencia para el volcanismo de lodo."
    ),
    "nota_construcciones": (
        "Conteo en radio fijo medido en línea recta desde el punto del volcán; el conteo "
        "de 1 km es acumulado e incluye las construcciones de 500 m."
    ),
    "niveles_alerta": [
        {
            "id": "base",
            "titulo": "Actividad base:",
            "descripcion": "Sismicidad normal y sin deformaciones del cono.",
        },
        {
            "id": "moderada",
            "titulo": "Actividad moderada:",
            "descripcion": "Leve aumento de sismicidad y pequeñas deformaciones por ascenso de materiales.",
        },
        {
            "id": "alta",
            "titulo": "Actividad alta:",
            "descripcion": (
                "Fuerte emisión de lodo y gases, con riesgo de contaminación del agua, "
                "crecientes y daños en infraestructuras."
            ),
        },
    ],
    "fuentes": [
        "Servicio Geológico Colombiano (2017). Volcanismo de lodo del Caribe central colombiano. "
        "DOI 10.32685/9789585978201.",
        "Infobae (12-nov-2024). Qué son los volcanes de lodo y dónde están ubicados.",
        "Infobae (13-nov-2024). Qué encontró el SGC al inspeccionar el volcán Los Aburridos.",
        "El Espectador. Así quedó la zona de la erupción de lodo del volcán El Aburrido, en Turbo.",
        "Infobae (26-feb-2026). San Juan de Urabá: qué causó la columna de fuego y las grietas en Antioquia.",
        "SAMA/EAFIT. Informe de flujos, mayo de 2026: WP1.2.6 Modelado de flujos de lodo (Q-LavHA) y "
        "WP1.2.7 Piloto de monitoreo.",
        "Napoli et al. (2025). Clasificación morfométrica de volcanes de lodo (cono, pastel de lodo).",
    ],
}


def normalizar(texto):
    """Minúsculas, sin acentos, sin espacios y sin el prefijo «Volcán»."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower().strip()
    texto = re.sub(r"^volcan\s+", "", texto)
    return re.sub(r"[^a-z0-9]", "", texto)


def cargar_volcanes():
    """Devuelve (índice nombre normalizado -> id, dict id -> nombre)."""
    datos = json.loads(RUTA_VOLCANES.read_text(encoding="utf-8"))
    indice, nombres = {}, {}
    for feature in datos["features"]:
        propiedades = feature["properties"]
        indice[normalizar(propiedades["nombre"])] = propiedades["id"]
        nombres[propiedades["id"]] = propiedades["nombre"]
    indice.update(ALIAS)
    return indice, nombres


def emparejar(nombre, indice):
    return indice.get(normalizar(nombre))


def vacio(valor):
    return valor is None or valor == "" or valor == [] or valor == {}


def fusionar(destino, nuevo, forzar=False):
    """Copia `nuevo` en `destino` sin pisar valores ya editados (salvo `forzar`)."""
    for clave, valor in nuevo.items():
        if isinstance(valor, dict) and isinstance(destino.get(clave), dict):
            fusionar(destino[clave], valor, forzar)
        elif isinstance(valor, dict) and vacio(destino.get(clave)):
            destino[clave] = valor
        elif clave == "notas_internas":
            actual = destino.get(clave) or ""
            if valor and valor not in actual:
                destino[clave] = (actual + "\n" + valor).strip()
        elif forzar or vacio(destino.get(clave)):
            destino[clave] = valor
    return destino


def cargar_boletin():
    if RUTA_BOLETIN.exists():
        return json.loads(RUTA_BOLETIN.read_text(encoding="utf-8"))
    return {"general": json.loads(json.dumps(GENERAL_BASE)), "volcanes": {}}


def guardar_json(ruta, datos):
    """Escritura atómica: archivo temporal en la misma carpeta y reemplazo."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
        os.replace(temporal, ruta)
    except BaseException:
        if os.path.exists(temporal):
            os.unlink(temporal)
        raise


def guardar_imagen(datos, destino, ancho_max=1600, calidad=82, recorte=None):
    """Guarda `datos` (bytes) como WebP comprimido.

    `recorte` son las fracciones (izquierda, arriba, derecha, abajo) que se conservan.
    """
    from PIL import Image

    with Image.open(io.BytesIO(datos)) as original:
        if original.mode in ("RGBA", "LA", "P"):
            rgba = original.convert("RGBA")
            imagen = Image.new("RGB", rgba.size, "white")
            imagen.paste(rgba, mask=rgba.getchannel("A"))
        else:
            imagen = original.convert("RGB")

    if recorte:
        ancho, alto = imagen.size
        izquierda, arriba, derecha, abajo = recorte
        imagen = imagen.crop((
            round(ancho * izquierda), round(alto * arriba),
            round(ancho * derecha), round(alto * abajo),
        ))
    if imagen.width > ancho_max:
        imagen = imagen.resize(
            (ancho_max, round(imagen.height * ancho_max / imagen.width)), Image.LANCZOS
        )

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(destino, "WEBP", quality=calidad, method=6)
    return destino


def ruta_web(ruta):
    """Ruta relativa al sitio, con el prefijo ./ que usan los demás datos."""
    return "./" + Path(ruta).resolve().relative_to(RAIZ).as_posix()

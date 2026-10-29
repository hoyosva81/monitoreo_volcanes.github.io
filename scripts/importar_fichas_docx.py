"""Importa las fichas técnicas del documento Word a data/boletin.json y assets/.

Uso:
    py scripts/importar_fichas_docx.py "ruta/Fichas_Tecnicas_Volcanes_Lodo_Uraba.docx"
    py scripts/importar_fichas_docx.py "ruta.docx" --simular

El documento trae una sección por volcán con identificación, clasificación,
actividad histórica, monitoreo y gestión del riesgo. Las notas internas del
documento (rutas de proyecto, pendientes, nombres de personas) no se copian a los
campos públicos: se guardan en `notas_internas`, visible solo en el editor.

Por defecto no pisa lo que ya esté en boletin.json (por ejemplo, ediciones hechas
con el editor): solo completa campos vacíos. Usa --forzar para sobrescribir.
"""

import argparse
import re
import sys
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import boletin_comun as bc

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

ENCABEZADO = re.compile(r"^\s*(\d+)\s*\.\s*Volc[aá]n\s+(.+?)\s*$")
SEGMENTOS = [
    ("ident", r"Identificaci[oó]n"),
    ("clasif", r"Clasificaci[oó]n"),
    ("actividad", r"Actividad Hist"),
    ("monitoreo", r"Monitoreo e"),
    ("gestion", r"Gesti[oó]n del Riesgo"),
]
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
INTERNO = re.compile(
    r"Emilio|NotebookLM|PENDIENTE|advertencia metodol|\.gdb|\.xlsx|\.aprx|confirmar con la fuente|"
    r"ver nota de confirmaci|volcanes_lodo_pt|Construcciones_Afectadas|desconectada|"
    r"no existe ninguna capa|se requiere que",
    re.IGNORECASE,
)
MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y"}
# Recorte del mapa de «Ubicación»: quita la banda amarilla del título y los márgenes.
RECORTE_UBICACION = (0.016, 0.124, 0.984, 0.985)


# ============================================================
# LECTURA DEL DOCX
# ============================================================

def leer_relaciones(zf):
    raiz = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
    return {
        rel.get("Id"): rel.get("Target")
        for rel in raiz.iter(REL + "Relationship")
        if rel.get("Target", "").startswith("media/")
    }


def texto_parrafo(parrafo):
    partes = []
    for elemento in parrafo.iter():
        if elemento.tag == W + "t":
            partes.append(elemento.text or "")
        elif elemento.tag == W + "tab":
            partes.append(" ")
        elif elemento.tag == W + "br":
            partes.append("\n")
    return "".join(partes)


def elementos_parrafo(parrafo, relaciones):
    """Devuelve las líneas de texto e imágenes de un párrafo, en orden."""
    resultado = []
    for linea in texto_parrafo(parrafo).split("\n"):
        linea = re.sub(r"\s+", " ", linea).strip()
        if linea:
            resultado.append(("txt", linea))
    vistas = []
    for blip in parrafo.iter(A + "blip"):
        destino = relaciones.get(blip.get(R + "embed"))
        if destino and destino not in vistas:
            vistas.append(destino)
            resultado.append(("img", destino))
    return resultado


def leer_elementos(zf):
    relaciones = leer_relaciones(zf)
    cuerpo = ET.fromstring(zf.read("word/document.xml")).find(W + "body")
    for hijo in cuerpo:
        if hijo.tag == W + "p":
            yield from elementos_parrafo(hijo, relaciones)
        elif hijo.tag == W + "tbl":
            for parrafo in hijo.iter(W + "p"):
                yield from elementos_parrafo(parrafo, relaciones)


def dividir_secciones(elementos):
    secciones, actual = [], None
    for tipo, valor in elementos:
        if tipo == "txt":
            coincidencia = ENCABEZADO.match(valor)
            if coincidencia:
                actual = {"nombre": coincidencia.group(2).strip(), "lineas": [], "imagenes": []}
                secciones.append(actual)
                continue
        if actual is None:
            continue
        if tipo == "txt":
            actual["lineas"].append(valor)
        else:
            actual["imagenes"].append((valor, len(actual["lineas"])))
    return secciones


def segmentar(lineas):
    segmentos = {clave: [] for clave, _ in SEGMENTOS}
    actual = None
    for linea in lineas:
        cambio = None
        if len(linea) < 80:
            for clave, patron in SEGMENTOS:
                if re.match(rf"^\s*(?:\d\s*\.\s*)?{patron}", linea, re.IGNORECASE):
                    cambio = clave
                    break
        if cambio:
            actual = cambio
        elif actual:
            segmentos[actual].append(linea)
    return segmentos


# ============================================================
# EXTRACCIÓN DE CAMPOS
# ============================================================

def valor(lineas, etiqueta):
    """Texto tras «Etiqueta ...:» o, en las tablas, la línea siguiente a «Etiqueta»."""
    con_dos_puntos = re.compile(rf"^\s*(?:{etiqueta})\b[^:\n]*:\s*(.*)$", re.IGNORECASE)
    sola = re.compile(rf"^\s*(?:{etiqueta})\s*:?\s*$", re.IGNORECASE)
    for i, linea in enumerate(lineas):
        coincidencia = con_dos_puntos.match(linea)
        if coincidencia:
            return coincidencia.group(1).strip()
        if sola.match(linea):
            return lineas[i + 1].strip() if i + 1 < len(lineas) else ""
    return None


def limpiar_publico(texto):
    """Separa el texto público de las notas internas del documento."""
    if not texto:
        return "", ""
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"\s*\([^()]*(?:Emilio|NotebookLM|confirmar con la fuente)[^()]*\)", "", texto, flags=re.I)
    oraciones = re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿¡“\"(])", texto)
    publicas = [o for o in oraciones if not INTERNO.search(o)]
    internas = [o for o in oraciones if INTERNO.search(o)]
    publico = re.sub(r"\s+([.;,])", r"\1", " ".join(publicas)).strip()
    return publico, " ".join(internas).strip()


def titulo(texto):
    texto = re.split(r"\s*\(", texto)[0].strip().rstrip(".")
    if not texto.isupper():
        return texto
    palabras = texto.lower().split()
    return " ".join(
        p if (i and p in MINUSCULAS) else p.capitalize() for i, p in enumerate(palabras)
    )


def numero(texto):
    coincidencia = re.search(r"(\d+(?:[.,]\d+)?)", texto or "")
    if not coincidencia:
        return None
    valor_numerico = float(coincidencia.group(1).replace(",", "."))
    return int(valor_numerico) if valor_numerico.is_integer() else valor_numerico


def fechas_en(texto):
    """Fechas completas (dd/mm/aaaa o «d de mes de aaaa») ordenadas y sin repetir."""
    encontradas = set()
    for d, m, a in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", texto):
        encontradas.add((int(a), int(m), int(d)))
    for d, m, a in re.findall(r"\b(\d{1,2}) de ([a-záéíóú]+) de (\d{4})\b", texto, flags=re.I):
        mes = MESES.get(m.lower())
        if mes:
            encontradas.add((int(a), mes, int(d)))
    validas = []
    for anio, mes, dia in sorted(encontradas):
        try:
            date(anio, mes, dia)
        except ValueError:
            continue
        validas.append((anio, mes, dia))
    return validas


def resumir_amenaza(texto):
    if not texto:
        return ""
    if re.search(r"Q-LavHA COMPLETADO", texto, re.I):
        return "Modelado de propagación de flujos de lodo (Q-LavHA) disponible: mapa de probabilidad de propagación."
    if re.search(r"No incluido en el modelado", texto, re.I):
        return "Sin modelado de propagación de flujos para este volcán."
    if re.search(r"calibrar el umbral", texto, re.I):
        return "Usado para calibrar el modelo de propagación Q-LavHA; sin escenario de propagación propio."
    return limpiar_publico(texto)[0]


def extraer_volcan(seccion):
    segmentos = segmentar(seccion["lineas"])
    ident, clasif = segmentos["ident"], segmentos["clasif"]
    actividad, monitoreo, gestion = segmentos["actividad"], segmentos["monitoreo"], segmentos["gestion"]
    internas = []
    datos = {}

    municipio = valor(ident, "Municipio")
    if municipio:
        datos["municipio"] = titulo(municipio)

    principal = valor(ident, "Nombre principal")
    if principal:
        datos["nombre_principal"] = principal.rstrip(".").strip()

    altitud = valor(ident, "Altitud|Elevaci[oó]n")
    if altitud:
        datos["altitud_msnm"] = numero(altitud)
        if re.search(r"costa", altitud, re.I):
            internas.append(f"Altitud en el documento: {altitud}")

    for linea in ident:
        if re.match(r"^Ubicado en", linea):
            datos["ubicacion_texto"] = linea.strip()
            lugar = re.search(r"vereda\s+([^,]+),\s*corregimiento\s+([^,]+),", linea)
            if lugar:
                datos["vereda"] = lugar.group(1).strip()
                datos["corregimiento"] = lugar.group(2).strip()

    tipo = valor(clasif, "Tipo")
    if tipo:
        coincidencia = re.search(r"Tipo\s+(I{1,3}|\d)", tipo)
        if coincidencia:
            datos["tipo"] = f"Tipo {coincidencia.group(1)}"

    morfologia = valor(clasif, "Morfolog[ií]a")
    if morfologia and not morfologia.startswith("Los volcanes de lodo del Caribe"):
        publico, interno = limpiar_publico(morfologia)
        datos["morfologia"] = publico
        if interno:
            internas.append(interno)

    flujo = valor(clasif, "Comportamiento del flujo")
    if flujo:
        publico, interno = limpiar_publico(flujo)
        datos["comportamiento_flujo"] = publico
        if interno:
            internas.append(interno)

    estado = valor(actividad, "Estado de actividad")
    if estado:
        publico, interno = limpiar_publico(estado)
        datos["estado_actividad"] = publico
        if interno:
            internas.append(interno)

    ultima = valor(actividad, r"[ÚU]ltima erupci[oó]n conocida")
    if ultima:
        publico, interno = limpiar_publico(ultima)
        datos["ultima_erupcion_texto"] = publico
        if interno:
            internas.append(interno)

    texto_actividad = " ".join(
        l for l in actividad if not re.match(r"^\s*Contexto regional", l)
    )
    marcador = bool(re.search(r"marcador", texto_actividad, re.I))
    erupciones = []
    for anio, mes, dia in fechas_en(texto_actividad):
        aproximada = marcador and mes == 1 and dia == 1
        erupciones.append({
            "fecha": f"{anio:04d}" if aproximada else f"{anio:04d}-{mes:02d}-{dia:02d}",
            "precision": "anio" if aproximada else "dia",
            "descripcion": "",
        })
    if erupciones:
        datos["erupciones"] = erupciones
    contexto = next((l for l in actividad if re.match(r"^\s*Contexto regional", l)), None)
    if contexto:
        internas.append(contexto)

    red = valor(monitoreo, "Red de monitoreo")
    if red:
        if re.match(r"No existe una red de monitoreo instrumental", red):
            datos["red_monitoreo"] = (
                "No cuenta con una red instrumental de monitoreo sísmico ni geodésico (GPS) específica."
            )
        else:
            publico, interno = limpiar_publico(red)
            datos["red_monitoreo"] = publico
            if interno:
                internas.append(interno)

    afectaciones = {}
    texto_gestion = " ".join(gestion)
    construcciones = re.search(
        r"(\d+)\s+dentro de 500 m\s*;?\s*(\d+)\s+dentro de 1 km", texto_gestion
    ) or re.search(
        r"(\d+)\s+construcciones.*?500 m.*?\by\s+(\d+)\s+dentro de 1 km", texto_gestion
    )
    if construcciones:
        afectaciones["construcciones_500m"] = int(construcciones.group(1))
        afectaciones["construcciones_1km"] = int(construcciones.group(2))

    infraestructura = valor(gestion, r"Infraestructura cr[ií]tica expuesta")
    if infraestructura:
        publico, interno = limpiar_publico(infraestructura)
        afectaciones["infraestructura_critica"] = publico.rstrip(".")
        if interno:
            internas.append(interno)

    poblacion = valor(gestion, r"Poblaci[oó]n en riesgo")
    if poblacion:
        publico, interno = limpiar_publico(poblacion)
        afectaciones["poblacion"] = publico
        if interno:
            internas.append(interno)

    amenaza = valor(gestion, "Mapa de amenaza")
    if amenaza:
        afectaciones["amenaza_texto"] = resumir_amenaza(amenaza)
        internas.append(f"Mapa de amenaza (texto original): {amenaza}")
    if afectaciones:
        datos["afectaciones"] = afectaciones

    construccion_interna = re.search(r"(Fuente: capa Construcciones_Afectadas.*)", texto_gestion)
    if construccion_interna:
        internas.append(construccion_interna.group(1))

    if internas:
        datos["notas_internas"] = "\n".join(i for i in internas if i)
    return datos


# ============================================================
# IMÁGENES
# ============================================================

def extraer_imagenes(zf, seccion, id_volcan, simular):
    """Asigna rol a las imágenes de la sección y las guarda comprimidas."""
    imagenes = seccion["imagenes"]
    if not imagenes:
        return {}
    roles = ["mapa_ubicacion", "mapa_propagacion", "mapa_amenaza"]
    if imagenes[0][0].lower().endswith((".jpg", ".jpeg")):
        roles = ["foto"] + roles

    resultado = {}
    for (destino_docx, posicion), rol in zip(imagenes, roles):
        carpeta = "fotos" if rol == "foto" else "mapas"
        nombre = {
            "foto": "principal",
            "mapa_ubicacion": "ubicacion",
            "mapa_propagacion": "propagacion",
            "mapa_amenaza": "amenaza",
        }[rol]
        archivo = bc.RAIZ / "assets" / carpeta / id_volcan / f"{nombre}.webp"
        if not simular:
            bc.guardar_imagen(
                zf.read("word/" + destino_docx),
                archivo,
                recorte=RECORTE_UBICACION if rol == "mapa_ubicacion" else None,
            )
        pie = ""
        if rol == "foto":
            leyenda = next(
                (l for l in seccion["lineas"] if re.match(r"^Figura \d+\.", l)), ""
            )
            pie = re.sub(r"^Figura \d+\.\s*", "", leyenda).replace("Vista área", "Vista aérea")
        resultado[rol] = {"archivo": bc.ruta_web(archivo), "pie": pie}
    return resultado


# ============================================================
# PRINCIPAL
# ============================================================

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("docx", type=Path, help="Documento Word con las fichas técnicas")
    parser.add_argument("--forzar", action="store_true", help="Sobrescribir campos ya presentes")
    parser.add_argument("--simular", action="store_true", help="Mostrar el informe sin escribir archivos")
    parser.add_argument("--sin-imagenes", action="store_true", help="No extraer ni comprimir imágenes")
    args = parser.parse_args(argv)

    indice, nombres = bc.cargar_volcanes()
    boletin = bc.cargar_boletin()
    bc.fusionar(boletin["general"], bc.GENERAL_BASE, args.forzar)
    hoy = date.today().isoformat()

    with zipfile.ZipFile(args.docx) as zf:
        secciones = dividir_secciones(leer_elementos(zf))
        emparejados, sin_emparejar = [], []
        for seccion in secciones:
            id_volcan = bc.emparejar(seccion["nombre"], indice)
            if not id_volcan:
                sin_emparejar.append(seccion["nombre"])
                continue
            datos = extraer_volcan(seccion)
            datos["nombre"] = nombres[id_volcan]
            if not args.sin_imagenes:
                imagenes = extraer_imagenes(zf, seccion, id_volcan, args.simular)
                if imagenes:
                    datos["imagenes"] = imagenes
            datos["actualizado"] = hoy
            destino = boletin["volcanes"].setdefault(id_volcan, {})
            bc.fusionar(destino, datos, args.forzar)
            emparejados.append((seccion["nombre"], id_volcan, datos))

    print(f"Secciones leídas: {len(secciones)}  |  emparejadas: {len(emparejados)}")
    for nombre_doc, id_volcan, datos in emparejados:
        afect = datos.get("afectaciones", {})
        print(
            f"  {nombre_doc:<30} -> {id_volcan:<26} "
            f"mun={datos.get('municipio', '--'):<18} alt={datos.get('altitud_msnm', '--')!s:<5} "
            f"tipo={datos.get('tipo', '--'):<8} erup={len(datos.get('erupciones', [])):<2} "
            f"constr={afect.get('construcciones_500m', '--')}/{afect.get('construcciones_1km', '--')} "
            f"img={len(datos.get('imagenes', {}))}"
        )
    if sin_emparejar:
        print("SIN EMPAREJAR (revisar ALIAS en boletin_comun.py):", ", ".join(sin_emparejar))
    faltantes = [n for i, n in nombres.items() if i not in {e[1] for e in emparejados}]
    if faltantes:
        print("Volcanes del portal sin sección en el documento:", ", ".join(faltantes))

    if args.simular:
        print("Simulación: no se escribió nada.")
        return 0
    bc.guardar_json(bc.RUTA_BOLETIN, boletin)
    print(f"Escrito {bc.RUTA_BOLETIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Importa la morfometría de los volcanes a data/boletin.json y assets/.

Uso:
    py scripts/importar_morfometria.py "ruta/morfometria_clasificacion.xlsx" "ruta/figuras_articulo"
    py scripts/importar_morfometria.py "ruta.xlsx" "ruta/figuras" --simular

Lee la hoja «Datos» del libro (una fila por volcán) y las figuras `fig2_<Volcán>.png`
(mapa del DEM con la base y perfiles A-B y C-D). Las figuras se comprimen a WebP
(máximo 1600 px de ancho) en `assets/mapas/<id>/morfometria.webp`.

Requiere openpyxl y Pillow. No pisa lo que ya esté en boletin.json salvo con --forzar.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import boletin_comun as bc

COLUMNAS = {
    "volcan": r"^Volc[aá]n$",
    "dem": r"^DEM usado",
    "dmax": r"^Dmax",
    "dmin": r"^Dmin",
    "dmean": r"^Dmean",
    "altura": r"^Altura H",
    "sb": r"^[ÁA]rea basal Sb",
    "volumen": r"^Volumen cono",
    "pendiente_dem": r"^Pendiente local del DEM",
    "azimuts": r"^Azimuts interpolados$",
    "hr": r"^H/R$",
    "arctan": r"^arctan\(H/R\)",
    "pct_azimuts": r"^% azimuts interpolados",
    "base_poco_fiable": r"^Base poco",
    "tamano": r"^Tama[ñn]o",
    "clase_calculada": r"^Clase calculada",
    "clase_usuario": r"^Clase del usuario",
    "clase_usada": r"^Clase usada",
    "origen_clase": r"^Origen de la clase",
    "hr_alto": r"^H/R alto",
    "bsr": r"^bsr",
    "observaciones": r"^Observaciones",
}


def numero(valor, decimales):
    try:
        return round(float(valor), decimales)
    except (TypeError, ValueError):
        return None


def si_no(valor):
    return str(valor).strip().lower() in {"sí", "si", "yes", "true", "1"}


def leer_hoja_datos(ruta_xlsx):
    import openpyxl

    libro = openpyxl.load_workbook(ruta_xlsx, data_only=True)
    hoja = libro["Datos"]
    encabezado = [str(c.value or "").strip() for c in hoja[1]]
    indices = {}
    for clave, patron in COLUMNAS.items():
        for i, texto in enumerate(encabezado):
            if re.search(patron, texto, re.IGNORECASE):
                indices[clave] = i
                break
    faltantes = [c for c in ("volcan", "dmax", "dmin", "altura", "hr", "clase_usada") if c not in indices]
    if faltantes:
        raise SystemExit(f"Faltan columnas en la hoja Datos: {', '.join(faltantes)}")

    filas = []
    for fila in hoja.iter_rows(min_row=2, values_only=True):
        if not fila or not fila[indices["volcan"]]:
            continue
        filas.append({clave: fila[i] for clave, i in indices.items()})
    return filas


def datos_morfometria(fila):
    clase = fila.get("clase_usada") or fila.get("clase_calculada")
    return {
        "clase": clase,
        "clase_calculada": fila.get("clase_calculada"),
        "origen_clase": fila.get("origen_clase"),
        "tamano": fila.get("tamano"),
        "dmax_m": numero(fila.get("dmax"), 0),
        "dmin_m": numero(fila.get("dmin"), 0),
        "dmean_m": numero(fila.get("dmean"), 0),
        "altura_m": numero(fila.get("altura"), 1),
        "hr": numero(fila.get("hr"), 3),
        "arctan_hr_grados": numero(fila.get("arctan"), 1),
        "pendiente_dem_grados": numero(fila.get("pendiente_dem"), 1),
        "azimuts_interpolados": int(fila["azimuts"]) if fila.get("azimuts") is not None else None,
        "pct_azimuts_interpolados": numero(fila.get("pct_azimuts"), 2),
        "base_poco_fiable": si_no(fila.get("base_poco_fiable")),
        "hr_alto_segun_articulo": si_no(fila.get("hr_alto")),
        "bsr": numero(fila.get("bsr"), 3),
        "dem": fila.get("dem"),
        # Sb y V del libro usan fórmulas simples (círculo de Dmean y cono); los valores
        # medidos sobre el DEM están en el pie de cada figura.
        "sb_km2_circulo": numero(fila.get("sb"), 3),
        "v_cono_km3": numero(fila.get("volumen"), 4),
        "fuente": "Napoli et al. (2025); morfometria_clasificacion.xlsx",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx", type=Path, help="Libro morfometria_clasificacion.xlsx")
    parser.add_argument("figuras", type=Path, help="Carpeta con las figuras fig2_<Volcán>.png")
    parser.add_argument("--forzar", action="store_true", help="Sobrescribir campos ya presentes")
    parser.add_argument("--simular", action="store_true", help="Mostrar el informe sin escribir archivos")
    args = parser.parse_args(argv)

    indice, nombres = bc.cargar_volcanes()
    boletin = bc.cargar_boletin()
    bc.fusionar(boletin["general"], bc.GENERAL_BASE, args.forzar)
    hoy = date.today().isoformat()

    sin_emparejar, con_datos, con_figura = [], set(), set()

    for fila in leer_hoja_datos(args.xlsx):
        id_volcan = bc.emparejar(fila["volcan"], indice)
        if not id_volcan:
            sin_emparejar.append(fila["volcan"])
            continue
        nuevo = {"morfometria": datos_morfometria(fila), "actualizado": hoy}
        if fila.get("observaciones"):
            nuevo["notas_internas"] = f"Morfometría: {str(fila['observaciones']).strip()}"
        destino = boletin["volcanes"].setdefault(id_volcan, {"nombre": nombres[id_volcan]})
        bc.fusionar(destino, nuevo, args.forzar)
        con_datos.add(id_volcan)

    for figura in sorted(args.figuras.glob("fig2_*.png")):
        nombre = figura.stem.removeprefix("fig2_").replace("_", " ")
        id_volcan = bc.emparejar(nombre, indice)
        if not id_volcan:
            sin_emparejar.append(f"{figura.name} (figura)")
            continue
        archivo = bc.RAIZ / "assets" / "mapas" / id_volcan / "morfometria.webp"
        if not args.simular:
            bc.guardar_imagen(figura.read_bytes(), archivo)
        destino = boletin["volcanes"].setdefault(id_volcan, {"nombre": nombres[id_volcan]})
        imagen = {
            "archivo": bc.ruta_web(archivo),
            "pie": f"Morfometría de {nombres[id_volcan]}: (a) mapa del DEM con la base y los ejes; (b) perfiles A-B y C-D.",
        }
        bc.fusionar(destino, {"imagenes": {"morfometria": imagen}}, args.forzar)
        con_figura.add(id_volcan)

    print(f"Con datos morfométricos: {len(con_datos)}  |  con figura: {len(con_figura)}")
    if sin_emparejar:
        print("SIN EMPAREJAR (revisar ALIAS en boletin_comun.py):", ", ".join(sin_emparejar))
    sin_morfometria = [n for i, n in nombres.items() if i not in con_datos]
    if sin_morfometria:
        print("Volcanes del portal sin morfometría:", ", ".join(sin_morfometria))

    if args.simular:
        print("Simulación: no se escribió nada.")
        return 0
    bc.guardar_json(bc.RUTA_BOLETIN, boletin)
    print(f"Escrito {bc.RUTA_BOLETIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

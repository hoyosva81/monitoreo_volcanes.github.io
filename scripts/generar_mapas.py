"""
PIPELINE PARA GENERACION DE MAPAS DE DESPLAZAMIENTO INSAR - MINTPY

Flujo:
    geo_timeseries.h5
        |
        v
    save_gdal.py
        |
        v
    GeoTIFF
        |
        v
    Recorte por mascara
        |
        v
    Conversion m -> cm
        |
        v
    Raster -> puntos
        |
        v
    Clasificacion
        |
        v
    GeoPackage

Requisitos:
    pip install numpy pandas rasterio geopandas shapely

Ademas:
    MintPy debe estar instalado y save_gdal.py disponible
    en el entorno activo.
"""

from pathlib import Path
import subprocess
import shutil

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio

from rasterio.mask import mask as rio_mask


# ============================================================
# 1. CONFIGURACION
# ============================================================

# Nombre del sitio / volcan
VOLCAN = "Palmares Cenizosa"

# Fecha que quieres extraer del timeseries
FECHA = "20260911"

# Archivo MintPy
TIMESERIES = Path(
    "/run/media/spinedas1/Seagate/saocom/desc137/PalmaresCenizosa/geo/geo_timeseries_ERA5_ramp_demErr.h5"
)

# Mascara espacial del volcan
# Puede ser .shp o .gpkg
MASCARA = Path(
    "/run/media/spinedas1/Seagate/Diapiros/Desarrollos/Volcanes_lodo/Shp_radios_influencia/radios_influencia.shp"
)

CAMPO_VOLCAN = "nombre"

# Si el GPKG tiene varias capas, puedes indicar la capa.
# Si tiene una sola, dejar en None.
CAPA_MASCARA = None

# Flujos historicos
# Si no quieres agregarlos al GeoPackage final:
# FLUJOS_HISTORICOS = None
FLUJOS_HISTORICOS = Path(
    "/run/media/spinedas1/Seagate/Diapiros/Desarrollos/QGIS/volcanes-lodo/Volcanes_flujos/Bocas.shp"
)

# CAPA_FLUJOS = 'Flujos históricos'

# Carpeta principal de salida
CARPETA_SALIDA = Path(
    "/run/media/spinedas1/Seagate/Diapiros/Desarrollos/InSAR/SBAS/Geoportal/data/rasters"
)

CAMPO_FLUJOS = "Nombre"

# Si True, vuelve a generar los archivos aunque ya existan
SOBRESCRIBIR = True


# ============================================================
# 2. CONFIGURACION DE DESPLAZAMIENTO
# ============================================================

# MintPy normalmente almacena desplazamiento en metros.
# Lo convertiremos a centimetros.

FACTOR_M_A_CM = 100.0


# ============================================================
# 3. CLASIFICACION FIJA
# ============================================================
#
# Estos limites deben permanecer iguales para TODOS
# los volcanes si quieres comparar los mapas visualmente.
#
# Puedes modificarlos segun tus necesidades.
# ============================================================

LIMITES_CM = np.array(
    [
        -6,
        -4,
        -2,
        -1,
         1,
         2,
         4,
         6
    ],
    dtype=float
)

ETIQUETAS = [
    "< -6 cm",
    "-6 a -4 cm",
    "-4 a -2 cm",
    "-2 a -1 cm",
    "-1 a +1 cm",
    "+1 a +2 cm",
    "+2 a +4 cm",
    "+4 a +6 cm",
    "> +6 cm"
]

# Colores fijos, similares a Viridis
# azul -> cian -> verde -> amarillo
COLORES = [
    "#d73027",
    "#f46d43",
    "#fdae61",
    "#fee090",
    "#ffffbf",
    "#e0f3f8",
    "#abd9e9",
    "#74add1",
    "#4575b4"
]


# ============================================================
# 4. CREAR CARPETAS
# ============================================================

SALIDA = (
    CARPETA_SALIDA
    / VOLCAN
    / FECHA
)

SALIDA.mkdir(
    parents=True,
    exist_ok=True
)

TIF_ORIGINAL = (
    SALIDA
    / f"{VOLCAN}_{FECHA}_desplazamiento.tif"
)

TIF_RECORTADO = (
    SALIDA
    / f"{FECHA}.tif"
)

GPKG_SALIDA = (
    SALIDA
    / f"{VOLCAN}_{FECHA}.gpkg"
)

CSV_RESUMEN = (
    SALIDA
    / f"{VOLCAN}_{FECHA}_resumen.csv"
)


# ============================================================
# 5. FUNCIONES
# ============================================================


def verificar_archivo(ruta, nombre):
    """
    Comprueba que exista un archivo requerido.
    """

    if not ruta.exists():
        raise FileNotFoundError(
            f"\nNo se encontro {nombre}:\n{ruta}\n"
        )


def generar_geotiff_mintpy():
    """
    Ejecuta save_gdal.py para extraer una fecha
    desde geo_timeseries.h5.
    """

    print("\n========================================")
    print("1. GENERANDO GEOTIFF DESDE MINTPY")
    print("========================================")

    if TIF_ORIGINAL.exists() and not SOBRESCRIBIR:
        print(
            f"Ya existe:\n{TIF_ORIGINAL}"
        )
        return

    comando = [
        "save_gdal.py",
        str(TIMESERIES),
        "-d",
        FECHA,
        "-o",
        str(TIF_ORIGINAL),
    ]

    print(
        "\nEjecutando:\n"
        + " ".join(comando)
    )

    try:
        subprocess.run(
            comando,
            check=True
        )

    except FileNotFoundError:

        raise RuntimeError(
            "\nNo se encontro save_gdal.py.\n"
            "Activa primero el ambiente donde tienes "
            "instalado MintPy.\n"
        )

    except subprocess.CalledProcessError as error:

        raise RuntimeError(
            "\nMintPy produjo un error al generar "
            "el GeoTIFF."
        ) from error

    verificar_archivo(
        TIF_ORIGINAL,
        "GeoTIFF generado por MintPy"
    )

    print(
        f"\nGeoTIFF generado:\n{TIF_ORIGINAL}"
    )


def leer_mascara():
    """
    Lee el archivo que contiene las mascaras de todos los volcanes
    y selecciona solamente la correspondiente a VOLCAN.
    """

    print("\n========================================")
    print("2. LEYENDO MASCARA")
    print("========================================")

    verificar_archivo(
        MASCARA,
        "archivo de mascaras"
    )

    # Leer shapefile / geopackage
    if CAPA_MASCARA is None:
        mascaras = gpd.read_file(MASCARA)
    else:
        mascaras = gpd.read_file(
            MASCARA,
            layer=CAPA_MASCARA
        )

    if mascaras.empty:
        raise ValueError(
            "El archivo de mascaras esta vacio."
        )

    if mascaras.crs is None:
        raise ValueError(
            "El archivo de mascaras no tiene CRS definido."
        )

    # Comprobar que existe el campo
    if CAMPO_VOLCAN not in mascaras.columns:
        raise ValueError(
            f"No existe el campo '{CAMPO_VOLCAN}' "
            f"en el archivo de mascaras.\n"
            f"Campos disponibles: {list(mascaras.columns)}"
        )

    # Seleccionar solamente el volcan actual
    area = mascaras[
        mascaras[CAMPO_VOLCAN]
        .astype(str)
        .str.strip()
        .str.lower()
        == VOLCAN.strip().lower()
    ].copy()

    if area.empty:
        raise ValueError(
            f"No se encontro una mascara para el volcan: {VOLCAN}"
        )

    # Eliminar geometrías vacías
    area = area[
        area.geometry.notna()
    ].copy()

    area = area[
        ~area.geometry.is_empty
    ].copy()

    # Reparar geometrías inválidas
    area["geometry"] = area.geometry.make_valid()

    print(f"Volcan seleccionado: {VOLCAN}")
    print(f"CRS mascara: {area.crs}")
    print(f"Numero de geometrías: {len(area)}")

    return area

def recortar_raster(area):
    """
    Recorta el GeoTIFF generado por MintPy
    utilizando la mascara espacial.
    """

    print("\n========================================")
    print("3. RECORTANDO RASTER")
    print("========================================")

    if (
        TIF_RECORTADO.exists()
        and not SOBRESCRIBIR
    ):
        print(
            f"Ya existe:\n{TIF_RECORTADO}"
        )

        with rasterio.open(
            TIF_RECORTADO
        ) as src:

            return src.crs

    with rasterio.open(
        TIF_ORIGINAL
    ) as src:

        raster_crs = src.crs

        if raster_crs is None:
            raise ValueError(
                "El GeoTIFF no tiene CRS."
            )

        print(
            f"CRS raster: {raster_crs}"
        )

        # Reproyectar máscara al CRS del raster
        area_raster = area.to_crs(
            raster_crs
        )

        geometrías = [
            geom.__geo_interface__
            for geom
            in area_raster.geometry
        ]

        # Recorte
        raster_recortado, transformacion = rio_mask(
            src,
            geometrías,
            crop=True,
            nodata=np.nan,
            filled=True
        )

        metadata = src.meta.copy()

        # Aseguramos float32 para poder utilizar NaN
        raster_recortado = (
            raster_recortado
            .astype(np.float32)
        )

        metadata.update(
            {
                "driver": "GTiff",
                "dtype": "float32",
                "height": raster_recortado.shape[1],
                "width": raster_recortado.shape[2],
                "transform": transformacion,
                "nodata": np.nan,
                "compress": "deflate",
            }
        )

    with rasterio.open(
        TIF_RECORTADO,
        "w",
        **metadata
    ) as dst:

        dst.write(
            raster_recortado
        )

    print(
        f"\nRaster recortado:\n{TIF_RECORTADO}"
    )

    return raster_crs


def clasificar_desplazamiento(valores_cm):
    """
    Clasifica los valores de desplazamiento y asigna
    categoria y color.
    """

    clases = np.digitize(
        valores_cm,
        LIMITES_CM,
        right=False
    )

    categorias = np.array(
        ETIQUETAS,
        dtype=object
    )[clases]

    colores = np.array(
        COLORES,
        dtype=object
    )[clases]

    return clases, categorias, colores


def raster_a_puntos():
    """
    Convierte cada pixel valido del raster a un punto
    localizado en el centro de la celda.
    """

    print("\n========================================")
    print("4. CONVIRTIENDO RASTER A PUNTOS")
    print("========================================")

    with rasterio.open(
        TIF_RECORTADO
    ) as src:

        raster = src.read(1)

        raster_crs = src.crs

        nodata = src.nodata

        # ----------------------------------------------------
        # PIXELES VALIDOS
        # ----------------------------------------------------

        validos = np.isfinite(
            raster
        )

        if (
            nodata is not None
            and np.isfinite(nodata)
        ):
            validos &= (
                raster != nodata
            )

        filas, columnas = np.where(
            validos
        )

        if len(filas) == 0:
            raise ValueError(
                "No hay pixeles validos "
                "dentro de la mascara."
            )

        # ----------------------------------------------------
        # VALORES DE DESPLAZAMIENTO
        # ----------------------------------------------------

        valores_m = raster[
            filas,
            columnas
        ].astype(float)

        valores_cm = (
            valores_m
            * FACTOR_M_A_CM
        )

        # ----------------------------------------------------
        # COORDENADAS DE LOS CENTROS DE PIXEL
        # ----------------------------------------------------

        xs, ys = rasterio.transform.xy(
            src.transform,
            filas,
            columnas,
            offset="center"
        )

        xs = np.asarray(xs)
        ys = np.asarray(ys)

    # --------------------------------------------------------
    # CLASIFICACION Y COLORES
    # --------------------------------------------------------

    clases, categorias, colores = (
        clasificar_desplazamiento(
            valores_cm
        )
    )

    # --------------------------------------------------------
    # GEOMETRIA
    # --------------------------------------------------------

    geometria = gpd.points_from_xy(
        xs,
        ys
    )

    # --------------------------------------------------------
    # CREAR GEODATAFRAME
    # --------------------------------------------------------

    gdf = gpd.GeoDataFrame(
        {
            "volcan": [VOLCAN] * len(valores_m),
            "fecha": [FECHA] * len(valores_m),

            "fila": filas,
            "columna": columnas,

            "disp_m": valores_m,
            "disp_cm": valores_cm,

            "clase": clases,
            "categoria": categorias,

            # Color asociado a cada categoria
            "color": colores,
        },

        geometry=geometria,
        crs=raster_crs
    )

    print(
        f"Pixeles convertidos: "
        f"{len(gdf):,}"
    )

    print("\nDistribucion de clases:")
    print(
        gdf.groupby(
            ["clase", "categoria"]
        ).size()
    ) 

    print("\nRango de desplazamiento:")
    print(f"Minimo: {gdf['disp_cm'].min():.3f} cm")
    print(f"Maximo: {gdf['disp_cm'].max():.3f} cm")

    return gdf


def guardar_desplazamiento(
    gdf
):
    """
    Guarda los puntos de desplazamiento en GeoPackage.
    """

    print("\n========================================")
    print("5. GUARDANDO GEOPACKAGE")
    print("========================================")

    if (
        GPKG_SALIDA.exists()
        and SOBRESCRIBIR
    ):
        GPKG_SALIDA.unlink()

    gdf.to_file(
        GPKG_SALIDA,
        layer="desplazamiento",
        driver="GPKG"
    )

    print(
        "\nCapa creada:"
        "\n  desplazamiento"
    )


def agregar_mascara_al_gpkg(
    area,
    crs_destino
):
    """
    Copia la mascara al mismo GeoPackage final.
    """

    area_out = area.to_crs(
        crs_destino
    )

    area_out.to_file(
        GPKG_SALIDA,
        layer="area_estudio",
        driver="GPKG"
    )

    print(
        "  area_estudio"
    )


def agregar_flujos_historicos(
    crs_destino
):
    """
    Selecciona los flujos historicos asociados al volcan
    actual y los guarda en el GeoPackage.
    """

    if FLUJOS_HISTORICOS is None:
        return

    verificar_archivo(
        FLUJOS_HISTORICOS,
        "flujos historicos"
    )

    print("\n========================================")
    print("6. AGREGANDO FLUJOS HISTORICOS")
    print("========================================")

    flujos = gpd.read_file(
        FLUJOS_HISTORICOS
    )

    if flujos.empty:
        raise ValueError(
            "El archivo de flujos historicos esta vacio."
        )

    if flujos.crs is None:
        raise ValueError(
            "Los flujos historicos no tienen CRS."
        )

    if CAMPO_FLUJOS not in flujos.columns:
        raise ValueError(
            f"No existe el campo '{CAMPO_FLUJOS}' "
            "en el archivo de flujos.\n"
            f"Campos disponibles: {list(flujos.columns)}"
        )

    nombre_objetivo = (
        VOLCAN
        .replace("_", " ")
        .strip()
        .casefold()
    )

    nombres = (
        flujos[CAMPO_FLUJOS]
        .astype(str)
        .str.strip()
        .str.casefold()
    )

    flujos_volcan = flujos[
        nombres == nombre_objetivo
    ].copy()

    if flujos_volcan.empty:

        print(
            f"No se encontraron flujos historicos "
            f"para {VOLCAN}."
        )

        return

    flujos_volcan = flujos_volcan.to_crs(
        crs_destino
    )

    flujos_volcan.to_file(
        GPKG_SALIDA,
        layer="flujos_historicos",
        driver="GPKG"
    )

    print(
        f"Flujos encontrados: {len(flujos_volcan)}"
    )


def generar_resumen(
    gdf
):
    """
    Genera estadísticas y cantidad de pixeles
    en cada categoria.
    """

    print("\n========================================")
    print("7. GENERANDO RESUMEN")
    print("========================================")

    resumen = (
        gdf
        .groupby(
            [
                "clase",
                "categoria"
            ],
            observed=False
        )
        .agg(
            numero_pixeles=(
                "disp_cm",
                "size"
            ),
            minimo_cm=(
                "disp_cm",
                "min"
            ),
            maximo_cm=(
                "disp_cm",
                "max"
            ),
            promedio_cm=(
                "disp_cm",
                "mean"
            ),
        )
        .reset_index()
        .sort_values(
            "clase"
        )
    )

    resumen.to_csv(
        CSV_RESUMEN,
        index=False
    )

    print(
        resumen.to_string(
            index=False
        )
    )

    print(
        f"\nResumen guardado:\n{CSV_RESUMEN}"
    )


def imprimir_estadisticas(
    gdf
):
    """
    Estadísticas básicas.
    """

    valores = gdf[
        "disp_cm"
    ]

    print("\n========================================")
    print("ESTADISTICAS DEL DESPLAZAMIENTO")
    print("========================================")

    print(
        f"Numero de pixeles : "
        f"{len(valores):,}"
    )

    print(
        f"Minimo            : "
        f"{valores.min():.3f} cm"
    )

    print(
        f"Maximo            : "
        f"{valores.max():.3f} cm"
    )

    print(
        f"Promedio          : "
        f"{valores.mean():.3f} cm"
    )

    print(
        f"Mediana           : "
        f"{valores.median():.3f} cm"
    )

    print(
        f"Desv. estandar    : "
        f"{valores.std():.3f} cm"
    )


# ============================================================
# 6. PROGRAMA PRINCIPAL
# ============================================================

def main():

    print("\n")
    print("========================================")
    print(" PIPELINE INSAR - MINTPY")
    print("========================================")
    print(
        f"Volcan : {VOLCAN}"
    )
    print(
        f"Fecha  : {FECHA}"
    )

    # --------------------------------------------------------
    # Verificaciones
    # --------------------------------------------------------

    verificar_archivo(
        TIMESERIES,
        "geo_timeseries.h5"
    )

    verificar_archivo(
        MASCARA,
        "mascara espacial"
    )

    # --------------------------------------------------------
    # MintPy -> GeoTIFF
    # --------------------------------------------------------

    generar_geotiff_mintpy()

    # --------------------------------------------------------
    # Leer máscara
    # --------------------------------------------------------

    area = leer_mascara()

    # --------------------------------------------------------
    # Recorte
    # --------------------------------------------------------

    raster_crs = recortar_raster(
        area
    )

    # --------------------------------------------------------
    # Raster -> puntos
    # --------------------------------------------------------

    gdf = raster_a_puntos()

    # --------------------------------------------------------
    # Estadísticas
    # --------------------------------------------------------

    imprimir_estadisticas(
        gdf
    )

    # --------------------------------------------------------
    # Crear GeoPackage
    # --------------------------------------------------------

    guardar_desplazamiento(
        gdf
    )

    # Agregar área de estudio
    agregar_mascara_al_gpkg(
        area,
        raster_crs
    )

    # Agregar flujos históricos
    agregar_flujos_historicos(
        raster_crs
    )

    # --------------------------------------------------------
    # Resumen
    # --------------------------------------------------------

    generar_resumen(
        gdf
    )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print("\n========================================")
    print("PROCESO TERMINADO")
    print("========================================")

    print(
        "\nGeoTIFF original:"
        f"\n{TIF_ORIGINAL}"
    )

    print(
        "\nGeoTIFF recortado:"
        f"\n{TIF_RECORTADO}"
    )

    print(
        "\nGeoPackage:"
        f"\n{GPKG_SALIDA}"
    )

    print(
        "\nCSV resumen:"
        f"\n{CSV_RESUMEN}"
    )

    print("\nCapas del GeoPackage:")

    print(
        "  - desplazamiento"
    )

    print(
        "  - area_estudio"
    )

    if (
        FLUJOS_HISTORICOS is not None
        and FLUJOS_HISTORICOS.exists()
    ):
        print(
            "  - flujos_historicos"
        )

    print("\n")


# ============================================================
# 7. EJECUCION
# ============================================================

if __name__ == "__main__":
    main()
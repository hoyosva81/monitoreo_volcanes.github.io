from pathlib import Path
import json
import subprocess
import tempfile

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask


# ============================================================
# CONFIGURACION
# ============================================================

VOLCAN = "Palmares Cenizosa"

ID_VOLCAN = "palmares_cenizosa"

TIMESERIES = Path(
    "/run/media/spinedas1/Seagate/saocom/desc137/"
    "PalmaresCenizosa/geo/geo_timeseries_ERA5_ramp_demErr.h5"
)

MASCARA = Path(
    "/run/media/spinedas1/Seagate/Diapiros/Desarrollos/"
    "Volcanes_lodo/Shp_radios_influencia/"
    "radios_influencia.shp"
)

CAMPO_VOLCAN = "nombre"

SALIDA = Path(
    "data/series/Palmares_Cenizosa.json"
)


# ============================================================
# LEER FECHAS DEL TIMESERIES
# ============================================================

def obtener_fechas():

    comando = [
        "info.py",
        str(TIMESERIES),
        "--date"
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        check=True
    )

    fechas = []

    for linea in resultado.stdout.splitlines():

        linea = linea.strip()

        if (
            len(linea) == 8
            and linea.isdigit()
        ):
            fechas.append(
                linea
            )

    if not fechas:

        raise RuntimeError(
            "No se encontraron fechas en el timeseries."
        )

    return fechas


# ============================================================
# LEER MASCARA
# ============================================================

def obtener_area():

    mascaras = gpd.read_file(
        MASCARA
    )

    area = mascaras[
        mascaras[
            CAMPO_VOLCAN
        ]
        .astype(str)
        .str.strip()
        .str.casefold()
        ==
        VOLCAN
        .strip()
        .casefold()
    ].copy()

    if area.empty:

        raise ValueError(
            f"No se encontro la mascara de {VOLCAN}"
        )

    return area


# ============================================================
# CALCULAR PROMEDIO DE UNA FECHA
# ============================================================

def procesar_fecha(
    fecha,
    area,
    carpeta_temporal
):

    tif = (
        carpeta_temporal
        / f"{fecha}.tif"
    )


    comando = [
        "save_gdal.py",
        str(TIMESERIES),
        "-d",
        fecha,
        "-o",
        str(tif)
    ]


    subprocess.run(
        comando,
        check=True
    )


    with rasterio.open(
        tif
    ) as src:

        area_raster = area.to_crs(
            src.crs
        )


        geometrias = [
            geometria.__geo_interface__
            for geometria
            in area_raster.geometry
        ]


        datos, _ = rio_mask(
            src,
            geometrias,
            crop=True,
            filled=False
        )


        valores_m = (
            datos[0]
            .compressed()
            .astype(float)
        )


    valores_m = valores_m[
        np.isfinite(
            valores_m
        )
    ]


    if valores_m.size == 0:

        return None


    valores_cm = (
        valores_m
        * 100.0
    )


    return {
        "fecha":
            fecha,

        "promedio_cm":
            float(
                np.mean(
                    valores_cm
                )
            ),

        "minimo_cm":
            float(
                np.min(
                    valores_cm
                )
            ),

        "maximo_cm":
            float(
                np.max(
                    valores_cm
                )
            )
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        f"\nGenerando serie temporal: {VOLCAN}\n"
    )


    fechas = obtener_fechas()

    print(
        f"Fechas encontradas: {len(fechas)}"
    )


    area = obtener_area()


    serie = []


    with tempfile.TemporaryDirectory() as tmp:

        carpeta_temporal = Path(
            tmp
        )


        for i, fecha in enumerate(
            fechas,
            start=1
        ):

            print(
                f"[{i}/{len(fechas)}] {fecha}"
            )


            resultado = procesar_fecha(
                fecha,
                area,
                carpeta_temporal
            )


            if resultado is not None:

                serie.append(
                    resultado
                )


    salida = {

        "id":
            ID_VOLCAN,

        "nombre":
            VOLCAN,

        "unidad":
            "cm",

        "variable":
            "desplazamiento_LOS_promedio",

        "serie":
            serie
    }


    SALIDA.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    with open(
        SALIDA,
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            salida,
            archivo,
            indent=2,
            ensure_ascii=False
        )


    print(
        "\nSerie temporal guardada en:"
    )

    print(
        SALIDA
    )


if __name__ == "__main__":
    main()

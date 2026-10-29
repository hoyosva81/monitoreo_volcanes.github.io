import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import importar_fichas_docx as imp


def seccion(*lineas):
    return {"nombre": "Prueba", "lineas": list(lineas), "imagenes": []}


class ImportarFichasDocxTest(unittest.TestCase):
    def test_extrae_campos_de_una_ficha_con_tabla(self):
        datos = imp.extraer_volcan(seccion(
            "1. Identificación y Ubicación General",
            "Nombre principal", "Las Platas, Santa fé de las Platas.",
            "Municipio", "Arboletes", "Altitud", "322 m.s.n.m",
            "Ubicado en la vereda El Volcán, corregimiento Santafé de Las Platas, municipio de Arboletes, sobre un edificio.",
            "2. Clasificación y Contexto", "Tipo: Tipo I",
            "3. Actividad Histórica", "Estado de actividad:", "02/12/1991", "01/11/2006",
            "4. Monitoreo e Infraestructura de Vigilancia",
            "Red de monitoreo: No existe una red de monitoreo instrumental (estaciones sísmicas, GPS/InSAR).",
            "5. Gestión del Riesgo - Socionatural",
            "Construcciones afectadas en radio fijo (500 m / 1 km): 33 construcciones se encuentran dentro de "
            "500 m de radio alrededor del cráter y  68 dentro de 1 km (conteo acumulado).",
            "Infraestructura crítica expuesta:  Vía Veredal",
        ))
        self.assertEqual(datos["municipio"], "Arboletes")
        self.assertEqual(datos["altitud_msnm"], 322)
        self.assertEqual(datos["tipo"], "Tipo I")
        self.assertEqual(datos["vereda"], "El Volcán")
        self.assertEqual([e["fecha"] for e in datos["erupciones"]], ["1991-12-02", "2006-11-01"])
        self.assertEqual(datos["afectaciones"]["construcciones_500m"], 33)
        self.assertEqual(datos["afectaciones"]["construcciones_1km"], 68)
        self.assertEqual(datos["afectaciones"]["infraestructura_critica"], "Vía Veredal")
        self.assertNotIn("InSAR", datos["red_monitoreo"])

    def test_separa_notas_internas_del_texto_publico(self):
        datos = imp.extraer_volcan(seccion(
            "1. Identificación y Ubicación General", "Municipio: NECOCLÍ", "Elevación: 190 m s.n.m.",
            "3. Actividad Histórica y Estado Operativo",
            "Última erupción conocida: Registro histórico de erupciones (dato aportado por Emilio): "
            "un evento sin fecha exacta registrada, y otro el 11 de agosto de 2026.",
            "5. Gestión del Riesgo y Entorno Socionatural",
            "Población en riesgo / área de influencia (500 m / 1 km / 2 km): PENDIENTE — requiere la capa de viviendas.",
            "Construcciones afectadas en radio fijo (500 m / 1 km): 0 dentro de 500 m; 0 dentro de 1 km (conteo "
            "acumulado). Fuente: capa Construcciones_Afectadas cargada por Emilio (D:\\SAMA\\datos.gdb).",
        ))
        self.assertEqual(datos["municipio"], "Necoclí")
        self.assertNotIn("Emilio", datos["ultima_erupcion_texto"])
        self.assertEqual([e["fecha"] for e in datos["erupciones"]], ["2026-08-11"])
        self.assertEqual(datos["afectaciones"]["poblacion"], "")
        self.assertIn("Emilio", datos["notas_internas"])

    def test_no_toma_fechas_del_contexto_regional(self):
        datos = imp.extraer_volcan(seccion(
            "3. Actividad Histórica y Estado Operativo",
            "Última erupción conocida: No se encontró un evento documentado específico.",
            "Contexto regional sin vínculo confirmado: el 26 de febrero de 2026 se registró un evento.",
        ))
        self.assertNotIn("erupciones", datos)

    def test_fecha_01_01_con_marcador_queda_con_precision_de_anio(self):
        datos = imp.extraer_volcan(seccion(
            "3. Actividad Histórica y Estado Operativo",
            "Última erupción conocida: 1 de enero de 1993 (posible marcador de año conocido). "
            "Evento del 3 de junio de 2016: erupción intensa.",
        ))
        self.assertEqual(
            [(e["fecha"], e["precision"]) for e in datos["erupciones"]],
            [("1993", "anio"), ("2016-06-03", "dia")],
        )

    def test_resume_el_texto_de_amenaza(self):
        self.assertIn("Q-LavHA", imp.resumir_amenaza("Modelado de amenaza Q-LavHA COMPLETADO (Informe, avance 100%)"))
        self.assertTrue(imp.resumir_amenaza("No incluido en el modelado de amenaza Q-LavHA").startswith("Sin modelado"))
        self.assertEqual(imp.resumir_amenaza("Baja - Turístico."), "Baja - Turístico.")


if __name__ == "__main__":
    unittest.main()

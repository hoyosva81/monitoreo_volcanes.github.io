import http.client
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import boletin_comun as bc
import editor_boletin


def png_de_prueba():
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buffer, "PNG")
    return buffer.getvalue()


class EditorBoletinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporal = tempfile.TemporaryDirectory()
        cls.raiz = Path(cls.temporal.name)
        (cls.raiz / "data").mkdir()
        (cls.raiz / "assets" / "logos").mkdir(parents=True)
        (cls.raiz / "assets" / "logos" / "sama.png").write_bytes(png_de_prueba())
        (cls.raiz / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"id": "volcan_uno", "nombre": "Volcán Uno"}, "geometry": None},
                {"type": "Feature", "properties": {"id": "volcan_dos", "nombre": "Volcán Dos"}, "geometry": None},
            ],
        }
        (cls.raiz / "data" / "volcanes.geojson").write_text(json.dumps(geojson), encoding="utf-8")
        cls.servidor = editor_boletin.crear_servidor(cls.raiz, 0)
        cls.puerto = cls.servidor.server_address[1]
        cls.hilo = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.temporal.cleanup()

    def peticion(self, metodo, ruta, cuerpo=None, host=None, origen=None, editor=True):
        conexion = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=5)
        conexion.putrequest(metodo, ruta, skip_host=True)
        conexion.putheader("Host", host or f"localhost:{self.puerto}")
        if origen:
            conexion.putheader("Origin", origen)
        if editor:
            conexion.putheader("X-Boletin-Editor", "1")
        conexion.putheader("Content-Length", str(len(cuerpo or b"")))
        conexion.endheaders(cuerpo or b"")
        respuesta = conexion.getresponse()
        datos = respuesta.read()
        conexion.close()
        return respuesta.status, datos

    def peticion_json(self, *args, **kwargs):
        estado, datos = self.peticion(*args, **kwargs)
        return estado, json.loads(datos.decode("utf-8"))

    def boletin_valido(self):
        return json.dumps({"general": {"numero_boletin": "1"}, "volcanes": {"volcan_uno": {"municipio": "Turbo"}}}).encode()

    # ------------------------------------------------------------

    def test_ping_y_archivos_estaticos(self):
        self.assertEqual(self.peticion_json("GET", "/api/ping"), (200, {"editor": True}))
        estado, cuerpo = self.peticion("GET", "/index.html")
        self.assertEqual((estado, cuerpo), (200, b"<html>ok</html>"))

    def test_guarda_boletin_y_crea_copia(self):
        estado, _ = self.peticion_json("PUT", "/api/boletin", self.boletin_valido())
        self.assertEqual(estado, 200)
        destino = self.raiz / "data" / "boletin.json"
        self.assertEqual(json.loads(destino.read_text(encoding="utf-8"))["volcanes"]["volcan_uno"]["municipio"], "Turbo")

        nuevo = json.dumps({"general": {}, "volcanes": {"volcan_dos": {}}}).encode()
        self.assertEqual(self.peticion_json("PUT", "/api/boletin", nuevo)[0], 200)
        copia = json.loads((self.raiz / "data" / "boletin.json.bak").read_text(encoding="utf-8"))
        self.assertIn("volcan_uno", copia["volcanes"])

    def test_rechaza_boletin_invalido(self):
        self.assertEqual(self.peticion_json("PUT", "/api/boletin", b"no es json")[0], 400)
        self.assertEqual(self.peticion_json("PUT", "/api/boletin", b'{"general": {}}')[0], 400)
        desconocido = json.dumps({"general": {}, "volcanes": {"../etc": {}}}).encode()
        estado, respuesta = self.peticion_json("PUT", "/api/boletin", desconocido)
        self.assertEqual(estado, 400)
        self.assertIn("desconocidos", respuesta["error"])

    def test_rechaza_escrituras_que_no_vienen_del_editor(self):
        cuerpo = self.boletin_valido()
        self.assertEqual(self.peticion_json("PUT", "/api/boletin", cuerpo, host="evil.example.com")[0], 403)
        self.assertEqual(self.peticion_json("PUT", "/api/boletin", cuerpo, origen="https://evil.example.com")[0], 403)
        self.assertEqual(self.peticion_json("PUT", "/api/boletin", cuerpo, editor=False)[0], 403)
        self.assertEqual(
            self.peticion_json("PUT", "/api/boletin", cuerpo, origen=f"http://localhost:{self.puerto}")[0], 200
        )

    def test_sube_imagen_comprimida_a_webp(self):
        estado, respuesta = self.peticion_json("POST", "/api/imagen?volcan=volcan_uno&rol=morfometria", png_de_prueba())
        self.assertEqual(estado, 200)
        self.assertRegex(respuesta["archivo"], r"^\./assets/mapas/volcan_uno/morfometria-\d+\.webp$")
        archivo = self.raiz / respuesta["archivo"]
        with Image.open(archivo) as imagen:
            self.assertEqual(imagen.format, "WEBP")

        estado, respuesta = self.peticion_json("POST", "/api/imagen?volcan=volcan_dos&rol=galeria", png_de_prueba())
        self.assertEqual(estado, 200)
        self.assertRegex(respuesta["archivo"], r"^\./assets/fotos/volcan_dos/galeria-\d+\.webp$")

    def test_rechaza_imagenes_invalidas(self):
        self.assertEqual(self.peticion_json("POST", "/api/imagen?volcan=otro&rol=foto", png_de_prueba())[0], 400)
        self.assertEqual(self.peticion_json("POST", "/api/imagen?volcan=volcan_uno&rol=../x", png_de_prueba())[0], 400)
        self.assertEqual(self.peticion_json("POST", "/api/imagen?volcan=volcan_uno&rol=foto", b"MZ-no-imagen")[0], 400)
        self.assertEqual(self.peticion_json("POST", "/api/imagen?volcan=../..&rol=foto", png_de_prueba())[0], 400)

    def test_borra_solo_imagenes_de_fotos_y_mapas(self):
        _, subida = self.peticion_json("POST", "/api/imagen?volcan=volcan_uno&rol=mapa_amenaza", png_de_prueba())
        archivo = self.raiz / subida["archivo"]
        self.assertTrue(archivo.exists())
        estado, _ = self.peticion_json("DELETE", "/api/imagen?archivo=" + subida["archivo"])
        self.assertEqual(estado, 200)
        self.assertFalse(archivo.exists())

        logo = self.raiz / "assets" / "logos" / "sama.png"
        for ruta in (
            "./assets/logos/sama.png",
            "./assets/mapas/../logos/sama.png",
            "../data/volcanes.geojson",
            "./assets/mapas/volcan_uno/../../logos/sama.webp",
        ):
            self.assertEqual(self.peticion_json("DELETE", "/api/imagen?archivo=" + ruta)[0], 400, ruta)
        self.assertTrue(logo.exists())


class UtilidadesBoletinTest(unittest.TestCase):
    def test_fusionar_no_pisa_ediciones_salvo_forzar(self):
        actual = {"municipio": "Turbo", "tipo": "", "afectaciones": {"construcciones_500m": 5}}
        nuevo = {"municipio": "Necoclí", "tipo": "Tipo I", "afectaciones": {"construcciones_500m": 9, "poblacion": "x"}}
        bc.fusionar(actual, nuevo)
        self.assertEqual(actual["municipio"], "Turbo")
        self.assertEqual(actual["tipo"], "Tipo I")
        self.assertEqual(actual["afectaciones"], {"construcciones_500m": 5, "poblacion": "x"})
        bc.fusionar(actual, nuevo, forzar=True)
        self.assertEqual(actual["municipio"], "Necoclí")

    def test_normaliza_nombres_con_acentos_y_prefijo(self):
        self.assertEqual(bc.normalizar("Volcán Vereda Molinillo"), "veredamolinillo")
        self.assertEqual(bc.normalizar("Gigantón"), bc.normalizar("Giganton"))


if __name__ == "__main__":
    unittest.main()

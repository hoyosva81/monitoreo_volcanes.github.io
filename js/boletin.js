// Ficha técnica de cada volcán (estilo «Boletín de Diapiros de Lodo» de SAMA).
//
// Los textos y cifras salen de data/boletin.json (campo `volcanes.<id>`), las
// coordenadas de data/volcanes.geojson y la línea de monitoreo InSAR de la
// metadata del volcán. Todo el texto se inserta con textContent.

const MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
    "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
];

const COLORES_NIVEL = {
    base: "#8dc63f",
    moderada: "#f2c230",
    alta: "#e53935"
};

const $ = id => document.getElementById(id);


// ============================================================
// FORMATO
// ============================================================

function numero(valor, decimales = 1) {
    const n = Number(valor);

    if (valor === null || valor === undefined || !Number.isFinite(n)) {
        return null;
    }

    return n.toLocaleString("es", {
        minimumFractionDigits: decimales,
        maximumFractionDigits: decimales
    });
}

export function aDMS(valor, positivo, negativo) {
    const n = Number(valor);

    if (!Number.isFinite(n)) {
        return "";
    }

    const hemisferio = n >= 0 ? positivo : negativo;
    const absoluto = Math.abs(n);
    let grados = Math.floor(absoluto);
    const minutosTotales = (absoluto - grados) * 60;
    let minutos = Math.floor(minutosTotales);
    let segundos = Number(((minutosTotales - minutos) * 60).toFixed(2));

    if (segundos >= 60) {
        segundos = 0;
        minutos += 1;
    }

    if (minutos >= 60) {
        minutos = 0;
        grados += 1;
    }

    return `${grados}°${minutos}'${segundos.toFixed(2)}"${hemisferio}`;
}

function partesFecha(texto) {
    const coincidencia = /^(\d{4})(?:-?(\d{2}))?(?:-?(\d{2}))?$/.exec(
        String(texto || "").trim()
    );

    if (!coincidencia) {
        return null;
    }

    return {
        anio: coincidencia[1],
        mes: coincidencia[2] || null,
        dia: coincidencia[3] || null
    };
}

export function formatearFechaCorta(texto) {
    const partes = partesFecha(texto);

    if (!partes) {
        return String(texto || "");
    }

    if (partes.dia && partes.mes) {
        return `${partes.dia}/${partes.mes}/${partes.anio}`;
    }

    if (partes.mes) {
        return `${partes.mes}/${partes.anio}`;
    }

    return partes.anio;
}

export function fechaDeBoletin(texto) {
    const partes = partesFecha(texto);

    if (!partes || !partes.mes || !partes.dia) {
        return "--";
    }

    return `${MESES[Number(partes.mes) - 1]} ${partes.dia}/${partes.anio}`;
}

function plural(cantidad, singular, plurales) {
    return `${cantidad} ${Number(cantidad) === 1 ? singular : plurales}`;
}

export function municipioPorPunto(municipios, lon, lat) {
    function dentroDelAnillo(anillo) {
        let dentro = false;

        for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
            const [xi, yi] = anillo[i];
            const [xj, yj] = anillo[j];

            if (
                (yi > lat) !== (yj > lat) &&
                lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
            ) {
                dentro = !dentro;
            }
        }

        return dentro;
    }

    function dentroDelPoligono(anillos) {
        return (
            dentroDelAnillo(anillos[0]) &&
            !anillos.slice(1).some(dentroDelAnillo)
        );
    }

    for (const feature of municipios?.features || []) {
        const geometria = feature.geometry;

        if (!geometria) {
            continue;
        }

        const poligonos = geometria.type === "Polygon"
            ? [geometria.coordinates]
            : geometria.type === "MultiPolygon"
                ? geometria.coordinates
                : [];

        if (poligonos.some(dentroDelPoligono)) {
            return feature.properties?.municipality || null;
        }
    }

    return null;
}


// ============================================================
// UTILIDADES DE DOM
// ============================================================

function hayTexto(valor) {
    return (
        valor !== null &&
        valor !== undefined &&
        String(valor).trim() !== ""
    );
}

function fijar(id, valor, edicion, vacio = "Sin información") {
    const elemento = $(id);

    if (!elemento) {
        return;
    }

    const hay = hayTexto(valor);

    elemento.textContent = hay
        ? String(valor)
        : (edicion ? "Por completar" : vacio);

    elemento.classList.toggle("vacio", !hay);
}

function crear(etiqueta, clase, texto) {
    const elemento = document.createElement(etiqueta);

    if (clase) {
        elemento.className = clase;
    }

    if (texto !== undefined) {
        elemento.textContent = texto;
    }

    return elemento;
}

function fijarImagen(idFigura, imagen, alt, edicion) {
    const figura = $(idFigura);

    if (!figura) {
        return;
    }

    const img = figura.querySelector("img");
    const pie = figura.querySelector("figcaption");
    const archivo = imagen?.archivo;

    figura.classList.toggle("sin-imagen", !archivo);
    figura.dataset.vacio = edicion
        ? "Por completar: suba una imagen"
        : "Imagen no disponible";

    if (archivo) {
        img.src = archivo;
        img.alt = imagen.alt || alt;
        img.hidden = false;
        img.tabIndex = 0;
        img.dataset.pie = imagen.pie || "";
    } else {
        img.removeAttribute("src");
        img.alt = "";
        img.hidden = true;
        img.removeAttribute("tabindex");
    }

    if (pie) {
        pie.textContent = archivo ? (imagen.pie || "") : "";
        pie.hidden = !archivo || !imagen.pie;
    }
}


// ============================================================
// FICHA
// ============================================================

function textoRedMonitoreo(ctx) {
    const partes = [];

    if (hayTexto(ctx.ficha.red_monitoreo)) {
        partes.push(ctx.ficha.red_monitoreo.trim());
    }

    if (ctx.estaciones.length > 0) {
        partes.push(
            `Estaciones sísmicas registradas en el portal: ${ctx.estaciones.length}.`
        );
    }

    if (ctx.tieneInsar) {
        const metadata = ctx.metadata || {};
        const detalle = [metadata.sensor, metadata.geometria]
            .filter(Boolean)
            .join(", ");
        const referencia = metadata.fecha_referencia
            ? ` Fecha de referencia: ${formatearFechaCorta(metadata.fecha_referencia)}.`
            : "";

        partes.push(
            `Monitoreo satelital InSAR${detalle ? ` (${detalle})` : ""}.${referencia}`
        );
    }

    return partes.join(" ");
}

function textoConstrucciones(afectaciones) {
    const cerca = afectaciones.construcciones_500m;
    const lejos = afectaciones.construcciones_1km;

    if (!Number.isFinite(Number(cerca)) || !Number.isFinite(Number(lejos))) {
        return "";
    }

    return (
        "Construcciones afectadas en radio fijo (500 m / 1 km): " +
        `${plural(cerca, "construcción se encuentra", "construcciones se encuentran")} ` +
        "dentro de 500 m de radio alrededor del cráter y " +
        `${lejos} dentro de 1 km (conteo acumulado, incluye las de 500 m).`
    );
}

function renderizarErupciones(erupciones, edicion) {
    const lista = $("f-erupciones");
    lista.replaceChildren();

    const ordenadas = [...(erupciones || [])]
        .filter(e => hayTexto(e.fecha))
        .sort((a, b) => String(b.fecha).localeCompare(String(a.fecha)));

    lista.classList.toggle("sin-eventos", ordenadas.length === 0);

    for (const evento of ordenadas.slice(0, 4)) {
        const item = crear("li");
        item.append(crear("b", "", formatearFechaCorta(evento.fecha)));

        if (hayTexto(evento.descripcion)) {
            item.append(crear("span", "", ` · ${evento.descripcion}`));
        }

        lista.append(item);
    }

    if (ordenadas.length === 0) {
        lista.append(
            crear(
                "li",
                "vacio",
                edicion ? "Por completar" : "Sin eventos documentados"
            )
        );
    }

    if (ordenadas.length > 4) {
        const restantes = ordenadas.length - 4;

        lista.append(
            crear(
                "li",
                "mas",
                `+ ${restantes} ${restantes === 1 ? "evento anterior" : "eventos anteriores"}`
            )
        );
    }
}

function renderizarNiveles(general, nivelVigente) {
    const contenedor = $("f-niveles");
    contenedor.replaceChildren();

    for (const nivel of general.niveles_alerta || []) {
        const bloque = crear("div", "nivel");
        bloque.style.setProperty(
            "--c",
            COLORES_NIVEL[nivel.id] || "#52667a"
        );
        bloque.append(crear("h4", "", nivel.titulo || ""));
        bloque.append(crear("p", "", nivel.descripcion || ""));

        if (nivelVigente && nivelVigente === nivel.id) {
            bloque.classList.add("activo");
            bloque.append(crear("span", "vigente", "Nivel vigente"));
        }

        contenedor.append(bloque);
    }
}

function chipsMorfometria(m) {
    if (!m) {
        return [];
    }

    const dmax = numero(m.dmax_m, 0);
    const dmin = numero(m.dmin_m, 0);

    return [
        hayTexto(m.clase) && `Clase: ${m.clase}`,
        hayTexto(m.tamano) && `Tamaño: ${m.tamano}`,
        numero(m.altura_m) && `H = ${numero(m.altura_m)} m`,
        dmax && dmin && `Dmax × Dmin = ${dmax} × ${dmin} m`,
        numero(m.arctan_hr_grados) && `arctan(H/R) = ${numero(m.arctan_hr_grados)}°`
    ].filter(Boolean);
}

export function renderizarFicha(ctx) {
    const { ficha, general } = ctx;
    const edicion = Boolean(ctx.editando);
    const afectaciones = ficha.afectaciones || {};
    const imagenes = ficha.imagenes || {};
    const morfometria = ficha.morfometria || null;
    const [lon, lat] = ctx.coordenadas || [];

    $("ficha-boletin").classList.toggle("modo-edicion", edicion);

    // Encabezado
    fijar("f-numero", general.numero_boletin, edicion, "XXXXXXX");
    fijar(
        "f-fecha",
        fechaDeBoletin(general.fecha_boletin || ficha.actualizado),
        edicion
    );
    fijar("f-red-social", general.red_social, edicion, "");

    // Identificación
    fijar("f-nombre", ficha.nombre_principal || ctx.nombre, edicion);
    fijar("f-municipio", ficha.municipio, edicion);
    fijar("f-vereda", ficha.vereda, edicion);
    $("f-vereda-fila").hidden = !edicion && !hayTexto(ficha.vereda);
    fijar("f-lat", Number.isFinite(lat) ? lat.toFixed(6) : "", edicion);
    fijar("f-lon", Number.isFinite(lon) ? lon.toFixed(6) : "", edicion);
    fijar("f-lat-dms", aDMS(lat, "N", "S"), false, "");
    fijar("f-lon-dms", aDMS(lon, "E", "W"), false, "");
    fijar(
        "f-alt",
        Number.isFinite(Number(ficha.altitud_msnm)) && hayTexto(ficha.altitud_msnm)
            ? `${ficha.altitud_msnm} m.s.n.m`
            : "",
        edicion
    );

    if (!hayTexto(ficha.municipio) && Number.isFinite(lat) && ctx.cargarMunicipios) {
        ctx.cargarMunicipios()
            .then(municipios => {
                const encontrado = municipioPorPunto(municipios, lon, lat);

                if (encontrado && !hayTexto(ctx.ficha.municipio)) {
                    fijar("f-municipio", encontrado, false);
                }
            })
            .catch(error => {
                console.warn("No fue posible calcular el municipio:", error);
            });
    }

    // Imágenes
    fijarImagen(
        "f-foto",
        imagenes.foto,
        `Foto del volcán ${ctx.nombre}`,
        edicion
    );
    fijarImagen(
        "f-ubicacion",
        imagenes.mapa_ubicacion,
        `Mapa de ubicación del volcán ${ctx.nombre}`,
        edicion
    );
    fijarImagen(
        "f-propagacion",
        imagenes.mapa_propagacion,
        `Modelo de propagación del flujo de ${ctx.nombre}`,
        edicion
    );
    fijarImagen(
        "f-amenaza",
        imagenes.mapa_amenaza,
        `Mapa de amenaza de ${ctx.nombre}`,
        edicion
    );
    $("f-foto").hidden = !edicion && !imagenes.foto?.archivo;
    $("f-card-ubicacion").hidden = !edicion && !imagenes.mapa_ubicacion?.archivo;

    // Sin mapa, el texto de la tarjeta ocupa todo el ancho.
    for (const [idFigura, imagen] of [
        ["f-propagacion", imagenes.mapa_propagacion],
        ["f-amenaza", imagenes.mapa_amenaza]
    ]) {
        const oculto = !edicion && !imagen?.archivo;

        $(idFigura).hidden = oculto;
        $(idFigura).closest(".ficha-fila").classList.toggle("sin-mapa", oculto);
    }

    // Clasificación y actividad
    fijar("f-tipo", ficha.tipo, edicion);
    $("f-clase-fila").hidden = !morfometria;
    fijar(
        "f-clase",
        morfometria
            ? [morfometria.clase, morfometria.tamano && `tamaño ${morfometria.tamano.toLowerCase()}`]
                .filter(Boolean)
                .join(" · ")
            : "",
        false
    );
    fijar("f-estado", ficha.estado_actividad, edicion, "");
    $("f-estado").hidden = !edicion && !hayTexto(ficha.estado_actividad);
    $("f-estado").title = ficha.estado_actividad || "";
    renderizarErupciones(ficha.erupciones, edicion);
    fijar("f-red", textoRedMonitoreo(ctx), edicion);

    // Morfología
    const textoMorfologia = [
        ficha.morfologia || general.morfologia,
        morfometria ? "" : general.morfologia_sin_datos
    ].filter(hayTexto).join(" ");

    fijar("f-morfologia", textoMorfologia, edicion);

    const chips = $("f-chips");
    chips.replaceChildren(
        ...chipsMorfometria(morfometria).map(texto => crear("li", "", texto))
    );
    chips.hidden = chips.children.length === 0;
    fijar("f-flujo", ficha.comportamiento_flujo, edicion);

    // Gestión del riesgo
    fijar(
        "f-poblacion",
        hayTexto(afectaciones.poblacion)
            ? `Población en el área de influencia: ${afectaciones.poblacion}`
            : "Población en el área de influencia: sin información.",
        false
    );
    fijar("f-construcciones", textoConstrucciones(afectaciones), edicion, "Sin conteo de construcciones.");
    fijar("f-infra", afectaciones.infraestructura_critica, edicion);
    fijar("f-amenaza-texto", afectaciones.amenaza_texto, edicion, "");
    $("f-amenaza-fila").hidden = !edicion && !hayTexto(afectaciones.amenaza_texto);

    renderizarNiveles(general, ficha.nivel_actividad);

    renderizarComplementos(ctx);
}


// ============================================================
// SECCIONES COMPLEMENTARIAS (morfometría, fuentes, galería)
// ============================================================

function renderizarMorfometria(ctx) {
    const m = ctx.ficha.morfometria;
    const seccion = $("seccion-morfometria");
    const navegacion = $("nav-morfometria");
    const visible = Boolean(m);

    seccion.hidden = !visible;
    navegacion.hidden = !visible;

    if (!visible) {
        return;
    }

    fijar("m-clase", m.clase, false);
    fijar("m-tamano", m.tamano ? `Tamaño ${m.tamano.toLowerCase()}` : "", false, "");
    $("m-tamano").hidden = !m.tamano;

    const porcentaje = Number.isFinite(Number(m.pct_azimuts_interpolados))
        ? Math.round(Number(m.pct_azimuts_interpolados) * 100)
        : null;

    const filas = [
        ["Altura (H)", numero(m.altura_m) && `${numero(m.altura_m)} m`],
        ["Diámetro máximo (Dmax)", numero(m.dmax_m, 0) && `${numero(m.dmax_m, 0)} m`],
        ["Diámetro mínimo (Dmin)", numero(m.dmin_m, 0) && `${numero(m.dmin_m, 0)} m`],
        ["Diámetro medio", numero(m.dmean_m, 0) && `${numero(m.dmean_m, 0)} m`],
        ["Relación H/R", numero(m.hr, 3)],
        ["arctan(H/R)", numero(m.arctan_hr_grados) && `${numero(m.arctan_hr_grados)}°`],
        ["Pendiente local del DEM en la base", numero(m.pendiente_dem_grados) && `${numero(m.pendiente_dem_grados)}°`],
        [
            "Azimuts interpolados",
            Number.isFinite(Number(m.azimuts_interpolados))
                ? `${m.azimuts_interpolados} de 120${porcentaje === null ? "" : ` (${porcentaje} %)`}`
                : null
        ],
        ["DEM usado", m.dem]
    ].filter(([, valor]) => hayTexto(valor));

    $("m-tabla").replaceChildren(
        ...filas.map(([etiqueta, valor]) => {
            const fila = document.createElement("tr");
            fila.append(crear("th", "", etiqueta), crear("td", "", valor));
            return fila;
        })
    );

    const aviso = $("m-aviso");
    aviso.hidden = !m.base_poco_fiable;
    aviso.textContent = m.base_poco_fiable
        ? "La base de este edificio se apoya en muchos azimuts interpolados: " +
          "interprete la altura y el área con cautela."
        : "";

    const figura = $("m-figura");
    const imagen = ctx.ficha.imagenes?.morfometria;

    if (imagen?.archivo) {
        figura.src = imagen.archivo;
        figura.alt =
            `Morfometría de ${ctx.nombre}: mapa del modelo digital de elevación ` +
            "con la base del edificio y perfiles topográficos A-B y C-D.";
        figura.dataset.pie = imagen.pie || "";
        figura.hidden = false;
        figura.tabIndex = 0;
        $("m-pie").textContent = imagen.pie || "";
    } else {
        figura.removeAttribute("src");
        figura.hidden = true;
        $("m-pie").textContent = "Figura no disponible.";
    }
}

function renderizarGaleria(ctx) {
    const fotos = (ctx.ficha.galeria || []).filter(f => f.archivo);
    const galeria = $("galeria");

    $("galeria-bloque").hidden = fotos.length === 0;
    galeria.replaceChildren(
        ...fotos.map((foto, indice) => {
            const figura = crear("figure");
            const img = document.createElement("img");

            img.src = foto.archivo;
            img.alt = foto.alt || `Foto ${indice + 1} del volcán ${ctx.nombre}`;
            img.loading = "lazy";
            img.tabIndex = 0;
            img.dataset.zoom = "";
            img.dataset.pie = foto.pie || "";
            figura.append(img);

            if (foto.pie) {
                figura.append(crear("figcaption", "", foto.pie));
            }

            return figura;
        })
    );
}

// ------------------------------------------------------------
// Línea de tiempo de la actividad (escala proporcional al tiempo)
// ------------------------------------------------------------

const DIA_MS = 24 * 60 * 60 * 1000;

// Separación (px) entre el eje y la etiqueta según la fila que ocupa.
const SEPARACION_FILA = [40, 104];

// Orden de preferencia de las filas: alternan arriba y abajo del eje.
const FILAS_LINEA = [
    { lado: "arriba", fila: 0 },
    { lado: "abajo", fila: 0 },
    { lado: "arriba", fila: 1 },
    { lado: "abajo", fila: 1 }
];

function marcaDeTiempo(texto) {
    const partes = partesFecha(texto);

    if (!partes) {
        return null;
    }

    const anio = Number(partes.anio);
    const mes = partes.mes ? Number(partes.mes) - 1 : 6;
    const dia = partes.dia ? Number(partes.dia) : (partes.mes ? 15 : 1);
    const marca = Date.UTC(anio, mes, dia);

    return Number.isFinite(marca) && mes >= 0 && mes <= 11 ? marca : null;
}

function renderizarLineaTiempo(ctx) {
    const seccion = $("seccion-actividad");
    const contenedor = $("linea-tiempo");
    const caja = contenedor.closest(".linea-tiempo-caja");

    contenedor.replaceChildren();

    const eventos = (ctx.ficha.erupciones || [])
        .map(evento => ({ ...evento, t: marcaDeTiempo(evento.fecha) }))
        .filter(evento => evento.t !== null)
        .sort((a, b) => a.t - b.t);

    const hayUltima = hayTexto(ctx.ficha.ultima_erupcion_texto);
    const visible = eventos.length > 0 || hayUltima;

    seccion.hidden = !visible;
    caja.hidden = eventos.length === 0;

    if (!visible) {
        return;
    }

    if (eventos.length === 0) {
        $("linea-resumen").textContent =
            "No hay erupciones con fecha registrada para este volcán.";
        return;
    }

    // Eje: desde el 1 de enero del primer año hasta hoy (mínimo un año de ancho).
    const hoy = Date.now();
    const ultimo = eventos[eventos.length - 1];
    const fin = Math.max(hoy, ultimo.t + 30 * DIA_MS);
    const inicio = Math.min(
        Date.UTC(new Date(eventos[0].t).getUTCFullYear(), 0, 1),
        fin - 365 * DIA_MS
    );
    const posicion = t => ((t - inicio) / (fin - inicio)) * 100;
    const posicionHoy = posicion(hoy);

    function ponerMarca(t, texto, clase) {
        const marca = crear("li", `marca ${clase || ""}`.trim());
        marca.setAttribute("aria-hidden", "true");
        marca.style.left = `${posicion(t)}%`;
        marca.append(crear("span", "", texto));
        contenedor.append(marca);
    }

    const eje = crear("li", "eje");
    eje.setAttribute("aria-hidden", "true");
    contenedor.append(eje);

    const anioInicio = new Date(inicio).getUTCFullYear();
    const anioFin = new Date(fin).getUTCFullYear();
    const paso = [1, 2, 5, 10, 20, 50].find(
        p => (anioFin - anioInicio) / p <= 8
    ) || 50;

    for (let anio = Math.ceil(anioInicio / paso) * paso; anio <= anioFin; anio += paso) {
        const t = Date.UTC(anio, 0, 1);

        if (t >= inicio && t <= fin && Math.abs(posicion(t) - posicionHoy) > 5) {
            ponerMarca(t, String(anio));
        }
    }

    ponerMarca(hoy, "Hoy", "hoy");

    // Cada evento ocupa la primera fila en la que su etiqueta no choca con la anterior.
    const anchoCaja = contenedor.clientWidth || 900;
    const distanciaMinima = (165 / anchoCaja) * 100;
    const ultimaPosicion = FILAS_LINEA.map(() => -Infinity);
    let filaMaxima = 0;

    for (const evento of eventos) {
        const x = posicion(evento.t);
        let indice = ultimaPosicion.findIndex(previa => x - previa >= distanciaMinima);

        if (indice < 0) {
            indice = ultimaPosicion.indexOf(Math.min(...ultimaPosicion));
        }

        ultimaPosicion[indice] = x;

        const { lado, fila } = FILAS_LINEA[indice];
        const item = crear("li", `evento ${lado}`);

        filaMaxima = Math.max(filaMaxima, fila);

        item.style.left = `${x}%`;
        item.style.setProperty("--sep", `${SEPARACION_FILA[fila]}px`);

        if (x < 9) {
            item.classList.add("alinear-izq");
        } else if (x > 91) {
            item.classList.add("alinear-der");
        }

        const etiqueta = crear("div", "etiqueta");
        etiqueta.append(crear("b", "", formatearFechaCorta(evento.fecha)));

        if (hayTexto(evento.descripcion)) {
            etiqueta.append(crear("span", "", evento.descripcion));
        }

        item.append(crear("span", "tallo"), crear("span", "punto"), etiqueta);
        contenedor.append(item);
    }

    // Altura justa: eje + etiquetas de la fila más lejana usada, a cada lado.
    contenedor.style.height = `${2 * (SEPARACION_FILA[filaMaxima] + 58)}px`;

    const anios = Math.floor((hoy - ultimo.t) / (365.25 * DIA_MS));
    const primerAnio = new Date(eventos[0].t).getUTCFullYear();
    const ultimoAnio = new Date(ultimo.t).getUTCFullYear();

    $("linea-resumen").textContent =
        `${plural(eventos.length, "erupción registrada", "erupciones registradas")}` +
        (eventos.length > 1 ? ` entre ${primerAnio} y ${ultimoAnio}` : ` en ${ultimoAnio}`) +
        `. La más reciente fue ${formatearFechaCorta(ultimo.fecha)}` +
        (anios >= 1 ? ` (hace ${plural(anios, "año", "años")}).` : ".");
}

function renderizarComplementos(ctx) {
    const { ficha, general } = ctx;

    renderizarMorfometria(ctx);
    renderizarGaleria(ctx);
    renderizarLineaTiempo(ctx);

    $("ultima-erupcion-bloque").hidden = !hayTexto(ficha.ultima_erupcion_texto);
    $("ultima-erupcion").textContent = ficha.ultima_erupcion_texto || "";

    $("nota-monitoreo").textContent = general.nota_monitoreo || "";
    $("nota-construcciones").textContent = general.nota_construcciones || "";
    $("nota-vigilancia").textContent = general.entidad_vigilancia
        ? `Entidad encargada de la vigilancia: ${general.entidad_vigilancia}`
        : "";

    $("fuentes-lista").replaceChildren(
        ...(general.fuentes || []).map(fuente => crear("li", "", fuente))
    );

    $("actualizado").textContent = ficha.actualizado
        ? `Ficha actualizada el ${formatearFechaCorta(ficha.actualizado)}.`
        : "";

    $("volcano-subtitle").textContent = [
        ficha.municipio,
        Number.isFinite(Number(ficha.altitud_msnm)) && hayTexto(ficha.altitud_msnm)
            ? `${ficha.altitud_msnm} m s. n. m.`
            : null,
        ficha.tipo
    ].filter(hayTexto).join(" · ");
}


// ============================================================
// VISOR DE IMAGENES
// ============================================================

export function iniciarVisor() {
    const visor = $("visor-imagen");
    const vista = $("bulletin-view");

    if (!visor || visor.dataset.listo) {
        return;
    }

    visor.dataset.listo = "1";

    function abrir(img) {
        if (!img.getAttribute("src")) {
            return;
        }

        visor.querySelector("img").src = img.src;
        visor.querySelector("img").alt = img.alt;
        visor.querySelector("p").textContent = img.dataset.pie || img.alt || "";
        visor.showModal();
    }

    vista.addEventListener("click", evento => {
        const img = evento.target.closest("img[data-zoom]");

        if (img) {
            abrir(img);
        }
    });

    vista.addEventListener("keydown", evento => {
        const img = evento.target.closest?.("img[data-zoom]");

        if (img && (evento.key === "Enter" || evento.key === " ")) {
            evento.preventDefault();
            abrir(img);
        }
    });

    visor.addEventListener("click", evento => {
        if (evento.target === visor) {
            visor.close();
        }
    });
}


// ============================================================
// IMPRESION / PDF
// ============================================================

export async function descargarPDF(ctx) {
    const imagenes = [...document.querySelectorAll("#ficha-boletin img")]
        .filter(img => img.getAttribute("src"));

    await Promise.all(
        imagenes.map(img => (img.decode ? img.decode().catch(() => {}) : null))
    );

    const tituloOriginal = document.title;
    const fecha = (ctx.general.fecha_boletin || ctx.ficha.actualizado || "")
        .replaceAll("-", "");
    const nombre = ctx.nombre
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/[^A-Za-z0-9]+/g, "_");

    document.title = `Boletin_${nombre}${fecha ? `_${fecha}` : ""}`;

    const restaurar = () => {
        document.title = tituloOriginal;
        window.removeEventListener("afterprint", restaurar);
    };

    window.addEventListener("afterprint", restaurar);
    window.print();
}

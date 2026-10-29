import {
    cargarCatalogo,
    cargarVolcanesGeoJSON,
    cargarMunicipiosAntioquia,
    cargarEstacionesSismicas,
    cargarBoletinCampos,
    buscarVolcan,
    obtenerFechas,
    buscarObservacion,
    cargarMetadata,
    cargarArea,
    cargarFlujos,
    cargarEstadisticas,
    cargarSerieTemporal as cargarSerieTemporalJSON,
    contarVolcanesInSAR,
    contarVolcanesSismica
} from "./data.js?v=20261027-ficha-sama";

import {
    crearMapaGeneral,
    crearMapaBoletin
} from "./map.js?v=20261027-uraba2";

import {
    crearGraficaEvolucion
} from "./charts.js?v=20261001-eje-y";

import {
    renderizarFicha,
    iniciarVisor,
    descargarPDF
} from "./boletin.js?v=20261027-linea";


const homeView = document.getElementById("home-view");
const bulletinView = document.getElementById("bulletin-view");
const dateSelect = document.getElementById("date-select");
const backButton = document.getElementById("back-button");


// ============================================================
// INICIO
// ============================================================

async function iniciar() {
    try {
        const parametros = new URLSearchParams(
            window.location.search
        );

        const volcanId = parametros.get("volcan");
        const fechaUrl = parametros.get("fecha");

        const [catalogo, volcanes, boletin] = await Promise.all([
            cargarCatalogo(),
            cargarVolcanesGeoJSON(),
            cargarBoletinCampos()
        ]);

        boletin.general = boletin.general || {};
        boletin.volcanes = boletin.volcanes || {};

        poblarSelectorVolcanes(volcanes, catalogo, volcanId);

        if (!volcanId) {
            await mostrarMapaGeneral(catalogo, volcanes, boletin);
            return;
        }

        await mostrarBoletin(
            catalogo,
            volcanes,
            boletin,
            volcanId,
            fechaUrl
        );
    } catch (error) {
        console.error(
            "Error iniciando el geoportal:",
            error
        );
    }
}


function irAVolcan(volcanId) {
    const url = new URL(
        window.location.href
    );

    url.search = "";
    url.hash = "";
    url.searchParams.set(
        "volcan",
        volcanId
    );

    window.location.href = url.toString();
}


function poblarSelectorVolcanes(volcanes, catalogo, volcanActual) {
    const selector = document.getElementById("volcano-nav-select");

    if (!selector) {
        return;
    }

    const conInsar = new Set(
        (catalogo.volcanes || []).map(volcan => volcan.id)
    );

    const ordenados = [...(volcanes.features || [])]
        .map(feature => feature.properties || {})
        .filter(propiedades => propiedades.id)
        .sort(
            (a, b) => String(a.nombre).localeCompare(String(b.nombre), "es")
        );

    for (const propiedades of ordenados) {
        const opcion = document.createElement("option");
        opcion.value = propiedades.id;
        opcion.textContent = conInsar.has(propiedades.id)
            ? `${propiedades.nombre} · InSAR`
            : propiedades.nombre;
        selector.appendChild(opcion);
    }

    selector.value = volcanActual || "";

    selector.addEventListener("change", () => {
        if (selector.value) {
            irAVolcan(selector.value);
        }
    });
}


// ============================================================
// MAPA GENERAL
// ============================================================

async function mostrarMapaGeneral(catalogo, volcanes, boletin) {
    homeView.hidden = false;
    bulletinView.hidden = true;

    let municipiosAntioquia = null;

    try {
        municipiosAntioquia = await cargarMunicipiosAntioquia();
    } catch (error) {
        console.warn(
            "No fue posible cargar los límites municipales de Antioquia:",
            error
        );
    }

    const volcanesInSAR = new Set(
        (catalogo.volcanes || []).map(volcan => volcan.id)
    );

    let estaciones = {
        type: "FeatureCollection",
        features: []
    };

    try {
        estaciones = await cargarEstacionesSismicas();
    } catch (error) {
        console.warn(
            "No fue posible cargar las estaciones sísmicas:",
            error
        );
    }

    const volcanesSismica = new Set(
        (estaciones.features || [])
            .map(feature => feature.properties?.volcan_id)
            .filter(Boolean)
    );

    volcanes = {
        ...volcanes,
        features: (volcanes.features || []).map(feature => {
            const id = feature.properties?.id;
            const ficha = boletin.volcanes[id] || {};

            return {
                ...feature,
                properties: {
                    ...feature.properties,
                    tiene_insar: volcanesInSAR.has(id),
                    tiene_sismica: volcanesSismica.has(id),
                    municipio: ficha.municipio || null,
                    altitud_msnm: ficha.altitud_msnm ?? null,
                    clase: ficha.morfometria?.clase || null
                }
            };
        })
    };

    colocarTexto(
        "stat-volcanic-buildings",
        volcanes.features?.length || 0
    );

    colocarTexto(
        "stat-insar",
        contarVolcanesInSAR(catalogo)
    );

    colocarTexto(
        "stat-seismic",
        contarVolcanesSismica(estaciones)
    );

    crearMapaGeneral(
        volcanes,
        irAVolcan,
        municipiosAntioquia
    );
}


// ============================================================
// BOLETIN
// ============================================================

async function mostrarBoletin(
    catalogo,
    volcanes,
    boletin,
    volcanId,
    fechaUrl
) {
    const feature = (volcanes.features || []).find(
        elemento => elemento.properties?.id === volcanId
    );

    const volcan = buscarVolcan(
        catalogo,
        volcanId
    );

    if (!feature && !volcan) {
        throw new Error(
            `No se encontró el volcán '${volcanId}'.`
        );
    }

    const nombre =
        volcan?.nombre ||
        feature?.properties?.nombre ||
        volcanId;

    homeView.hidden = true;
    bulletinView.hidden = false;

    colocarTexto(
        "volcano-name",
        nombre
    );

    document.title = `${nombre} | SAMA`;

    backButton.onclick = () => {
        window.location.href = window.location.pathname;
    };

    ajustarAlturaCabecera();
    iniciarVisor();

    // --------------------------------------------------------
    // Estaciones sísmicas del volcán (las usan el mapa InSAR
    // y la línea de monitoreo de la ficha).
    // --------------------------------------------------------

    let estacionesVolcan = {
        type: "FeatureCollection",
        features: []
    };

    try {
        const estaciones = await cargarEstacionesSismicas();
        estacionesVolcan.features = (estaciones.features || []).filter(
            elemento => elemento.properties?.volcan_id === volcanId
        );
    } catch (error) {
        console.warn(
            "No fue posible cargar las estaciones sísmicas del volcán:",
            error
        );
    }

    // --------------------------------------------------------
    // Monitoreo InSAR (solo volcanes del catálogo)
    // --------------------------------------------------------

    let metadata = null;

    document.getElementById("seccion-insar").hidden = !volcan;
    document.getElementById("nav-insar").hidden = !volcan;
    document.getElementById("insar-aviso").hidden = Boolean(volcan);

    if (volcan) {
        try {
            metadata = await mostrarInsar(
                volcan,
                estacionesVolcan,
                fechaUrl
            );
        } catch (error) {
            console.error(
                "Error mostrando el monitoreo InSAR:",
                error
            );
        }
    }

    // --------------------------------------------------------
    // Ficha técnica
    // --------------------------------------------------------

    const contexto = {
        id: volcanId,
        nombre,
        coordenadas: feature?.geometry?.coordinates || null,
        general: boletin.general,
        ficha: boletin.volcanes[volcanId] || {},
        metadata,
        tieneInsar: Boolean(volcan),
        estaciones: estacionesVolcan.features,
        cargarMunicipios: cargarMunicipiosAntioquia,
        editando: false
    };

    try {
        renderizarFicha(contexto);
    } catch (error) {
        console.error(
            "Error mostrando la ficha técnica:",
            error
        );
    }

    document.getElementById("pdf-button").onclick = () => {
        descargarPDF(contexto);
    };

    await habilitarEditor(boletin, contexto);
}


// ============================================================
// EDITOR LOCAL (solo si se abrió con scripts/editor_boletin.py)
// ============================================================

async function habilitarEditor(boletin, contexto) {
    // El editor solo existe en el equipo local: no se consulta en el sitio publicado.
    if (!["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname)) {
        return;
    }

    try {
        const controlador = new AbortController();
        const espera = window.setTimeout(() => controlador.abort(), 1000);
        const respuesta = await fetch(
            "./api/ping",
            {
                cache: "no-store",
                signal: controlador.signal
            }
        );

        window.clearTimeout(espera);

        if (!respuesta.ok || !(await respuesta.json()).editor) {
            return;
        }

        const { iniciarEditor } = await import(
            "./editor.js?v=20261027-ficha-sama"
        );

        iniciarEditor({
            boletin,
            contexto,
            renderizar: () => renderizarFicha(contexto),
            botonEditar: document.getElementById("edit-button"),
            panel: document.getElementById("editor-panel")
        });
    } catch (error) {
        // Sitio publicado o servidor sin editor: la ficha queda de solo lectura.
    }
}


function ajustarAlturaCabecera() {
    const cabecera = document.querySelector(".institutional-header");

    if (cabecera) {
        document.documentElement.style.setProperty(
            "--alto-cabecera",
            `${cabecera.offsetHeight}px`
        );
    }
}

window.addEventListener("resize", ajustarAlturaCabecera);

// El PDF usa un formato de página fijo, independiente del ancho de la pantalla.
window.addEventListener("beforeprint", () => {
    document.getElementById("ficha-boletin")?.classList.add("formato-pdf");
});

window.addEventListener("afterprint", () => {
    document.getElementById("ficha-boletin")?.classList.remove("formato-pdf");
});


// ============================================================
// MONITOREO INSAR DEL VOLCAN
// ============================================================

async function mostrarInsar(
    volcan,
    estacionesVolcan,
    fechaUrl
) {
    // --------------------------------------------------------
    // Metadatos
    // --------------------------------------------------------

    const metadata = await cargarMetadata(
        volcan.metadata
    );

    colocarTexto(
        "technical-sensor",
        metadata.sensor || "--"
    );

    colocarTexto(
        "technical-method",
        metadata.metodo || "--"
    );

    colocarTexto(
        "technical-processing",
        metadata.procesamiento || "--"
    );

    colocarTexto(
        "technical-geometry",
        metadata.geometria || "--"
    );

    colocarTexto(
        "technical-note",
        metadata.nota ||
        "La información presentada tiene carácter informativo y corresponde a observaciones satelitales de cambios en la superficie."
    );

    // --------------------------------------------------------
    // Área y flujos: son opcionales para que un archivo faltante
    // no impida cargar el raster.
    // --------------------------------------------------------

    let area = null;
    let flujos = null;

    try {
        area = await cargarArea(volcan);
    } catch (error) {
        console.warn(
            "No fue posible cargar el área de estudio:",
            error
        );
    }

    try {
        flujos = await cargarFlujos(volcan);
    } catch (error) {
        console.warn(
            "No fue posible cargar los flujos históricos:",
            error
        );
    }

    // --------------------------------------------------------
    // Fechas disponibles
    // --------------------------------------------------------

    const observaciones = obtenerFechas(volcan);

    if (observaciones.length === 0) {
        throw new Error(
            `El volcán '${volcan.nombre}' no tiene observaciones registradas.`
        );
    }

    dateSelect.innerHTML = "";

    for (const observacion of observaciones) {
        const opcion = document.createElement("option");

        opcion.value = observacion.fecha;
        opcion.textContent = formatearFecha(
            observacion.fecha
        );

        dateSelect.appendChild(opcion);
    }

    const fechaInicial =
        fechaUrl &&
        buscarObservacion(volcan, fechaUrl)
            ? fechaUrl
            : observaciones[0].fecha;

    dateSelect.value = fechaInicial;

    const observacionInicial = buscarObservacion(
        volcan,
        fechaInicial
    );

    await cargarObservacion(
        observacionInicial,
        area,
        flujos,
        estacionesVolcan
    );

    // --------------------------------------------------------
    // Serie temporal completa del volcán
    // --------------------------------------------------------

    await mostrarSerieTemporal(
        volcan
    );

    // --------------------------------------------------------
    // Eventos
    // --------------------------------------------------------

    dateSelect.onchange = async () => {
        const fecha = dateSelect.value;

        const observacion = buscarObservacion(
            volcan,
            fecha
        );

        if (!observacion) {
            return;
        }

        const url = new URL(
            window.location.href
        );

        url.searchParams.set(
            "volcan",
            volcan.id
        );

        url.searchParams.set(
            "fecha",
            fecha
        );

        window.history.replaceState(
            {},
            "",
            url
        );

        await cargarObservacion(
            observacion,
            area,
            flujos,
            estacionesVolcan
        );
    };

    return metadata;
}


// ============================================================
// OBSERVACION INDIVIDUAL
// ============================================================

async function cargarObservacion(
    observacion,
    area,
    flujos,
    estacionesGeoJSON
) {
    if (!observacion) {
        return;
    }

    const estadisticas = await cargarEstadisticas(
        observacion.estadisticas
    );

    colocarTexto(
        "stat-min",
        formatoCm(
            estadisticas.minimo_cm
        )
    );

    colocarTexto(
        "stat-max",
        formatoCm(
            estadisticas.maximo_cm
        )
    );

    colocarTexto(
        "stat-mean",
        formatoCm(
            estadisticas.promedio_cm
        )
    );

    const fechaDato =
        estadisticas.fecha ||
        observacion.fecha;

    colocarTexto(
        "stat-date",
        formatearFecha(
            String(fechaDato)
        )
    );

    colocarTexto(
        "observation-description",
        generarDescripcionObservacion(
            estadisticas,
            String(fechaDato)
        )
    );

    await crearMapaBoletin(
        observacion,
        area,
        flujos,
        estacionesGeoJSON
    );
}


// ============================================================
// SERIE TEMPORAL
// ============================================================

async function mostrarSerieTemporal(volcan) {
    const mensaje = document.getElementById(
        "time-series-message"
    );

    const contenedorGrafica = document.querySelector(
        ".time-series-chart"
    );

    if (!volcan.serie) {
        mostrarMensajeSerie(
            mensaje,
            contenedorGrafica,
            "Serie temporal no disponible para este volcán."
        );
        return;
    }

    try {
        const datos = await cargarSerieTemporalJSON(
            volcan.serie
        );

        const serie = Array.isArray(datos)
            ? datos
            : datos?.serie;

        if (
            !Array.isArray(serie) ||
            serie.length === 0
        ) {
            mostrarMensajeSerie(
                mensaje,
                contenedorGrafica,
                "La serie temporal no contiene datos disponibles."
            );
            return;
        }

        if (mensaje) {
            mensaje.hidden = true;
            mensaje.textContent = "";
        }

        if (contenedorGrafica) {
            contenedorGrafica.hidden = false;
        }

        const creada = crearGraficaEvolucion(
            "evolution-chart",
            serie
        );

        if (!creada) {
            mostrarMensajeSerie(
                mensaje,
                contenedorGrafica,
                "No fue posible representar la serie temporal. Revise los datos de fecha y promedio_cm."
            );
        }
    } catch (error) {
        console.error(
            "Error cargando la serie temporal:",
            error
        );

        mostrarMensajeSerie(
            mensaje,
            contenedorGrafica,
            "No fue posible cargar la serie temporal."
        );
    }
}

function mostrarMensajeSerie(
    mensaje,
    contenedorGrafica,
    texto
) {
    if (mensaje) {
        mensaje.textContent = texto;
        mensaje.hidden = false;
    }

    if (contenedorGrafica) {
        contenedorGrafica.hidden = true;
    }
}


// ============================================================
// DESCRIPCION AUTOMATICA
// ============================================================

function generarDescripcionObservacion(
    estadisticas,
    fecha
) {
    const minimo = Number(
        estadisticas.minimo_cm
    );

    const maximo = Number(
        estadisticas.maximo_cm
    );

    const promedio = Number(
        estadisticas.promedio_cm
    );

    if (
        !Number.isFinite(minimo) ||
        !Number.isFinite(maximo) ||
        !Number.isFinite(promedio)
    ) {
        return (
            "No se encuentran disponibles las estadísticas " +
            "de esta observación."
        );
    }

    return (
        `El mapa correspondiente al ${formatearFecha(fecha)} ` +
        `muestra cambios acumulados en la superficie entre ` +
        `${minimo.toFixed(2)} cm y ${maximo.toFixed(2)} cm, ` +
        `con un valor promedio de ${promedio.toFixed(2)} cm. ` +
        `Los valores representan desplazamientos medidos en la ` +
        `línea de vista del sensor (LOS) respecto a la fecha de referencia.`
    );
}


// ============================================================
// UTILIDADES
// ============================================================

function colocarTexto(id, valor) {
    const elemento = document.getElementById(id);

    if (!elemento) {
        return;
    }

    if (
        valor === null ||
        valor === undefined ||
        valor === ""
    ) {
        elemento.textContent = "--";
        return;
    }

    elemento.textContent = valor;
}

function formatoCm(valor) {
    const numero = Number(valor);

    if (!Number.isFinite(numero)) {
        return "--";
    }

    return `${numero.toFixed(2)} cm`;
}

function formatearFecha(fecha) {
    if (!fecha) {
        return "--";
    }

    const texto = String(fecha);

    if (texto.length !== 8) {
        return texto;
    }

    const anio = texto.slice(0, 4);
    const mes = texto.slice(4, 6);
    const dia = texto.slice(6, 8);

    return `${dia}/${mes}/${anio}`;
}


const menuToggle = document.querySelector(".menu-toggle");
const siteNav = document.querySelector(".site-nav");
menuToggle.addEventListener("click", () => {
    const abierto = menuToggle.getAttribute("aria-expanded") !== "true";
    menuToggle.setAttribute("aria-expanded", String(abierto));
    siteNav.classList.toggle("is-open", abierto);
});

iniciar();

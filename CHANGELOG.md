# Changelog

Todos los cambios notables de este proyecto serán documentados en este archivo.

## [2.27.0] - 2026-03-10
### Added
- Nueva API `/api/promedio-anual` que calcula el promedio en el servidor
- Simplificado JavaScript: ahora solo llama a la API

### Fixed
- Promedio del año ahora es FIJO basado en la fecha de HOY
- Incluye: diciembre año anterior + meses cerrados hasta HOY
- No cambia al navegar entre meses
- Var. YTD compara el mes VISIBLE vs el promedio fijo

## [2.26.0] - 2026-03-10
### Fixed
- Promedio del año ahora es FIJO basado en la fecha de HOY, no el mes visible
- No importa qué mes navegues, el promedio siempre es el mismo
- Incluye: diciembre año anterior + meses cerrados hasta HOY
- Var. YTD compara el mes VISIBLE vs el promedio fijo

## [2.25.9] - 2026-03-10
### Fixed
- Corregido API `/api/month` para incluir eventos del mes
- Ahora devuelve las reservas que tocan cada mes (para calcular promedio anual)
- El promedio del año ahora se calcula correctamente con los eventos de cada mes

## [2.25.7] - 2026-03-10
### Fixed
- Corregido cálculo de ingresos para meses anteriores
- Ahora usa cálculo proporcional igual que el mes actual
- Corregido nombre de campo: `extra_valor` en lugar de `precio_extra`
- Agregado logging para debug de rentabilidad

## [2.25.6] - 2026-03-10
### Fixed
- Corregido error "rentabilidadMes is not defined" en consola
- Actualizado log de debug con variables correctas (roi, margen, promedioROI)

## [2.25.5] - 2026-03-10
### Changed
- Renombrado "% del año" a "Var. YTD" (Variación Year-To-Date)
- Nueva fórmula: (Ingreso mes - Promedio año) / Promedio año × 100
- Muestra si el mes está por encima (+%) o debajo (-%) del promedio histórico
- Tooltip detallado con valores comparados

## [2.25.4] - 2026-03-10
### Fixed
- Corregido cálculo del promedio del año: ahora excluye el mes actual
- El promedio se calcula solo con los meses anteriores cerrados
- Tooltip muestra cantidad de meses usados para el cálculo

## [2.25.3] - 2026-03-10
### Changed
- Estrellas ahora se calculan con 50% en lugar de 75%
- 1⭐ por cada 50% que los ingresos superan a los gastos
- Ejemplos: 50% sobre = 1⭐, 100% sobre = 2⭐, 150% sobre = 3⭐

## [2.25.2] - 2026-03-10
### Changed
- Widget de Rentabilidad ahora muestra DOS métricas:
  - **ROI**: (Ingresos - Gastos) / Gastos × 100
  - **Margen**: (Ingresos - Gastos) / Ingresos × 100
- "Prom. Año" ahora muestra el promedio de ingresos acumulado del año
- Flecha de tendencia basada en comparación de ROI vs promedio histórico

## [2.25.1] - 2026-03-10
### Fixed
- Corregido cálculo de rentabilidad anual con mejor manejo de errores
- Las llamadas a la API ahora se hacen en paralelo para mayor velocidad
- Agregada validación de respuestas antes de procesar datos
- Log de debug para verificar cálculos de rentabilidad

## [2.25.0] - 2026-03-10
### Added
- Nuevo widget de Rentabilidad debajo del Total del Mes
- Muestra rentabilidad porcentual del mes actual
- Flecha de tendencia: ↑ si supera el promedio del año, ↓ si está por debajo
- Comparación "vs Promedio año" con diferencia porcentual
- Porcentaje que representa el mes respecto al balance anual total
- Carga automática de datos históricos del año para calcular promedios

## [2.24.3] - 2026-03-10
### Changed
- Nueva fórmula de estrellas: 1 estrella por cada 75% sobre los gastos
- Ejemplos: 75% sobre = 1⭐, 150% sobre = 2⭐, 225% sobre = 3⭐
- Tooltip actualizado para mostrar el porcentaje sobre gastos

## [2.24.2] - 2026-03-10
### Added
- Icono "+" en cada widget de gasto para indicar que es clickeable
- El icono se agranda al pasar el mouse por encima
- Mejor UX para abrir los modales de gastos

## [2.24.1] - 2026-03-10
### Fixed
- Vista móvil: widgets de Ingresos, Gastos y Total ahora se apilan verticalmente
- Estilos responsivos para los grupos de widgets en pantallas pequeñas
- Ajustado tamaño de fuentes e iconos para móvil

## [2.24.0] - 2026-03-10
### Added
- Nuevo widget "Gastos" en rojo que agrupa Agua, Internet, Gasolina y Aseo
- Layout 2x2 para gastos (2 filas x 2 columnas)
- Layout 1x2 para ingresos (1 fila x 2 columnas)
- Los widgets de gastos son clickeables para abrir sus modales
- Total de gastos sumado en el header del widget
- Colores pastel: azul claro para ingresos, rojo claro para gastos

## [2.23.0] - 2026-03-10
### Added
- Nuevo contenedor "Ingresos" en azul que agrupa Arriendo y Tinaja
- El contenedor muestra el total sumado de ambos ingresos
- Diseño compacto con widgets mini dentro del contenedor

## [2.22.7] - 2026-03-10
### Fixed
- Restaurado soporte para checkout + checkin en el mismo día (franja negra + azul)
- El día de checkout ya no recibe clase 'reserved' para evitar conflictos CSS
- Agregado !important al CSS de checkin.checkout-day para mantener prioridad

## [2.22.6] - 2026-03-10
### Fixed
- Corregido borde redondeado del checkout: ahora se ve la colita negra con borde redondeado al final
- El CSS de checkout-day ahora tiene prioridad sobre reserved (usando !important)
- Funciona correctamente para días 9 y 13 de marzo

## [2.22.5] - 2026-03-10
### Fixed
- Quitado globito duplicado en día de checkout (el nombre solo aparece en el día de inicio)
- Las franjas azul/negro siguen mostrándose correctamente cuando checkout + checkin coinciden

## [2.22.4] - 2026-03-10
### Fixed
- Corregido bug de franjas: cuando una reserva termina y otra empieza el mismo día ahora se ven AMBAS franjas
- Franja negra (checkout) a la izquierda + franja azul (checkin) a la derecha en el mismo día
- Usado ::before para checkout y ::after para checkin cuando coinciden
- Agregado soporte responsive para el mismo caso

## [2.22.3] - 2026-03-10
### Fixed
- Ahora se muestran AMBOS globitos cuando una reserva termina y otra empieza el mismo día
- El día de checkout muestra el globito de la reserva que termina (apilado con el que empieza)
- Soporta visualización de checkin + checkout simultáneo en el mismo día

## [2.22.2] - 2026-03-10
### Fixed
- Corregido bug visual: el día de checkout ya no muestra globitos de nombre/precio duplicados
- Ahora el checkout cuenta como día ocupado pero sin mostrar globitos (excepto reservas de 1 día)
- Arreglado solapamiento de "Franco ign +1" cuando una reserva termina y otra empieza el mismo día

## [2.22.1] - 2026-03-10
### Fixed
- Corregido cálculo de estrellas: ahora ratio 2.77x = 2 estrellas (antes daba 1)
- Fórmula: estrellas = floor(ingresos/gastos), no floor(ratio)-1

## [2.22.0] - 2026-03-10
### Added
- Widget de gastos de Aseo (🧹) color violeta
- Modal para registrar gastos de aseo (limpieza, limpieza profunda)
- Historial de gastos de aseo por mes
- Selector de proveedor tipo "aseo" en modal
- API /api/gastos/aseo (GET, POST)
- Colección gastos_aseo en MongoDB
- Proveedores Severina y Hortencia Oyanedel (tipo aseo)
- Gastos de aseo incluidos en cálculo de Total del Mes
- Icono 🧹 en calendario para días con gastos de aseo

## [2.20.5] - 2026-03-10
### Changed
- Estrellas sin límite máximo (antes máximo 5)

## [2.20.4] - 2026-03-10
### Added
- Estrellas ⭐ en widget Total del Mes por cada 100% que ingresos superan gastos
- 1 estrella = 2x gastos, 2 estrellas = 3x gastos, etc.

## [2.20.2] - 2026-03-10
### Fixed
- Globitos de precio y nombres ahora se apilan verticalmente cuando hay múltiples reservas el mismo día
- Corregido solapamiento visual cuando una reserva termina y otra empieza el mismo día

## [2.20.1] - 2026-03-10
### Added
- Iconos de gastos en las casillas del calendario
- 💧 Agua (izquierda), 📡 Internet (centro), ⛽ Gasolina (derecha)
- Tooltip muestra tipo de gasto y valor al pasar el mouse
- Solo visible para admin

## [2.20.0] - 2026-03-10
### Added
- Widget "Total del Mes" que suma ingresos (arriendo + tinaja) menos gastos (agua + internet + gasolina)
- Widget más grande y visible que los demás
- Colores dinámicos según ratio ingresos/gastos:
  - 🔵 Azul: ingresos >= 2x gastos (excelente)
  - 🟢 Verde: ingresos >= 1.5x gastos (bueno)
  - 🟡 Amarillo: ingresos >= gastos (equilibrado)
  - 🔴 Rojo: ingresos < gastos (déficit)

## [2.19.2] - 2026-03-10
### Changed
- El día de checkout ahora cuenta como día ocupado (no se puede reservar ese día)
- Cálculo de días incluye checkout: reserva 30/12 al 01/01 = 3 días (30, 31 dic y 01 ene)
- Proporciones corregidas: el globito en enero muestra 1/3 del precio

## [2.19.1] - 2026-03-10
### Fixed
- Corregido cálculo de globitos proporcionales: ahora siempre muestra valor proporcional cuando reserva cruza meses
- Antes mostraba precio completo en el primer día incluso si cruzaba meses

## [2.19.0] - 2026-03-10
### Added
- Widget de gastos de Gasolina (negro petróleo) con icono ⛽
- Modal para registrar gastos de gasolina (combustible, aceite, mantención)
- Historial de gastos de gasolina por mes en el modal
- Selector de proveedor tipo "gasolinera" en modal
- API /api/gastos/gasolina (GET, POST)
- Colección gastos_gasolina en MongoDB
- Proveedor Shell (Gasolina 93 octanos)
- 11 gastos de gasolina para viajes checkin-checkout

## [2.18.0] - 2026-03-10
### Changed
- Ingresos de reservas que cruzan meses ahora se prorratean según días ocupados en cada mes
- Globitos de precio/extra muestran valor proporcional cuando la reserva viene de mes anterior
- Globitos proporcionales tienen estilo distintivo (borde punteado, itálica)
- Tooltip en globitos muestra proporción de días (ej: "Proporcional: 3/7 días")

## [2.17.0] - 2026-03-10
### Added
- Widget de gastos de Internet (gris) debajo del de Agua
- Modal para registrar gastos de internet (razón, nombre, tipo, fecha pago, valor, whatsapp, estado)
- Historial de gastos de internet por mes en el modal
- Selector de proveedor tipo "internet" en modal
- API /api/gastos/internet (GET, POST)
- Colección gastos_internet en MongoDB
- Proveedor Starlink (Internet Satelital)

## [2.16.0] - 2026-03-10
### Added
- Colección de proveedores en MongoDB
- Selector de proveedor en modal de gastos de agua
- API para obtener y guardar proveedores
- Proveedor Wilson Fuenzalida (H2O terreno costa) con datos bancarios
- Gasto de agua $50.000 del 15/12/2025

## [2.15.0] - 2026-03-10
### Added
- Widget de gastos de Agua con botón + para agregar
- Modal para registrar gastos de agua (razón, nombre, tipo, fecha pago, valor, whatsapp, estado)
- Historial de gastos de agua por mes en el modal
- Colección gastos_agua en MongoDB

## [2.13.0] - 2026-03-10
### Changed
- Widgets de ingresos movidos al lado izquierdo del calendario (desktop)
- Vista mobile: widgets debajo del calendario en fila
- Corregido cálculo de ocupación (solo reservas, no bloqueos)

## [2.12.0] - 2026-03-10
### Added
- Widgets de ingresos mensuales (Arriendo y Tinaja) solo para admin
- Campos comuna y país en modal de edición

## [2.11.0] - 2026-03-10
### Added
- Globito azul debajo del verde para reservas de 1 día

## [2.10.0] - 2026-03-10
### Added
- Campo extra con concepto y valor en modal de edición
- Globito verde para precio, globito azul para extra en calendario (admin)
- Precio y extra mostrados separados en cards de ocupación
- Valentina con precio $150.431 + Tinaja $20.000

## [2.9.1] - 2026-03-10
### Added
- Globito de precio en calendario (solo admin visible)

## [2.8.25] - 2026-03-10
### Added
- Mostrar precio en cards con formato $XXX.XXX [CLP]

## [2.8.24] - 2026-03-10
### Added
- Campo precio (CLP) en modal de edición de reservas

## [2.8.23] - 2026-03-10
### Changed
- Globito muestra 10 letras (Primera mayúscula, resto minúscula)
- Huella de mascotas 🐾 más grande en cards
- Stats calculados dinámicamente por mes visible

## [2.8.20] - 2026-03-10
### Fixed
- Sello "Próxima Estadía" solo en la primera reserva futura (no todas)

## [2.8.19] - 2026-03-10
### Added
- Mostrar hora de check-in y check-out con 🕐 en tarjetas de reserva

## [2.8.18] - 2026-03-10
### Fixed
- Stats solo cuentan reservas (no bloqueos ni eliminados)
- Total y Próximas ahora muestran solo reservas reales

## [2.8.17] - 2026-03-10
### Fixed
- Bloqueos no deben mostrar "en curso" (verde) - solo reservas

## [2.8.16] - 2026-03-10
### Fixed
- Sello finalizada: forzar posición con !important en top/right/left

## [2.8.15] - 2026-03-10
### Changed
- Sello finalizada: forzar posición derecha con left:auto
- Nuevo sello "Próxima Estadía" con ⚠ para reservas upcoming

## [2.8.14] - 2026-03-10
### Changed
- Sello: posición arriba-derecha, sobresale de la tarjeta

## [2.8.13] - 2026-03-10
### Changed
- Sello: fondo transparente, borde negro, texto negro, más grande

## [2.8.12] - 2026-03-10
### Changed
- Sello: círculo verde con ✓ y banner rojo diagonal "FINALIZADA"

## [2.8.11] - 2026-03-10
### Fixed
- Sello ✓ aparece si: fecha pasó O admin finalizó anticipadamente

## [2.8.10] - 2026-03-10
### Fixed
- Quitar overflow:hidden de todos los estados de reserva
- Sello checkout más grande y visible (z-index: 100)

## [2.8.9] - 2026-03-10
### Fixed
- Sello checkout como elemento HTML (no ::before) para compatibilidad

## [2.8.8] - 2026-03-10
### Fixed
- Sello checkout visible (quitar overflow:hidden de is-past)

## [2.8.7] - 2026-03-10
### Fixed
- Sello checkout con line-height (fix display:flex en ::before)

## [2.8.6] - 2026-03-10
### Fixed
- Restaurar sello de checkout ✓ visible en reservas finalizadas

## [2.8.5] - 2026-03-10
### Added
- Globito negro en día check-in con inicial del huésped + conteo personas + mascotas

## [2.8.4] - 2026-03-10
### Fixed
- Guardar campos huéspedes, mascotas, notas y horas en base de datos

## [2.8.3] - 2026-03-10
### Fixed
- Mostrar siempre iconos 👤👶🐾 con cantidades en ticket de reserva

## [2.8.0] - 2026-03-10
### Added
- Campos de huéspedes: adultos, niños y mascotas en reservas
- Campo nombre del huésped
- Campos hora de llegada y hora de salida (separados de las fechas)
- Campo de notas visibles para todos en el calendario
- Iconos en Calendario de Ocupación: 👤 adultos, 👶 niños, 🐾 mascotas
- Notas con icono 📝 y estilo destacado amarillo
- Formulario modal actualizado con nuevos campos
- APIs actualizadas para guardar/obtener nuevos datos

## [2.4.49] - 2026-03-09
### Fixed
- Botón Admin con fondo rojo en móvil (!important)
- Agregar emoji 🚗 al icono de próxima estadía
- Colores directos sin variables CSS para móvil

## [2.4.48] - 2026-03-09
### Fixed
- Mostrar gradiente naranja en próxima estadía móvil
- Mostrar overlays (PRÓXIMA ESTADÍA, auto) en móvil
- Fondo amarillo/naranja para reservas próximas

## [2.4.47] - 2026-03-09
### Fixed
- Estilos inline en SVG de usuario para forzar tamaño 16px
- Solución definitiva al avatar gigante en móvil

## [2.4.46] - 2026-03-09
### Fixed
- Agregar query string de versión al CSS para evitar caché
- CSS ahora carga como style.css?v=2.4.46

## [2.4.45] - 2026-03-09
### Fixed
- Ocultar completamente icono SVG de usuario en móvil (display: none)
- Solución definitiva al avatar gigante

## [2.4.44] - 2026-03-09
### Fixed
- Icono de usuario (avatar) gigante en móvil - ahora tamaño fijo 16px
- Forzar min/max width/height en .user-icon para evitar crecimiento

## [2.4.43] - 2026-03-09
### Fixed
- Forzar colores y efectos en móvil con !important
- Media query 900px para tablets
- Bordes izquierdos con colores correctos (verde, naranja, gris)
- Backgrounds de gradientes visibles en móvil
- Badges con colores forzados

## [2.4.42] - 2026-03-09
### Fixed
- Lista de reservas móvil más parecida a PC
- Mantener efectos de gradientes y luz en móvil
- Iconos de estadía proporcionales (no sobredimensionados)
- Colores grises y naranjos visibles en móvil
- Layout de fechas horizontal como en PC

## [2.4.40] - 2026-03-09
### Changed
- Simplificación lógica de finalizar: solo agrega campo `checkout` sin cambiar estado
- Botón "Finalizar" renombrado a "Checkout"
- Badge verde con fecha de checkout en lugar de cambio de estado

### Fixed
- Fix franjas negras/azules: problema de CSS width con from-cache resuelto
- Mejorar estilos responsive para móviles Android
- Franjas del calendario más pequeñas y mejor extendidas en móvil
- Sello de checkout reducido en móvil
- Badges y botones más compactos para pantallas pequeñas

## [2.1.0] - 2026-03-09
### Changed
- Rediseño completo de la lista de reservas
- Check-in y Check-out con labels claros arriba de las fechas
- Flecha más grande entre fechas
- Diferenciación visual entre reservas y bloqueos
- Scroll automático a la reserva más cercana al día actual
- Motivo claro para bloqueos del sistema

## [2.0.1] - 2026-03-09
### Fixed
- Bump de versión

## [2.0.0] - 2026-03-09
### Added
- Sistema de autenticación con login/logout
- Variables de entorno AUTH_USERNAME y AUTH_PASSWORD
- Estadísticas (Total, Próximas, % Ocupación) solo visibles para admin
- Botón Admin/Salir en header
- Calendario público para todos los usuarios

## [1.9.3] - 2026-03-09
### Fixed
- Versión visible en móvil junto al título
- Reorganización del header con flexbox
- Badges de status siempre visibles

## [1.9.1] - 2026-03-09
### Fixed
- Campo source agregado a colección dias
- Días futuros marcados como cache_airbnb antes de sync

## [1.9.0] - 2026-03-09
### Added
- MongoDB como fuente principal de datos
- iCal sincroniza en background sin bloquear
- Eventos no presentes en iCal se marcan como source: cache_airbnb
- Badge "Cache" amarillo cuando MongoDB está conectado
- Puntito amarillo en días que vienen del caché
- Datos históricos (< hoy) no se modifican

## [1.8.0] - 2026-03-09
### Added
- Fallback a MongoDB cuando iCal falla
- Badge "Cache" en la UI cuando usa datos de respaldo
- Mejorar lógica de estado MongoDB (ping para verificar conexión)
- Conectar a MongoDB al inicializar el servicio

## [1.7.4] - 2026-03-09
### Fixed
- No marcar días libres como bloqueados
- Código anterior marcaba incorrectamente días después del checkout

## [1.7.1] - 2026-03-09
### Fixed
- Serialización de ObjectId a string para JSON
- Captura del resultado de bulk_write de eventos

## [1.7.0] - 2026-03-09
### Changed
- Refactorización: separar responsabilidades
- Servicios: airbnb_calendar.py y database.py
- Sincronización en background con threading

## [1.6.2] - 2026-03-09
### Fixed
- Llave única event_start + event_end en airbnb-dias

## [1.6.1] - 2026-03-09
### Performance
- Optimizar poblado de días con bulk operations

## [1.6.0] - 2026-03-09
### Added
- Colección 'dias' para calendario individual
- Cada día con llave única (año, mes, día)

## [1.5.2] - 2026-03-09
### Fixed
- Usar airbnb-db en lugar de tomi-db

## [1.5.1] - 2026-03-09
### Added
- Auditoría user_origin y user_agent en MongoDB

## [1.5.0] - 2026-03-09
### Added
- Caché MongoDB para reservaciones
- Colección airbnb-dias

## [1.4.1] - 2026-03-09
### Changed
- Eliminar variable ENABLE_MONGO_DB
- MongoDB se activa automáticamente si MONGODB_URI está configurado

## [1.4.0] - 2026-03-09
### Added
- Badges de estado para iCal y MongoDB
- Indicadores visuales de conexión en tiempo real

## [1.3.9] - 2026-03-08
### Fixed
- Archivos estáticos para Vercel

## [1.3.8] - 2026-03-08
### Fixed
- Compatibilidad uv/Vercel en pyproject.toml

## [1.3.7] - 2026-03-08
### Added
- Configuración para deploy en Vercel

## [1.3.3] - 2026-03-08
### Added
- UI móvil mejorada
- Franja continua para reservas

## [1.3.1] - 2026-03-08
### Fixed
- Entrada con franja azul, sin pelotita

## [1.3.0] - 2026-03-08
### Changed
- Rediseño completo de UI móvil

## [1.2.0] - 2026-03-08
### Added
- Calendario navegable con flechas
- Navegación entre meses

## [1.0.7] - 2026-03-08
### Added
- Links clickeables en días del calendario

## [1.0.6] - 2026-03-08
### Changed
- Estilo Airbnb para el calendario

## [1.0.5] - 2026-03-08
### Added
- Links a reservaciones de Airbnb

## [1.0.4] - 2026-03-08
### Added
- Versión dinámica desde pyproject.toml
- Nombre de propiedad desde configuración

## [1.0.3] - 2026-03-08
### Added
- Días del calendario con colores según estado

## [1.0.2] - 2026-03-08
### Changed
- Versión inicial publicada

# Changelog

Todos los cambios notables de este proyecto serán documentados en este archivo.

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

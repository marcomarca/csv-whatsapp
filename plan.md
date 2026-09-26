# Proyecto: WhatsApp Backup to CSV

## 1. Rol y mandato

Actúa como arquitecto de software, ingeniero Python y agente de automatización con control de mi ordenador.

Tu responsabilidad es diseñar, implementar, probar y entregar una aplicación funcional para exportar automáticamente mis conversaciones de WhatsApp desde un teléfono Android mediante USB.

No te limites a elaborar un plan. Debes ejecutar las tareas de desarrollo, instalar las dependencias necesarias, crear el proyecto, implementar el software y verificarlo.

Cuando una operación requiera intervención física, permisos del teléfono o una decisión de seguridad, detén únicamente esa operación y muéstrame instrucciones concretas.

No me pidas ejecutar comandos que puedas ejecutar tú.

No me pidas decidir detalles técnicos que puedas resolver mediante investigación, documentación y pruebas.

**Objetivo final:** una aplicación local que, una vez configurada, permita conectar mi teléfono Android, ejecutar una exportación y obtener todas las conversaciones disponibles en archivos CSV normalizados.

---

## 2. Alcance

### IN — Obligatorio

- Compatible con Android y WhatsApp normal.
- Detección del teléfono mediante ADB.
- Configuración asistida de depuración USB.
- Detección de backups locales.
- Obtención automatizada mediante ADB.
- Soporte para backups `crypt15`.
- Gestión segura de la clave de cifrado.
- Descifrado y validación de SQLite.
- Extracción de todos los chats disponibles.
- Conversaciones individuales y grupos.
- Mensajes enviados y recibidos.
- Exportación de texto, fechas y metadatos.
- Identificación de mensajes multimedia.
- CSV unificado y CSV por conversación.
- Exportaciones repetidas sin duplicados.
- Interfaz sencilla.
- Registro de ejecuciones, errores y resultados.
- Funcionamiento local sin servicios externos.

### SHOULD — Segunda fase

- Descarga de fotografías, audios, vídeos y documentos.
- Generación de informes HTML.
- Programación de exportaciones periódicas.
- Soporte para WhatsApp Business.
- Soporte para formatos antiguos `crypt14`.
- Importación de backups existentes desde el ordenador.

### OUT — No implementar

- Root del dispositivo.
- Desbloqueo del bootloader.
- Reinstalación de WhatsApp.
- Extracción de datos privados de otras aplicaciones.
- Automatización mediante WhatsApp Web como sistema principal.
- Envío de mensajes.
- Modificación de conversaciones.
- Modificación de bases de datos originales.
- Subida de mensajes a servicios externos.
- Almacenamiento de secretos en el repositorio.

No prometas recuperar mensajes eliminados o conversaciones que no estén presentes en los datos obtenidos.

---

## 3. Arquitectura

Implementar una aplicación monolítica local en Python.

Flujo principal:

Android → ADB → backup cifrado → descifrado → SQLite → parser → normalización → base consolidada → CSV.

### Componentes

**DeviceManager**

- Detectar dispositivos conectados.
- Verificar autorización ADB.
- Identificar modelo y versión Android.
- Detectar WhatsApp normal o Business.
- Resolver rutas disponibles.
- Gestionar desconexiones.

**BackupManager**

- Localizar archivos `msgstore`.
- Obtener fecha, tamaño y formato.
- Seleccionar el backup apropiado.
- Copiarlo a una carpeta temporal.
- Comprobar que la transferencia terminó correctamente.
- Calcular SHA-256.
- Conservar el original cifrado.

**SecretManager**

- Solicitar la clave.
- Validar formato.
- Guardarla únicamente en el almacén seguro del sistema operativo, con consentimiento del usuario.
- Recuperarla en ejecuciones posteriores.
- Detectar una clave incorrecta.
- Permitir actualizarla.
- Evitar mostrarla en logs.

**DecryptManager**

- Identificar formato criptográfico.
- Descifrar con wa-crypt-tools.
- Verificar autenticidad criptográfica.
- Validar cabecera SQLite.
- Ejecutar comprobación de integridad.
- Rechazar resultados incompletos o inválidos.

**MessageParser**

- Utilizar WhaPa como motor principal.
- Detectar compatibilidad con el esquema de WhatsApp.
- Procesar conversaciones y mensajes.
- Conservar identificadores originales.
- Registrar tipos de mensajes desconocidos sin descartarlos silenciosamente.

**ExportManager**

- Crear CSV unificado.
- Crear CSV individuales.
- Consolidar exportaciones.
- Evitar duplicados.
- Mantener un historial de ejecuciones.
- Gestionar codificación UTF-8 y caracteres especiales.

**AppUI**

- Mostrar instrucciones al usuario.
- Gestionar configuración inicial.
- Mostrar estado de conexión.
- Ejecutar exportaciones.
- Mostrar errores y resultados.
- Permitir abrir la carpeta de exportación.

---

## 4. Stack

Python 3.11 o superior.

Dependencias:

- ADB: Android Platform Tools oficiales.
- wa-crypt-tools: descifrado.
- WhaPa 2.00 o versión posterior compatible: parser.
- sqlite3: base de datos local.
- csv: exportación.
- pathlib: gestión de rutas.
- subprocess: ejecución controlada de herramientas.
- hashlib: identificación de backups.
- keyring: custodia de secretos.
- pytest: pruebas.
- Tkinter: interfaz gráfica.

Usar entornos virtuales.

Registrar versiones exactas de dependencias.

No instalar frameworks adicionales sin una necesidad demostrable.

---

# 5. Fase P0 — Preparación del ordenador

Esta fase debe ejecutarla la IA autónomamente.

### P0.1 Detectar entorno

Identificar:

- Sistema operativo.
- Arquitectura.
- Versión de Python.
- Disponibilidad de Git.
- Disponibilidad de ADB.
- Permisos del usuario.
- Espacio disponible en disco.

Adaptar instalación y comandos a Windows, macOS o Linux.

### P0.2 Crear proyecto

Crear el directorio:

whatsapp-backup-csv/

Inicializar Git.

Crear entorno virtual.

Crear `.gitignore`.

Excluir obligatoriamente:

- Credenciales.
- Archivos `.key`.
- Bases de datos.
- Archivos `.crypt`.
- CSV exportados.
- Capturas con claves.
- Directorios temporales.
- Archivos multimedia privados.

### P0.3 Instalar ADB

Descargar Google Android SDK Platform Tools desde:

https://developer.android.com/tools/releases/platform-tools

Verificar procedencia y arquitectura.

Instalar o configurar la herramienta.

Comprobar:

`adb version`

Si no funciona, corregir PATH o configurar una ruta absoluta.

### P0.4 Instalar herramientas Python

Instalar:

- wa-crypt-tools.
- WhaPa.
- keyring.
- pytest.
- Dependencias declaradas por los proyectos anteriores.

Repositorios:

https://github.com/ElDavoo/wa-crypt-tools

https://github.com/B16f00t/whapa

Ejecutar los comandos de ayuda de cada herramienta y comprobar las interfaces reales de la versión instalada.

No asumir que las opciones CLI son idénticas entre versiones.

Crear un archivo de dependencias reproducible.

**Aceptación P0:** el ordenador puede ejecutar ADB, Python y las herramientas de descifrado y extracción.

---

# 6. Fase P1 — Configuración humana del teléfono

Implementar un asistente interactivo que me guíe por esta fase.

Presentar una instrucción por pantalla y esperar mi confirmación.

## Paso humano 1: conectar el teléfono

Mostrar:

"Conecta tu teléfono Android al ordenador utilizando un cable USB que permita transferir datos. Desbloquea el teléfono."

La IA debe ejecutar:

`adb devices`

Si el dispositivo aparece correctamente, continuar.

Si no aparece, mostrar las siguientes instrucciones.

## Paso humano 2: habilitar opciones de desarrollador

Mostrar:

1. Abre Ajustes en Android.
2. Entra en Información del teléfono.
3. Busca Número de compilación.
4. Púlsalo siete veces.
5. Introduce el PIN si Android lo solicita.
6. Regresa a Ajustes.
7. Abre Opciones de desarrollador.

Si el fabricante utiliza otra ubicación, buscar las instrucciones específicas para el modelo detectado.

No dar por hecho que todos los Android tienen menús idénticos.

## Paso humano 3: activar depuración USB

Mostrar:

1. Busca Depuración USB.
2. Actívala.
3. Confirma la advertencia.
4. Mantén el teléfono desbloqueado.

La IA debe ejecutar nuevamente:

`adb devices`

## Paso humano 4: autorizar ordenador

Si ADB devuelve `unauthorized`, mostrar:

"Comprueba la pantalla de tu teléfono. Android debería mostrar una solicitud para permitir la depuración USB desde este ordenador. Acepta únicamente si reconoces este ordenador."

Volver a comprobar automáticamente.

Si devuelve `device`, marcar conexión correcta.

Si hay varios dispositivos, pedir seleccionar uno.

Nunca ejecutar operaciones sobre un dispositivo ambiguo.

## Paso humano 5: comprobar WhatsApp

Detectar los paquetes:

`com.whatsapp`

`com.whatsapp.w4b`

Comprobar si están instalados.

Solicitar seleccionar la instalación correspondiente únicamente si ambas están presentes.

No leer ni modificar datos privados de aplicaciones mediante intentos de evasión de permisos.

**Aceptación P1:** dispositivo autorizado, identificado y accesible mediante ADB.

---

# 7. Fase P2 — Configuración del backup y obtención de la clave

Esta fase requiere intervención humana.

## Paso humano 6: abrir configuración de WhatsApp

Mostrar:

1. Abre WhatsApp.
2. Entra en Ajustes.
3. Entra en Chats.
4. Abre Copia de seguridad.
5. Abre Copia de seguridad cifrada de extremo a extremo.

Los nombres exactos pueden variar según versión o idioma.

## Paso humano 7: configurar cifrado

Preferencia técnica: clave de cifrado de 64 dígitos/caracteres hexadecimales.

Si la aplicación ofrece contraseña, passkey o clave de 64 dígitos, seleccionar esta última cuando esté disponible.

Si ya existe una configuración de cifrado, no modificarla automáticamente.

Primero informar del estado y de las opciones disponibles.

No desactivar ni sustituir una clave existente sin autorización expresa.

Si es necesario cambiar el método de protección, explicar las consecuencias antes de continuar.

## Paso humano 8: conservar la clave

Solicitar que el usuario guarde la clave generada por WhatsApp en un gestor de contraseñas o almacenamiento personal seguro.

La aplicación debe proporcionar un campo de entrada protegido para introducirla.

No pedir al usuario que envíe la clave a servicios de IA, correos electrónicos ni plataformas externas.

No incluirla en conversaciones, capturas de depuración o logs.

Validar que la representación hexadecimal tenga 64 caracteres válidos.

No considerar la contraseña de Google como equivalente a esta clave.

## Paso humano 9: generar copia

Mostrar:

1. Conecta el teléfono a una fuente de alimentación si es necesario.
2. Comprueba que existe espacio libre suficiente.
3. En WhatsApp, abre Copia de seguridad.
4. Pulsa Guardar o Crear copia.
5. Espera a que WhatsApp termine.
6. Regresa a la aplicación del ordenador.

No automatizar clics sensibles dentro de WhatsApp durante el MVP.

La IA debe comprobar posteriormente si existe un archivo de backup compatible y registrar su fecha.

Si el backup no aparece o no está actualizado, no afirmar que se ha generado correctamente.

## Paso humano 10: autorizar custodia de la clave

Mostrar dos opciones:

A. Guardar la clave en el almacén seguro del ordenador y permitir exportaciones automáticas posteriores.

B. Solicitar la clave manualmente en cada ejecución.

Adoptar A únicamente con consentimiento.

Si el sistema operativo no proporciona un almacén seguro adecuado, no guardar secretos en texto plano como alternativa silenciosa.

**Aceptación P2:** existe un backup compatible y la aplicación dispone de una clave introducida por el usuario.

---

# 8. Fase P3 — Descubrimiento y extracción del backup

Implementar detección automática de rutas.

Rutas candidatas para WhatsApp normal:

`/sdcard/Android/media/com.whatsapp/WhatsApp/Databases/`

`/sdcard/WhatsApp/Databases/`

Para WhatsApp Business:

`/sdcard/Android/media/com.whatsapp.w4b/WhatsApp Business/Databases/`

Comprobar existencia antes de intentar copiar.

Detectar archivos compatibles:

- msgstore.db.crypt15
- msgstore.db.crypt14
- Backups históricos con extensión compatible.

No utilizar una ruta fija sin comprobarla.

### Selección de archivo

Priorizar el backup actual compatible.

Registrar:

- Ruta original.
- Fecha de modificación.
- Tamaño.
- Formato.
- Identificador del dispositivo.
- SHA-256.

No seleccionar automáticamente un backup histórico más reciente por fecha de transferencia al ordenador.

### Transferencia

Utilizar ADB pull.

Ejemplo de operación:

`adb pull /sdcard/Android/media/com.whatsapp/WhatsApp/Databases/msgstore.db.crypt15`

La implementación real debe utilizar subprocess con argumentos separados, sin construir comandos de shell con datos no confiables.

Copiar primero a un archivo temporal.

Comprobar resultado y tamaño.

Calcular hash.

Mover a su ubicación definitiva mediante operación atómica cuando sea posible.

No sobrescribir el original.

Si la transferencia falla, conservar información del error y permitir reintentar.

### Carpetas

Crear:

data/backups/

data/working/

data/exports/

data/logs/

Conservar los backups cifrados usando nombres únicos.

**Aceptación P3:** el backup existe físicamente en el ordenador, puede leerse y tiene metadatos registrados.

---

# 9. Fase P4 — Descifrado

Usar wa-crypt-tools como motor principal.

No implementar criptografía propia.

### Clave

Recuperar la clave desde el almacén seguro.

No pasar la clave directamente como argumento visible de línea de comandos.

Preferir integración mediante API Python.

Si se requiere un archivo de clave temporal, generarlo mediante las funciones de la librería, con permisos restrictivos y fuera del proyecto.

No crear una clave aleatoria nueva: utilizar exclusivamente la clave correspondiente al backup.

### Comando de referencia

La herramienta documenta:

`wadecrypt encrypted_backup.key msgstore.db.crypt15 msgstore.db`

Implementar su equivalente integrado en el proyecto.

### Validación

Después de descifrar:

1. Comprobar autenticidad criptográfica.
2. Comprobar cabecera SQLite.
3. Abrir la base en modo lectura.
4. Ejecutar PRAGMA integrity_check.
5. Confirmar estructura mínima.
6. Registrar resultado.

No utilizar opciones de descifrado forzado que ignoren fallos de autenticidad para producir el CSV definitivo.

Si falla, devolver un error específico:

- Clave incorrecta.
- Backup incompleto.
- Archivo corrupto.
- Formato no soportado.
- Error de descifrado.
- Base SQLite inválida.

No continuar automáticamente ante un fallo.

**Aceptación P4:** existe una copia SQLite validada y legible.

---

# 10. Fase P5 — Extracción de conversaciones

Usar WhaPa como parser principal.

Versión de referencia: 2.00 o posterior.

Comando documentado de referencia:

`python libs/whapa.py msgstore.db -m -a -x -o ./salida`

Interpretación:

- `-m`: mensajes.
- `-a`: todas las conversaciones.
- `-x`: exportación CSV.
- `-o`: directorio de salida.

Antes de integrar, comprobar que la versión instalada admite estas opciones.

### Requisitos de extracción

Procesar todas las conversaciones disponibles.

No limitar resultados a los primeros N mensajes.

Conservar mensajes individuales, grupos y mensajes del sistema.

Conservar tipos de mensaje desconocidos mediante su código original.

No eliminar registros por tener texto vacío.

Un mensaje multimedia puede no contener texto y seguir siendo relevante.

Registrar advertencias si el parser encuentra estructuras desconocidas.

### Contactos

No depender obligatoriamente de `wa.db`, dado que puede no estar disponible sin acceso privilegiado.

Si está disponible mediante un backup propio accesible, utilizarlo.

Si no está disponible, conservar identificadores originales.

No inventar nombres de contactos.

### Validación

Comparar la salida del parser con la estructura de la base original.

Comprobar una muestra representativa de conversaciones.

Registrar mensajes omitidos y errores de interpretación.

**Aceptación P5:** la aplicación genera una representación estructurada de todas las conversaciones que el parser puede interpretar.

---

# 11. Fase P6 — Modelo de datos

Utilizar SQLite como almacenamiento interno de consolidación.

## Entidad: Backup

Campos:

- backup_id
- device_id
- source_path
- filename
- format
- file_size
- sha256
- source_modified_at
- imported_at
- decryption_status
- parser_version
- message_count

## Entidad: Conversation

Campos:

- conversation_id
- conversation_name
- conversation_type
- original_jid
- last_message_at

## Entidad: Message

Campos:

- message_uid
- conversation_id
- sender_id
- sender_name
- direction
- timestamp_utc
- timestamp_local
- message_type
- text
- media_path
- quoted_message_id
- forwarded
- edited
- starred
- raw_type_code
- source_backup_id

Conservar también los campos originales necesarios para identificar mensajes y resolver discrepancias.

No tratar nombres de contacto como identificadores estables.

## Entidad: ExportRun

Campos:

- run_id
- started_at
- finished_at
- status
- backup_id
- total_conversations
- total_messages
- inserted_messages
- updated_messages
- warnings
- error_code

### Deduplicación

Prioridad:

1. Identificador original de WhatsApp.
2. Identificador de conversación.
3. Identificador del emisor.

Si no existe identificador estable, aplicar una estrategia alternativa documentada que minimice colisiones.

No deduplicar únicamente mediante texto y fecha.

Dos mensajes idénticos enviados consecutivamente son registros distintos.

Los mensajes editados deben actualizar su representación o conservar su versión según el modelo adoptado.

No eliminar mensajes históricos simplemente porque desaparezcan de una copia posterior.

---

# 12. Fase P7 — Exportación CSV

Generar obligatoriamente:

**all_messages.csv**

Un mensaje por fila.

**conversations.csv**

Una conversación por fila.

**Carpeta conversations/**

Un CSV individual por conversación.

**manifest.json**

Metadatos de exportación:

- Fecha.
- Identificador de ejecución.
- Hash del backup.
- Versiones de herramientas.
- Cantidad de conversaciones.
- Cantidad de mensajes.
- Advertencias.
- Estado de validación.

Utilizar UTF-8 con BOM para facilitar apertura en Excel.

Utilizar el módulo csv con escape y entrecomillado correctos.

No eliminar saltos de línea dentro de mensajes.

Preservar emojis y caracteres Unicode.

No convertir valores nulos en textos ambiguos.

Prevenir interpretación de fórmulas CSV cuando el contenido empieza por caracteres especiales utilizados por aplicaciones de hojas de cálculo. Documentar la normalización aplicada y ofrecer una exportación de datos originales si es necesario.

### CSV individual

Usar nombres seguros.

No utilizar directamente nombres de conversaciones como rutas del sistema.

Preferir identificador estable más nombre sanitizado.

Evitar colisiones de nombres.

### CSV consolidado

Cada ejecución debe incorporar mensajes nuevos.

Si el backup no cambió, evitar reprocesamiento innecesario.

Actualizar el CSV consolidado mediante escritura temporal y sustitución atómica.

No borrar un CSV correcto si la nueva exportación falla.

**Aceptación P7:** los archivos pueden abrirse y procesarse con Python, pandas, SQLite y Excel.

---

# 13. Fase P8 — Interfaz de usuario

Implementar una interfaz de escritorio sencilla con Tkinter.

No desarrollar una aplicación web para esta primera versión.

Pantalla principal:

Estado del teléfono.

Estado de ADB.

Estado de configuración de la clave.

Fecha del último backup detectado.

Fecha de la última exportación.

Cantidad de conversaciones exportadas.

Cantidad de mensajes exportados.

Botón principal:

**EXPORTAR WHATSAPP**

Acciones secundarias:

- Configurar dispositivo.
- Actualizar clave.
- Seleccionar carpeta de salida.
- Abrir carpeta de resultados.
- Ver historial.
- Ver errores.
- Activar o desactivar exportación multimedia.

Mostrar progreso por etapas:

Conexión → Backup → Copia → Descifrado → Análisis → Consolidación → CSV → Finalizado.

Si falta intervención humana, mostrar una instrucción específica.

Ejemplo:

"El teléfono está conectado, pero ADB todavía no está autorizado. Desbloquéalo y acepta la solicitud de depuración USB."

No mostrar mensajes genéricos como "Error desconocido" cuando exista una causa identificable.

---

# 14. Fase P9 — Ejecuciones posteriores

Después de completar el onboarding, el comportamiento debe ser:

1. Abrir aplicación.
2. Detectar teléfono.
3. Comprobar backup.
4. Comparar hash con el último procesado.
5. Si es nuevo, copiarlo.
6. Recuperar clave autorizada.
7. Descifrar.
8. Validar.
9. Extraer conversaciones.
10. Consolidar mensajes.
11. Generar CSV.
12. Mostrar resultado.

Si el backup no se ha actualizado:

- Mostrar su fecha real.
- Ofrecer exportarlo de todos modos.
- Explicar que los mensajes posteriores al backup pueden faltar.

No afirmar que un archivo antiguo contiene mensajes actuales.

### Programación

Implementar programación periódica como funcionalidad secundaria.

Usar mecanismos nativos del sistema operativo cuando corresponda.

La ejecución programada debe comprobar:

- Dispositivo presente.
- ADB autorizado.
- Backup existente.
- Backup nuevo.
- Clave disponible.

Si alguna condición falla, registrar un estado pendiente.

No intentar desbloquear automáticamente el teléfono ni evadir sus mecanismos de seguridad.

No prometer exportación desatendida de mensajes que todavía no hayan sido incorporados a un backup por WhatsApp.

---

# 15. Fase P10 — Multimedia

Implementar después de estabilizar la exportación de texto.

Ruta habitual:

`/sdcard/Android/media/com.whatsapp/WhatsApp/Media/`

Copiar conservando estructura.

Incluir:

- Imágenes.
- Audios.
- Notas de voz.
- Vídeos.
- Documentos.
- Stickers.

Utilizar referencias relativas dentro del CSV.

No insertar binarios dentro de las celdas.

Añadir columna de estado:

available / missing / not_exported.

Los archivos que ya no existan en el teléfono deben quedar registrados como ausentes.

No presentar un mensaje multimedia como inexistente solamente porque no se encontró su archivo.

Evitar descargar nuevamente archivos idénticos mediante identificación por hash o metadatos verificables.

---

# 16. Seguridad

Este sistema procesa conversaciones privadas.

Reglas obligatorias:

1. Todo el procesamiento debe ser local.
2. No transmitir datos a proveedores de IA ni servicios externos.
3. No registrar claves en logs.
4. No registrar cuerpos de mensajes en logs técnicos por defecto.
5. No incluir bases de datos reales en pruebas o fixtures.
6. No subir datos a Git.
7. No modificar archivos originales del teléfono.
8. No utilizar root.
9. No instalar APKs innecesarios.
10. No almacenar credenciales de Google o WhatsApp.
11. No eliminar backups originales automáticamente.
12. No activar sincronización en la nube sin autorización.

Al finalizar la configuración, recomendar desactivar la depuración USB si no va a utilizarse habitualmente.

Advertir al usuario que los CSV exportados contienen información en claro y deben almacenarse en una ubicación protegida.

---

# 17. Estructura del proyecto

Crear una organización equivalente a:

whatsapp-backup-csv/
- src/
  - app.py
  - cli.py
  - device_manager.py
  - backup_manager.py
  - secret_manager.py
  - decrypt_manager.py
  - message_parser.py
  - database.py
  - export_manager.py
  - models.py
  - config.py
- tests/
  - test_device.py
  - test_backup.py
  - test_decrypt.py
  - test_parser.py
  - test_export.py
  - test_incremental.py
- vendor/
  - whapa/
- scripts/
- docs/
  - setup.md
  - troubleshooting.md
  - security.md
- data/
  - backups/
  - working/
  - exports/
  - logs/
- pyproject.toml
- requirements.lock
- README.md
- .gitignore

La organización exacta es reversible. Adáptala si hay una estructura más sencilla.

No convertir cada operación trivial en una clase.

---

# 18. Pruebas

Crear pruebas automatizadas con datos sintéticos.

### Prueba 1 — ADB

Detectar dispositivo autorizado, no autorizado y desconectado.

### Prueba 2 — Transferencia

Interrumpir una transferencia y comprobar que no se considera válida.

### Prueba 3 — Clave incorrecta

Debe impedir la exportación.

### Prueba 4 — Backup corrupto

Debe rechazarse.

### Prueba 5 — Unicode

Probar emojis, acentos, saltos de línea y caracteres especiales.

### Prueba 6 — Grupos

Comprobar que varios remitentes aparecen correctamente.

### Prueba 7 — Deduplicación

Importar dos veces el mismo backup y comprobar que no se duplican mensajes.

### Prueba 8 — Actualización incremental

Importar una copia nueva con mensajes adicionales.

### Prueba 9 — Multimedia

Comprobar referencias y ausencia de archivos.

### Prueba 10 — CSV

Abrir el CSV con un parser estándar y comprobar integridad de columnas.

### Prueba 11 — Recuperación

Simular un fallo a mitad de exportación y comprobar que la exportación anterior permanece intacta.

### Prueba 12 — Integración real

Ejecutar una exportación con mi teléfono.

Comparar al menos tres conversaciones reales, seleccionadas por mí, con los mensajes presentes en WhatsApp y en el backup utilizado.

No incluir esos mensajes en el repositorio ni en los logs de pruebas.

---

# 19. Manejo de errores

Implementar errores estructurados:

DEVICE_NOT_FOUND

DEVICE_UNAUTHORIZED

MULTIPLE_DEVICES

BACKUP_NOT_FOUND

BACKUP_OUTDATED

BACKUP_COPY_FAILED

INVALID_KEY

DECRYPTION_FAILED

INVALID_SQLITE

UNSUPPORTED_SCHEMA

PARSER_FAILED

EXPORT_FAILED

INSUFFICIENT_DISK_SPACE

Cada error debe contener:

- Código.
- Descripción comprensible.
- Operación fallida.
- Acción recomendada.
- Posibilidad de reintento.

Las ejecuciones fallidas no deben corromper el estado anterior.

---

# 20. Plan de ejecución obligatorio

Trabaja siguiendo este orden:

P0: entorno y herramientas.

P1: detección del teléfono.

P2: configuración de backup y clave.

P3: transferencia automatizada.

P4: descifrado verificado.

P5: extracción de conversaciones.

P6: normalización y almacenamiento.

P7: generación de CSV.

P8: interfaz gráfica.

P9: exportación incremental.

P10: multimedia y automatización programada.

No implementar la interfaz completa antes de comprobar el flujo técnico con un backup real.

Cada fase debe producir una funcionalidad verificable.

Si una dependencia falla, diagnosticarla antes de introducir otra librería.

---

# 21. Entregables

Al terminar debes entregarme:

1. Repositorio funcional.
2. Aplicación ejecutable desde el ordenador.
3. Script de instalación.
4. Script de exportación.
5. Interfaz gráfica.
6. Suite de pruebas.
7. Manual de configuración inicial.
8. Manual de solución de problemas.
9. Documentación de seguridad.
10. Ejemplo de estructura CSV con datos sintéticos.

Proporcionar comandos simples para iniciar la aplicación.

Ejemplo esperado:

`python -m src.app`

Y para ejecución mediante terminal:

`python -m src.cli export`

Adaptar los comandos a la estructura finalmente implementada.

---

# 22. Criterios finales de aceptación

El proyecto se considera terminado cuando:

- El ordenador detecta mi Android.
- El asistente me guía por la autorización USB.
- Obtiene un backup real.
- Lo descifra correctamente.
- Valida la base de datos.
- Extrae todos los chats compatibles disponibles.
- Genera CSV individuales.
- Genera CSV consolidado.
- Evita duplicados.
- Permite repetir la exportación.
- Informa claramente sobre backups antiguos.
- Gestiona errores sin destruir resultados anteriores.
- No requiere root.
- No requiere WhatsApp Web.
- No transmite mis conversaciones a terceros.

El objetivo de UX es que las ejecuciones posteriores necesiten únicamente conectar el teléfono y pulsar Exportar, siempre que exista un backup válido y actualizado.

## 23. Instrucción final al agente

Empieza inmediatamente por inspeccionar el ordenador.

Instala y configura lo que sea necesario.

Crea el proyecto.

Implementa primero la prueba de conexión ADB.

Cuando necesites una acción física mía, muestra:

- Qué tengo que hacer.
- Dónde tengo que hacerlo.
- Qué debería aparecer en pantalla.
- Cómo confirmo que he terminado.

Después de mi confirmación, continúa automáticamente.

No sustituyas trabajo ejecutable por instrucciones dirigidas a mí.

No declares que el proyecto está terminado hasta haber ejecutado una exportación real y haber comprobado los criterios de aceptación.

Si la versión instalada de WhatsApp utiliza un formato incompatible, identifica exactamente el bloqueo y conserva el resto del sistema funcionando.
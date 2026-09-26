# WhatsApp Backup to CSV

Aplicación local en Python para transferir automáticamente copias de seguridad de WhatsApp desde un teléfono Android mediante USB (ADB), descifrarlas de forma verificada y exportar todas las conversaciones a archivos CSV normalizados.

---

## Características Principales

- **Conexión Automatizada por USB (ADB)**: Detección de dispositivos Android, comprobación de estado de autorización y transferencia segura de archivos.
- **Soporte Criptográfico Completo**: Descifrado de copias de seguridad `crypt15`, `crypt14` y `crypt12` mediante clave de cifrado de 64 dígitos hexadecimales.
- **Custodia Segura de Claves**: Almacenamiento protegido de la clave de descifrado en el gestor de credenciales del sistema operativo (`keyring` / Windows Credential Manager).
- **Validación de Integridad SQLite**: Comprobación estricta de cabeceras binarias y ejecución de `PRAGMA integrity_check` antes de procesar cualquier base de datos.
- **Extracción Completa con WhaPa**: Conservación de chats individuales, grupos con múltiples remitentes, mensajes de sistema, llamadas, respuestas citadas, reacciones y referencias multimedia.
- **Consolidación Incremental y Deduplicación**: Almacén SQLite local que incorpora nuevos mensajes sin duplicar registros existentes ni borrar historial previo.
- **Exportación CSV Optimizada para Excel**: Codificación `UTF-8 con BOM (utf-8-sig)`, escape de inyección de fórmulas de hojas de cálculo y reemplazo atómico de archivos.
- **Doble Interfaz**: Interfaz gráfica de escritorio con Tkinter (`whatsapp-gui`) y CLI completa para terminal y automatizaciones (`whatsapp-csv`).

---

## Estructura del Proyecto

```txt
whatsapp-backup-csv/
├── src/
│   ├── app.py                 # Interfaz gráfica de escritorio (Tkinter)
│   ├── cli.py                 # Interfaz de línea de comandos
│   ├── config.py              # Rutas y configuración de entorno
│   ├── database.py            # Base de datos local de consolidación (Vault)
│   ├── decrypt_manager.py     # Descifrado criptográfico y validación SQLite
│   ├── device_manager.py      # Control de ADB, detección y transferencia USB
│   ├── errors.py              # Jerarquía de errores estructurados
│   ├── export_manager.py      # Generador de CSVs atómicos y manifest.json
│   ├── message_parser.py      # Motor de extracción de chats (WhaPa)
│   ├── models.py              # Modelos de datos del dominio
│   ├── pipeline.py            # Orquestador del flujo de exportación
│   └── secret_manager.py      # Gestión segura de claves en OS Keyring
├── tests/
│   ├── conftest.py            # Fixtures y generador de backups sintéticos
│   ├── unit/                  # Pruebas unitarias de cada componente
│   └── integration/           # Pruebas de integración del flujo completo
├── vendor/
│   └── whapa/                 # Parser forense WhaPa 2.00
├── data/
│   ├── backups/               # Copias de seguridad cifradas transferidas
│   ├── exports/               # Archivos CSV exportados y manifest.json
│   ├── logs/                  # Registros técnicos de ejecución
│   └── working/               # Base de consolidación y SQLite descifrada temporal
├── docs/                      # Documentación detallada (setup, seguridad, etc.)
├── scripts/                   # Scripts auxiliares para Windows
├── pyproject.toml             # Metadatos del proyecto y dependencias
└── uv.lock                    # Bloqueo reproducible de dependencias
```

---

## Instalación y Preparación

### 1. Requisitos
- Python 3.11 o superior.
- [uv](https://docs.astral.sh/uv/) (gestor rápido de paquetes Python).
- Android SDK Platform-Tools (`adb.exe`).

### 2. Instalación de dependencias
```bash
uv sync --all-extras
```

---

## Uso

### Interfaz Gráfica (Recomendado)
```bash
uv run python -m src.app
```
*O haz doble clic en `scripts/gui.bat`.*

### Línea de Comandos (CLI)

```bash
# 1. Comprobar estado de conexión y dispositivos
uv run python -m src.cli status

# 2. Configurar clave de cifrado en el almacén seguro del sistema
uv run python -m src.cli key set "TU_CLAVE_DE_64_CARACTERES_HEXADECIMALES"

# 3. Ejecutar exportación completa
uv run python -m src.cli export

# 4. Forzar re-exportación o incluir descarga de multimedia
uv run python -m src.cli export --force --include-media

# 5. Consultar historial de exportaciones
uv run python -m src.cli history
```

---

## Archivos Generados en `data/exports/`

- `all_messages.csv`: Tabla unificada con todos los mensajes de todas las conversaciones.
- `conversations.csv`: Resumen de chats con fechas de último mensaje y cantidad de registros.
- `conversations/[Nombre_Chat]_[ID].csv`: Archivos CSV individuales por cada conversación.
- `manifest.json`: Metadatos de la exportación, hash SHA-256 del backup y versiones de herramientas.

---

## Ejecución de Pruebas Automatizadas

```bash
uv run pytest
```

Para verificar formato y linter:
```bash
uv run ruff check src
```

---

## Seguridad y Privacidad

Todo el procesamiento ocurre de forma estrictamente local en tu ordenador. No se transmiten datos ni claves a ningún servidor externo. Consulta [docs/security.md](docs/security.md) para más detalles.

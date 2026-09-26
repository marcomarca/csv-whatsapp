# Comandos Frecuentes — WhatsApp Backup to CSV

Guía rápida de comandos para desarrollo, pruebas y ejecución de la aplicación.

---

## 1. Interfaz de Usuario y Ejecución

### Iniciar la Interfaz Gráfica (GUI)
```bash
uv run python -m src.app
```
*O haz doble clic en `scripts\gui.bat`.*

---

## 2. Línea de Comandos (CLI)

### Consultar estado del teléfono, ADB y clave
```bash
uv run python -m src.cli status
```

### Listar dispositivos conectados y backups disponibles en el teléfono
```bash
uv run python -m src.cli devices
```

### Guardar la clave de cifrado de 64 caracteres en el almacén seguro (OS Keyring)
```bash
uv run python -m src.cli key set "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES"
```

### Comprobar o eliminar la clave almacenada
```bash
# Ver estado de la clave (enmascarada)
uv run python -m src.cli key get

# Eliminar clave guardada
uv run python -m src.cli key clear
```

### Ejecutar exportación completa a CSV
```bash
# Exportación estándar
uv run python -m src.cli export

# Exportación pasando la clave directamente por parámetro
uv run python -m src.cli export -k "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES"

# Forzar exportación aunque el backup sea idéntico al anterior
uv run python -m src.cli export --force

# Incluir descarga de archivos multimedia
uv run python -m src.cli export --include-media

# Especificar un dispositivo concreto (si hay varios conectados)
uv run python -m src.cli export --serial <NUMERO_DE_SERIE>

# Guardar en una carpeta de salida personalizada
uv run python -m src.cli export --output-dir "D:/mis_exports_whatsapp"
```

### Consultar historial de ejecuciones previas
```bash
uv run python -m src.cli history
```

### Descifrar y exportar un backup local (sin teléfono conectado)
```bash
uv run python -m src.cli parse-local "data/backups/archivo.crypt15" -k "CLAVE_HEX"
```

---

## 3. Calidad y Pruebas

### Ejecutar suite completa de pruebas (pytest)
```bash
uv run pytest
```

### Ejecutar solo pruebas unitarias o de integración
```bash
uv run pytest tests/unit
uv run pytest tests/integration
```

### Comprobar y formatear código con ruff
```bash
uv run ruff check src
uv run ruff format src
```

---

## 4. Archivos de Salida

Los resultados se encuentran en `data/exports/`:
- `data/exports/all_messages.csv`: Todos los mensajes en una sola tabla.
- `data/exports/conversations.csv`: Resumen de conversaciones y métricas.
- `data/exports/conversations/`: Archivos CSV individuales por cada chat.
- `data/exports/manifest.json`: Metadatos técnicos y hashes de la exportación.

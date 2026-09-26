# Comandos Frecuentes — WhatsApp Backup to CSV

Guía rápida de comandos para desarrollo, pruebas y ejecución de la aplicación.

---

## 1. Detección de Cuentas (Principal y Xiaomi Dual Apps)

### Listar cuentas de WhatsApp detectadas en el teléfono conectado
```bash
uv run python -m src.cli accounts
```
*Identifica automáticamente la cuenta estándar (`principal`, User 0) y cuentas duales/clonadas como Xiaomi MIUI/HyperOS (`dual_xiaomi`, User 999 / XSpace).*

---

## 2. Interfaz de Usuario y Ejecución (GUI)

### Iniciar la Interfaz Gráfica
```bash
uv run python -m src.app
```
*O haz doble clic en `scripts\gui.bat`.*
- En la interfaz gráfica, selecciona la cuenta en el menú desplegable (**Principal (Usuario 0)** o **Dual Apps Xiaomi (Usuario 999)**).
- Usa el botón **📷 Capturar Clave (OCR)** para capturar la pantalla del teléfono, delimitar el área y extraer la clave de 64 dígitos de forma aislada para la cuenta activa.

---

## 3. Captura y Extracción OCR de la Clave por Cuenta

### Capturar pantalla por ADB y extraer clave con OCR (CLI)
```bash
# Para la cuenta principal
uv run python -m src.cli capture-key -a principal

# Para la cuenta dual de Xiaomi
uv run python -m src.cli capture-key -a dual_xiaomi

# Capturar y especificar área normalizada (x_min, y_min, x_max, y_max)
uv run python -m src.cli capture-key -a dual_xiaomi --roi 0.08,0.35,0.92,0.65 --save-roi

# Solo imprimir clave por pantalla sin guardarla en el almacén de contraseñas
uv run python -m src.cli capture-key -a dual_xiaomi --no-save
```

---

## 4. Gestión de Claves por Cuenta (OS Keyring)

### Guardar o consultar la clave de 64 caracteres hex por cuenta
```bash
# Guardar clave para cuenta principal
uv run python -m src.cli key set "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES" -a principal

# Guardar clave para cuenta dual de Xiaomi
uv run python -m src.cli key set "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES" -a dual_xiaomi

# Ver estado de la clave almacenada por cuenta
uv run python -m src.cli key get -a principal
uv run python -m src.cli key get -a dual_xiaomi

# Eliminar clave guardada de una cuenta
uv run python -m src.cli key clear -a dual_xiaomi
```

---

## 5. Exportación a CSV

### Consultar estado del teléfono, ADB y cuentas
```bash
uv run python -m src.cli status
```

### Ejecutar exportación completa a CSV
```bash
# Exportar cuenta principal
uv run python -m src.cli export -a principal

# Exportar cuenta dual de Xiaomi
uv run python -m src.cli export -a dual_xiaomi

# Exportación pasando la clave directamente por parámetro
uv run python -m src.cli export -a dual_xiaomi -k "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES"

# Forzar exportación aunque el backup sea idéntico al anterior
uv run python -m src.cli export -a dual_xiaomi --force

# Incluir descarga de archivos multimedia (opcional)
uv run python -m src.cli export -a dual_xiaomi --include-media

# Especificar un dispositivo concreto (si hay varios conectados)
uv run python -m src.cli export --serial <NUMERO_DE_SERIE> -a dual_xiaomi
```

### Consultar historial de ejecuciones previas por cuenta
```bash
uv run python -m src.cli history -a principal
uv run python -m src.cli history -a dual_xiaomi
```

### Descifrar y exportar un backup local (sin teléfono conectado)
```bash
uv run python -m src.cli parse-local "data/backups/msgstore.db.crypt14" -k "CLAVE_HEX" -a dual_xiaomi
```

---

## 6. Calidad y Pruebas

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

## 7. Archivos de Salida

Los resultados se guardan de forma aislada e independiente por cada cuenta en `data/exports/<account_id>/`:
- `data/exports/principal/`:
  - `all_messages.csv`: Todos los mensajes de la cuenta principal.
  - `conversations.csv`: Resumen de conversaciones y métricas.
  - `conversations/`: Archivos CSV individuales por cada chat (`<jid>.csv`).
  - `manifest.json`: Metadatos técnicos, hash SHA-256 y conteo de filas.
- `data/exports/dual_xiaomi/`:
  - `all_messages.csv`: Todos los mensajes de la cuenta dual de Xiaomi.
  - `conversations.csv`: Resumen de conversaciones de la cuenta dual.
  - `conversations/`: Archivos CSV individuales por cada chat.
  - `manifest.json`: Metadatos técnicos del backup de la cuenta dual.

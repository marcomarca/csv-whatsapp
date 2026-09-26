# Manual de Configuración Inicial — WhatsApp Backup to CSV

Este documento describe los pasos para configurar tu ordenador y tu teléfono Android para la extracción automatizada y descifrado de conversaciones a CSV.

---

## 1. Requisitos Previos

1. **Ordenador**:
   - Python 3.11 o superior.
   - Herramienta de gestión de paquetes: `uv` (o `pip`).
   - Android SDK Platform-Tools (`adb.exe`).

2. **Teléfono**:
   - Dispositivo Android con WhatsApp instalado y funcionando.
   - Cable USB con soporte para transmisión de datos.

---

## 2. Configuración en el Teléfono Android

### Paso 1: Habilitar Opciones de Desarrollador
1. Abre **Ajustes** en tu Android.
2. Entra en **Información del teléfono** (o *Acerca del teléfono*).
3. Busca **Número de compilación** (o *Versión de software*).
4. Púlsalo 7 veces consecutivas hasta que aparezca el mensaje *"¡Ya eres desarrollador!"*.
5. Introduce tu PIN o patrón si el sistema lo solicita.

### Paso 2: Activar Depuración por USB
1. Regresa a **Ajustes** > **Sistema** > **Opciones de desarrollador** (en Xiaomi/POCO: *Ajustes adicionales* > *Opciones de desarrollador*).
2. Activa la casilla **Depuración por USB**.
3. Confirma el cuadro de diálogo de seguridad.

### Paso 3: Conectar y Autorizar el Ordenador
1. Conecta el teléfono al ordenador mediante el cable USB.
2. Mantén la pantalla del teléfono desbloqueada.
3. Aparecerá una ventana emergente: *«¿Permitir depuración por USB desde este equipo?»*.
4. Marca la casilla **«Permitir siempre desde este equipo»** y pulsa **Aceptar**.

---

## 3. Configuración del Cifrado de WhatsApp y Clave

### Paso 4: Obtener la Clave de Cifrado de 64 Dígitos
1. Abre **WhatsApp** en tu teléfono.
2. Ve a **Ajustes** > **Chats** > **Copia de seguridad**.
3. Selecciona **Copia de seguridad cifrada de extremo a extremo**.
4. Pulsa **Activar**.
5. Cuando WhatsApp te ofrezca crear una contraseña o **Usar una clave de cifrado de 64 dígitos**, elige **Usar clave de cifrado de 64 dígitos**.
6. Anota o copia cuidadosamente la clave hexadecimal de 64 dígitos generada.
7. Guarda tu clave en tu gestor de contraseñas personal.
8. Pulsa **Crear** o **Guardar** en WhatsApp para generar la primera copia de seguridad cifrada local.

### Paso 5: Registrar la Clave en el Almacén Seguro
Puedes guardar la clave una sola vez de forma protegida en el almacén de credenciales de tu sistema operativo:

```bash
uv run python -m src.cli key set "TU_CLAVE_HEXADECIMAL_DE_64_CARACTERES"
```

O introduce la clave mediante la interfaz gráfica en el botón **🔑 Configurar Clave**.

---

## 4. Ejecución de la Aplicación

### Opción A: Interfaz Gráfica de Escritorio (Recomendada)
```bash
uv run python -m src.app
```
O haciendo doble clic en `scripts/gui.bat`.

### Opción B: Línea de Comandos (CLI)
```bash
# Ver estado del dispositivo y copias
uv run python -m src.cli status

# Ejecutar exportación completa
uv run python -m src.cli export
```

Los resultados normalizados se guardan automáticamente en la carpeta `data/exports/`:
- `data/exports/all_messages.csv`: Todos los mensajes consolidados.
- `data/exports/conversations.csv`: Resumen de todas las conversaciones.
- `data/exports/conversations/`: Un archivo CSV individual por cada chat.
- `data/exports/manifest.json`: Metadatos técnicos de la exportación y hashes de integridad.

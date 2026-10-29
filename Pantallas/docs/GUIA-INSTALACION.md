# 📖 Guía de Instalación y Restauración del Driver

Esta guía detalla los pasos para configurar el driver de pantallas de **Native Instruments Maschine MK3** en Windows para su uso con **Ableton Live 12**, así como el procedimiento para volver al driver de fábrica original.

---

## 📋 Requisitos Previos

1. **Native Instruments Maschine MK3** conectada por USB 2.0.
2. **Ableton Live 12** con el script `CustomMaschineMK3` instalado en:  
   `%USERPROFILE%\Documents\Ableton\User Library\Remote Scripts\CustomMaschineMK3`
3. **Zadig** (utilidad gratuita para controladores USB): [Descargar de zadig.akeo.ie](https://zadig.akeo.ie/).
4. Windows 10 u 11 (64 bits).

---

## ⚡ Paso 1: Configurar WinUSB con Zadig

Para que el servidor de pantallas pueda comunicarse directamente con las pantallas LCD a través del puerto USB Bulk sin interferir con los controles MIDI:

1. Abrí **Zadig** con permisos de Administrador.
2. En el menú superior, hacé clic en **Options** y marcá la casilla **List All Devices**.
3. En el menú desplegable principal, seleccioná con cuidado:  
   👉 **`Maschine MK3 BD (Interface 5)`**  
   *(o en algunos sistemas `Maschine MK3 (Interface 5)`)*
   
   > ⚠️ **¡Atención!** No toques la **Interfaz 0** (MIDI nativo), ni la **Interfaz 4** (botones y pads HID), ni la interfaz principal de audio. Cambiar el driver de otra interfaz deshabilitará temporalmente esas funciones.

4. En la casilla de driver de destino (a la derecha de la flecha verde), seleccioná **WinUSB**.
5. Hacé clic en el botón **Replace Driver** (o **Install Driver**).
6. Una vez completado, desconectá el cable USB de la Maschine MK3 y volvelo a conectar.

---

## 🚀 Paso 2: Iniciar el Driver de Pantallas

Tenés dos opciones para correr el driver:

### Opción A: Usando el binario compilado (Recomendado)
1. Descargá el archivo `.zip` del release (`MaschineMK3AsPush-v1.0.0-windows-x64.zip`) y descomprimilo en una carpeta fija (por ejemplo `C:\MaschineMK3Driver`).
2. Hacé doble clic en **`iniciar.bat`** (o ejecutá `MaschineMK3AsPush.exe`).
3. El supervisor arrancará silenciosamente en segundo plano y se conectará a las pantallas.
4. Para detenerlo, hacé doble clic en **`detener.bat`**.

### Opción B: Ejecución desde el código fuente con Python
Si deseás modificar o depurar el código:
```bash
# Crear entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Iniciar el supervisor
.venv\Scripts\python prototipo\supervisor.py
```

---

## 🔄 Cómo Restaurar el Driver Original de Fábrica

Si querés usar nuevamente el software oficial de Native Instruments (Maschine 2 Standalone / Controller Editor) con soporte oficial de pantallas:

### Método 1: Administrador de Dispositivos (Visual)
1. Con la controladora conectada, presioná <kbd>Win</kbd> + <kbd>X</kbd> y seleccioná **Administrador de dispositivos** (`devmgmt.msc`).
2. Desplegá la categoría **Dispositivos de bus serie universal** (o *Universal Serial Bus devices*).
3. Buscá **`Maschine MK3 BD (Interface 5)`**.
4. Hacé clic derecho y seleccioná **Desinstalar el dispositivo**.
5. Marcá la casilla que dice **"Intentar quitar el controlador de este dispositivo"** (o *Delete driver software*).
6. Hacé clic en **Desinstalar**.
7. Desconectá y reconectá el cable USB de la Maschine MK3. Windows reinstalará automáticamente el driver original oficial de Native Instruments (`nimc3usb.inf`).

### Método 2: Por Consola de Comandos (pnputil)
Si alguna vez se asignó WinUSB a una interfaz incorrecta por error:
1. Abrí PowerShell o CMD como Administrador.
2. Identificá el paquete de driver instalado:
   ```cmd
   pnputil /enum-drivers
   ```
3. Buscá el archivo `oemNN.inf` correspondiente a WinUSB de la Maschine y ejecutá:
   ```cmd
   pnputil /delete-driver oemNN.inf /uninstall /force
   pnputil /scan-devices
   ```

---

## ❓ Solución de Problemas Comunes

| Síntoma | Causa Probable | Solución |
|---|---|---|
| Las pantallas quedan en negro | El servicio no encuentra la interfaz USB 5 o Zadig no se aplicó | Verificá con Zadig que la Interface 5 tenga el driver WinUSB y reconectá el cable USB. |
| Ableton no actualiza los gráficos | El puerto UDP 9017 está bloqueado o el Remote Script no está seleccionado | En Preferencias de Ableton → Link, Tempo & MIDI, asegurate de que `CustomMaschineMK3` esté seleccionado como Superficie de Control. |
| El registro indica "Ya hay un supervisor corriendo" | Existe un proceso previo activo | Ejecutá `detener.bat` o cerrá el proceso `MaschineMK3AsPush.exe` desde el Administrador de Tareas. |
| Registro de eventos y errores | Diagnóstico detallado | Revisá el archivo `%LOCALAPPDATA%\MaschineMK3AsPush\pantallas.log`. |

# 📚 Documentación Técnica del Proyecto

Índice de especificaciones, guías de desarrollo y arquitectura del servidor de pantallas para Native Instruments Maschine MK3 y Ableton Live 12.

---

## 📑 Contenido

1. **[Guía de Instalación y Restauración](GUIA-INSTALACION.md)**  
   Instrucciones paso a paso para configurar WinUSB en la Interface 5 con Zadig, iniciar el driver de pantallas y procedimiento de restauración al controlador original de Native Instruments.

2. **[Prototipo de Pantallas y Protocolo USB](PROTOTIPO-PANTALLAS.md)**  
   Detalle de la arquitectura del prototipo, decodificación del protocolo bulk de Native Instruments, conversión de color a RGB565 y telemetría UDP desde Ableton Live 12.

3. **[Plan de Arquitectura y Roadmap](PLAN.md)**  
   Plan de diseño para el driver nativo definitivo en Go, estimación de latencias, lectura de reportes HID de pads y perillas, gestión de LEDs y portabilidad futura hacia Linux / Push 3.

---

## 🔗 Enlaces Relacionados

- **Repositorio Principal:** [maschine-mk3-as-ableton-push](https://github.com/santiagojorda/maschine-mk3-as-ableton-push)
- **Manual Web Interactivo:** [https://santiagojorda.github.io/maschine-mk3-as-ableton-push/](https://santiagojorda.github.io/maschine-mk3-as-ableton-push/)

# Protocolo del revisor independiente

Un agente distinto de quien escribió el código, con un modelo más capaz, comprueba el trabajo antes de que el orquestador lo fusione. Que los tests pasen no prueba que el código esté bien: el autor y sus tests pueden compartir el mismo malentendido. El revisor existe para encontrar justo eso.

Este protocolo complementa al CI, no lo sustituye. El CI comprueba lo mecánico y siempre ejecuta lo mismo; el revisor aporta criterio.

## Cuándo se usa

- Siempre en PR que tocan autenticación, contraseñas, tokens, claves de API, consultas a la base de datos o llamadas a servicios externos.
- En PR grandes o con muchos archivos.
- Cuando el orquestador lo pide.

No hace falta en cambios pequeños de documentación o configuración que el CI ya valida.

## Entradas

El orquestador entrega: el número del issue, la rama o el PR, y la ruta de la copia de trabajo donde está el código.

## Reglas estrictas

- **Solo lee, ejecuta y reporta.** No edites archivos de la rama bajo revisión, no hagas commits, push ni merge, y no publiques comentarios en GitHub salvo que se pida.
- Para las pruebas de sabotaje trabaja en una **copia temporal** fuera de la rama (o restaura exactamente el archivo con las herramientas de edición, nunca con PowerShell: corrompe los acentos). Verifica con `git status` que la rama quedó intacta.
- Usa bases de datos desechables propias (puerto y nombre de contenedor propios) y bórralas. Nunca toques la base del usuario ni leas sus `.env`.
- No instales paquetes que no puedas verificar como oficiales.

## Pasos

1. **Contrato.** Lee el issue y comprueba, casilla por casilla, que cada criterio de aceptación está cumplido en el código y en los tests. Si una casilla no se puede comprobar, dilo.
2. **Alcance.** Compara los archivos cambiados con el alcance del issue. Marca archivos fuera de lugar, dependencias nuevas (¿fijadas y oficiales?) y cambios en tests existentes.
3. **Ejecución independiente.** En un entorno limpio, instala y ejecuta la suite completa. No te fíes de la salida que reporta el autor.
4. **Sabotaje.** Rompe el código a propósito en las partes críticas (quita una validación, invierte una condición, elimina un filtro por usuario) y comprueba que algún test se pone en rojo. Un test que sigue pasando con el código roto no protege nada.
5. **Seguridad.** Revisa lo que un agente tiende a pasar por alto:
   - Rutas bajo `/me`: ¿filtran siempre por el usuario autenticado? ¿Devuelven 404 para recursos ajenos?
   - Contraseñas: ¿solo se guarda el hash? ¿Hay contraseñas o tokens en logs, errores o respuestas?
   - Consultas: ¿parametrizadas? ¿Hay SQL armado con texto?
   - Secretos: ¿alguna clave en código, tests o documentación? La de RetroAchievements solo en el backend.
   - CORS: ¿no se abrió a `*`?
   - Validación de entradas en el borde.
6. **Casos límite.** Piensa en lo que el autor no probó: vacíos, duplicados, valores extremos, concurrencia, orden de operaciones.
7. **Documentación y deuda.** ¿La documentación refleja el cambio? ¿Lo que se dejó para después está anotado?

## Informe

Entrega un informe en español con:

- **Veredicto:** aprobar, aprobar con observaciones, o pedir cambios.
- **Hallazgos**, cada uno con severidad, ubicación (archivo y línea), el problema, un escenario concreto en el que falla y una sugerencia:
  - **Bloqueante:** impide fusionar (bug, riesgo de seguridad, pérdida de datos, criterio incumplido).
  - **Importante:** debería corregirse pronto, pero no impide fusionar.
  - **Menor:** mejora opcional.
- **Qué comprobaste y cómo**, con la salida real de los comandos.
- **Qué no pudiste verificar.**

## Ciclo de corrección

Si hay hallazgos bloqueantes, el agente de trabajo los corrige y el revisor vuelve a comprobar solo lo afectado. **Máximo dos vueltas.** Si tras la segunda siguen apareciendo bloqueantes, el revisor lo informa al orquestador para que decida cómo seguir.

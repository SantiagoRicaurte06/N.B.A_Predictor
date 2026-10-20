---
name: checklist-lanzamiento
description: Revisa que un sitio web esté listo para producción antes de deployar con 24 puntos que suelen faltar en páginas hechas con IA (legal, privacidad, cookies, HTTPS, SEO, datos estructurados, ficha de Google, imágenes, velocidad, contraste, móvil, 404, enlaces rotos, formularios, spam, contacto, WhatsApp, analíticas, Open Graph y una sola llamada a la acción). Úsala cuando digan "antes de deployar", "checklist de lanzamiento", "¿está lista la página?", "revisa el sitio para producción" o al terminar una landing.
---

# Checklist de lanzamiento web

Una página hecha con IA se ve completa, pero le suelen faltar cosas que una página real necesita. Esta skill revisa 24 puntos, arregla lo que falte y entrega un reporte.

## Flujo

1. **Detecta el stack**: Next.js (App o Pages Router), Astro, Vite/React, SvelteKit, Nuxt, WordPress o HTML plano. Mira `package.json` y la estructura de carpetas.
2. **Compila** el sitio (`npm run build`) e identifica la carpeta de salida (`out/`, `dist/`, `build/`). En Next.js usa `output: 'export'` o revisa el código fuente.
3. **Corre el revisor automático** sobre esa carpeta:
   ```bash
   node <ruta-de-esta-skill>/scripts/revisar.mjs dist
   ```
   Imprime cada punto como ✅ / ⚠️ / ❌ y termina con código 1 si hay errores. `--json` da la salida en JSON.
4. **SPA (React/Vite sin prerender)**: hay un solo `index.html`, así que títulos, Open Graph, 404 y rutas se resuelven en el router. Revisa el código fuente además del script.
5. **Arregla** cada ❌ y ⚠️ con la guía de abajo, de la forma idiomática del framework. No inventes datos legales, de contacto ni IDs: deja un `TODO` visible y avisa.
6. **Revisión manual** de lo que el script no puede confirmar (ver abajo).
7. **Reporte final**: tabla con los 24 puntos, estado y qué se hizo, más los pendientes que necesitan decisión humana.

## Los 24 puntos y cómo arreglarlos

### Legal y confianza
| # | Punto | Cómo arreglarlo |
|---|---|---|
| 1 | **Aviso legal y términos y condiciones** | Página `/aviso-legal` (o `/terminos`) en el footer: titular real (nombre o razón social, NIT/NIF, dirección, contacto), uso del sitio, pagos/reembolsos si aplica y ley aplicable. |
| 2 | **Política de privacidad** | `/privacidad` en el footer: qué datos se recogen, para qué, terceros (analíticas, formularios), cookies, derechos y contacto. Menciona la ley que aplique (Ley 1581 de 2012 en Colombia, RGPD en la UE). |
| 3 | **Aviso de cookies** | Si hay cookies no esenciales (Google Analytics, Meta Pixel, Hotjar…): banner con *Aceptar* y *Rechazar* del mismo peso, enlace a privacidad, y cargar esos scripts solo tras aceptar. Con analíticas sin cookies (Plausible, Umami, Vercel) puede no hacer falta: dilo en la política. |
| 4 | **Forzar HTTPS** | Activa "Force HTTPS" y la redirección 301 http→https en el hosting (Vercel/Netlify lo traen; Apache con `.htaccess`). Ningún recurso ni enlace propio con `http://` (contenido mixto). |
| 20 | **Dirección de contacto real** | `mailto:`/`tel:` y dirección verdaderos en el footer o `/contacto`. Nunca `example.com`, `+1 555` ni "123 Main St". |
| 21 | **Botón de WhatsApp visible** | Botón flotante abajo a la derecha con `https://wa.me/<código-país><número>?text=<mensaje-prellenado-codificado>`, visible en móvil y sin tapar la llamada a la acción. Solo si el negocio atiende por WhatsApp. |

### SEO y presencia en Google
| # | Punto | Cómo arreglarlo |
|---|---|---|
| 5 | **Meta títulos y descripciones** | `<title>` único por página (≤ 60 caracteres, `Página · Marca`) y `meta description` única (≈ 150 caracteres). Next: `metadata`/`generateMetadata`. Astro: props del layout. React SPA: `react-helmet-async`. |
| 6 | **Datos estructurados** | `<script type="application/ld+json">` con `Organization` o `LocalBusiness` (nombre, logo, dirección, teléfono, horario, `sameAs` con redes) y `WebSite`. Más `Product`, `FAQPage` o `Article` si aplica. Valida en search.google.com/test/rich-results. |
| 7 | **Sitemap y robots.txt** | `/sitemap.xml` con las URLs públicas y `/robots.txt` con `Sitemap: https://dominio/sitemap.xml`. Que **no** quede `Disallow: /` de un entorno de pruebas. Next: `app/sitemap.ts` y `app/robots.ts`. Astro: `@astrojs/sitemap`. |
| 8 | **Ficha de Google** | Perfil de Google Business creado y verificado, con la web, horario, fotos y el mismo nombre/dirección/teléfono que el sitio. Sitio verificado en Search Console y sitemap enviado. Enlace a Google Maps en el sitio. |
| 23 | **Imagen Open Graph** | `og:title`, `og:description`, `og:image` 1200×630 con URL absoluta, `og:url` y `twitter:card=summary_large_image`. Next: `app/opengraph-image.png`. Prueba en opengraph.xyz. |

### Imágenes, velocidad y diseño
| # | Punto | Cómo arreglarlo |
|---|---|---|
| 9 | **Favicon** | Propio, no el del template (`vite.svg`, React, Next): `favicon.ico` 32×32, `icon.svg`, `apple-touch-icon.png` 180×180. Next: `app/icon.png`. |
| 10 | **Texto alternativo en las imágenes** | `alt` que describa qué muestra y para qué; `alt=""` solo en decorativas. Nada de `alt="image"` ni el nombre del archivo. |
| 11 | **Imágenes comprimidas** | < 200 KB, en WebP/AVIF, con `width`/`height`. Next: `next/image`. Astro: `<Image />`. Otros: `sharp` o `squoosh`. |
| 12 | **Velocidad de carga optimizada** | Meta: LCP < 2,5 s en móvil (PageSpeed Insights). `loading="lazy"` fuera de la primera pantalla, `defer`/`async` en scripts, dividir bundles grandes, precargar la fuente principal, quitar librerías que no se usan. |
| 13 | **Contraste de colores** | Texto normal ≥ 4.5:1 y grande ≥ 3:1 (WCAG AA). Cuidado con gris claro sobre blanco y texto sobre imágenes. Revisa con Lighthouse → Accesibilidad o axe. |
| 14 | **Que se vea bien en el móvil** | `<meta name="viewport" content="width=device-width, initial-scale=1">` sin bloquear el zoom, diseño que funcione en 375, 768 y 1024 px, botones de al menos 44×44 px, sin scroll horizontal. |
| 24 | **Una sola llamada a la acción** | Una acción principal (ej. "Pide tu demo") repetida igual en el hero y al final. Las demás, como enlaces secundarios. Varios botones del mismo peso compiten y bajan la conversión. |

### Navegación y formularios
| # | Punto | Cómo arreglarlo |
|---|---|---|
| 15 | **Página 404 personalizada** | Con la marca, mensaje claro y enlace al inicio. Next: `app/not-found.tsx`. Astro: `src/pages/404.astro`. Estático: `404.html`. SPA: ruta `*` y el hosting sirviendo `index.html`. |
| 16 | **Enlaces rotos arreglados** | Ningún enlace interno ni ancla sin destino. Tras deployar, revisa también los externos con `npx linkinator https://tu-dominio --recurse`. |
| 17 | **Estado de error en formularios** | Error junto al campo, `aria-invalid="true"` + `aria-describedby`, resumen con `role="alert"`, conservar lo escrito, estado de carga en el botón y manejo del fallo de red. Validar también en el servidor. |
| 18 | **Formularios protegidos contra spam** | Cloudflare Turnstile o hCaptcha, o un campo trampa (honeypot) oculto. Más límite de envíos por IP en el servidor. |
| 19 | **Página de "Gracias"** | `/gracias` tras un envío exitoso: qué pasa ahora y un siguiente paso. Úsala como conversión en las analíticas. |
| 22 | **Analítica instalada** | Plausible, Umami, Vercel Analytics o Google Analytics 4, con el envío o `/gracias` marcado como conversión. Respeta el aviso de cookies (punto 3). |

## Lo que hay que mirar a mano

El script detecta señales, pero no puede confirmar:
- **Ficha de Google (8)**: que el perfil exista, esté verificado y coincida con el sitio.
- **Contraste (13)**: pásalo por Lighthouse o axe.
- **Una sola llamada a la acción (24)**: mira el inicio como un visitante: ¿qué es lo único que quieres que haga?
- **Formularios (17, 18)**: envía uno vacío, uno inválido y prueba sin conexión.
- **Contacto y WhatsApp (20, 21)**: que el correo, teléfono y número respondan.
- **HTTPS (4)**: entra con `http://` y confirma que redirige a `https://`.
- **Móvil y velocidad (12, 14)**: PageSpeed Insights en móvil y el sitio en 375 px.
- **Textos legales (1, 2)**: que no sean genéricos y mencionen la empresa real.

## Reglas

- No inventes datos legales, direcciones, teléfonos, números de WhatsApp ni IDs de analíticas. Pregunta o deja un `TODO` visible.
- No agregues aviso de cookies si el sitio no usa cookies no esenciales; explícalo en la política.
- No agregues WhatsApp si el negocio no atiende por ahí: márcalo como "no aplica".
- Arregla con las herramientas del framework antes que con librerías nuevas.
- Termina siempre con el reporte de los 24 puntos, aunque todo esté bien.

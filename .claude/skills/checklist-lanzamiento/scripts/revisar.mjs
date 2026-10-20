#!/usr/bin/env node
// Revisa la carpeta compilada de un sitio (dist/, out/, build/…) contra los 24 puntos de lanzamiento.
// Uso: node revisar.mjs <carpeta> [--json]
// Sin dependencias (Node 18+). Termina con código 1 si algún punto falla (❌).
// ⚠️ = revisar a mano (el script no puede confirmarlo del todo o es una recomendación).
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative, extname, basename, dirname, posix } from 'node:path';

const args = process.argv.slice(2);
const raiz = args.find((a) => !a.startsWith('--'));
const comoJson = args.includes('--json');
if (!raiz || !existsSync(raiz) || !statSync(raiz).isDirectory()) {
  console.error('Uso: node revisar.mjs <carpeta-compilada> [--json]   (ej: dist, out, build)');
  process.exit(2);
}

// ---------- archivos ----------
const archivos = [];
(function recorrer(dir) {
  for (const nombre of readdirSync(dir)) {
    if (nombre === 'node_modules' || nombre.startsWith('.')) continue;
    const ruta = join(dir, nombre);
    const st = statSync(ruta);
    if (st.isDirectory()) recorrer(ruta);
    else archivos.push({ ruta, rel: relative(raiz, ruta).replaceAll('\\', '/'), ext: extname(nombre).toLowerCase(), tam: st.size });
  }
})(raiz);

const leer = (f) => readFileSync(f.ruta, 'utf8');
const html = archivos.filter((f) => f.ext === '.html');
const css = archivos.filter((f) => f.ext === '.css');
const js = archivos.filter((f) => ['.js', '.mjs'].includes(f.ext));
const imagenes = archivos.filter((f) => ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.svg'].includes(f.ext));
const paginas = html.map((f) => ({ ...f, src: leer(f) }));
const textoHtml = paginas.map((p) => p.src).join('\n');
const textoJs = js.filter((f) => f.tam < 3_000_000).map(leer).join('\n');
const textoCss = css.map(leer).join('\n');
const todo = `${textoHtml}\n${textoJs}`;
const esSpa = paginas.length === 1;
const inicio = paginas.find((p) => p.rel === 'index.html') ?? paginas[0];

const existe = (patron) => archivos.some((f) => patron.test(f.rel));
const enlaza = (patron) => patron.test(textoHtml) || patron.test(textoJs);
const kb = (b) => `${Math.round(b / 1024)} KB`;
const lista = (xs, n = 5) => xs.slice(0, n).join(', ') + (xs.length > n ? ` y ${xs.length - n} más` : '');
const unir = (...partes) => partes.filter(Boolean).join(' · ');
const hayForm = /<form[\s>]/i.test(textoHtml) || /onSubmit|handleSubmit|<form/i.test(textoJs);

const r = [];
const punto = (n, nombre, estado, detalle) => r.push({ n, nombre, estado, detalle });

// 1. Aviso legal y términos
const legal = existe(/(aviso-?legal|legal|termin|terms|condicion)[^/]*(\/index)?\.html$/i)
  || enlaza(/href=["'][^"']*(aviso-?legal|legal|termin|terms|condicion)/i);
punto(1, 'Aviso legal y términos y condiciones', legal ? 'ok' : 'error',
  legal ? 'Hay página o enlace legal: que identifique al titular real (nombre, NIT/NIF, contacto).' : 'Falta /aviso-legal o /terminos enlazado desde el footer.');

// 2. Privacidad
const privacidad = existe(/(privac|privacy)[^/]*(\/index)?\.html$/i) || enlaza(/href=["'][^"']*(privac|privacy)/i);
punto(2, 'Política de privacidad', privacidad ? 'ok' : 'error',
  privacidad ? 'Hay página o enlace de privacidad: revisa que el texto sea real.' : 'Falta /privacidad (o /privacy) enlazado desde el footer.');

// Analíticas (se usan en 3 y 22)
const analiticas = [
  ['Google Analytics', /googletagmanager\.com|gtag\(|google-analytics\.com/i], ['Plausible', /plausible\.io/i],
  ['Umami', /umami/i], ['PostHog', /posthog/i], ['Vercel Analytics', /@vercel\/analytics|_vercel\/insights|va\.vercel-scripts/i],
  ['Microsoft Clarity', /clarity\.ms/i], ['Meta Pixel', /connect\.facebook\.net|fbq\(/i], ['Hotjar', /hotjar/i],
].filter(([, re]) => re.test(todo)).map(([n]) => n);
const conCookies = analiticas.some((n) => ['Google Analytics', 'Meta Pixel', 'Hotjar', 'Microsoft Clarity', 'PostHog'].includes(n));

// 3. Cookies
const banner = /cookie[\s-]?(banner|consent|notice)|consentimiento|aceptar cookies|accept (all )?cookies|cookieconsent|cookiebot|onetrust|klaro/i.test(todo);
punto(3, 'Aviso de cookies', banner ? 'ok' : conCookies ? 'error' : 'aviso',
  banner ? 'Se detectó un aviso: verifica que tenga Rechazar y que bloquee los scripts antes de aceptar.'
    : conCookies ? `Usas ${lista(analiticas)} (con cookies) y no hay aviso.` : 'Sin aviso. Si no usas cookies no esenciales, decláralo en la política.');

// 4. HTTPS
const inseguros = [...new Set((todo.match(/(?:src|href|action|content)=["']http:\/\/[^"']+/gi) ?? [])
  .map((x) => x.replace(/^\w+=["']/, '')).filter((u) => !/http:\/\/(localhost|127\.0\.0\.1|www\.w3\.org|schema\.org)/i.test(u)))];
const redireccion = archivos.find((f) => /^(_redirects|_headers|vercel\.json|netlify\.toml|\.htaccess|staticwebapp\.config\.json)$/i.test(f.rel));
punto(4, 'Forzar HTTPS', inseguros.length ? 'error' : 'aviso',
  unir(inseguros.length ? `Recursos o enlaces con http:// (contenido mixto): ${lista(inseguros, 4)}` : 'Sin recursos http://.',
    'Activa "Force HTTPS" y la redirección http→https en el hosting',
    redireccion ? `config encontrada: ${redireccion.rel}` : ''));

// 5. Títulos y descripciones
const titulos = paginas.map((p) => ({
  rel: p.rel,
  t: (p.src.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? '').trim(),
  d: p.src.match(/<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)["']/i)?.[1]
    ?? p.src.match(/<meta[^>]+content=["']([^"']*)["'][^>]*name=["']description["']/i)?.[1] ?? '',
}));
const sinTitulo = titulos.filter((x) => !x.t).map((x) => x.rel);
const titRep = [...new Set(titulos.map((x) => x.t).filter((t, i, a) => t && a.indexOf(t) !== i))];
const sinDesc = titulos.filter((x) => !x.d).map((x) => x.rel);
const descRep = [...new Set(titulos.map((x) => x.d).filter((d, i, a) => d && a.indexOf(d) !== i))];
const largos = titulos.filter((x) => x.t.length > 60).map((x) => `${x.rel} (${x.t.length})`);
let est5 = sinTitulo.length || sinDesc.length === paginas.length ? 'error' : 'ok';
if (est5 === 'ok' && (titRep.length || descRep.length || sinDesc.length || largos.length) && paginas.length > 0) est5 = 'aviso';
punto(5, 'Meta títulos y descripciones', est5,
  unir(sinTitulo.length ? `Sin <title>: ${lista(sinTitulo)}` : '', sinDesc.length ? `Sin meta description: ${lista(sinDesc)}` : '',
    titRep.length && !esSpa ? `Títulos repetidos: ${lista(titRep.map((t) => `"${t}"`))}` : '',
    descRep.length && !esSpa ? 'Descripciones repetidas entre páginas' : '', largos.length ? `Títulos de más de 60 caracteres: ${lista(largos)}` : '',
    esSpa ? 'Un solo HTML (¿SPA?): revisa títulos y descripciones por ruta en el código' : '')
  || `${paginas.length} página(s) con título y descripción únicos.`);

// 6. Datos estructurados
const ld = paginas.flatMap((p) => [...p.src.matchAll(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)].map((m) => ({ rel: p.rel, json: m[1] })));
const ldMalos = ld.filter((x) => { try { JSON.parse(x.json); return false; } catch { return true; } }).map((x) => x.rel);
const tiposLd = [...new Set(ld.flatMap((x) => { try { const j = JSON.parse(x.json); return [j].flat().flatMap((o) => o['@graph'] ?? [o]).map((o) => o['@type']).flat(); } catch { return []; } }).filter(Boolean))];
punto(6, 'Datos estructurados (JSON-LD)', !ld.length ? 'error' : ldMalos.length ? 'error' : 'ok',
  !ld.length ? 'No hay <script type="application/ld+json">. Agrega Organization o LocalBusiness y WebSite.'
    : ldMalos.length ? `JSON-LD inválido en: ${lista(ldMalos)}` : `Tipos: ${lista(tiposLd)}. Valídalo en search.google.com/test/rich-results.`);

// 7. Sitemap y robots
const sitemap = archivos.find((f) => /^sitemap[\w-]*\.xml$/i.test(f.rel));
const robots = archivos.find((f) => f.rel === 'robots.txt');
const bloqueaTodo = robots && /^\s*disallow:\s*\/\s*$/im.test(leer(robots));
punto(7, 'Sitemap y robots.txt', !sitemap || bloqueaTodo ? 'error' : !robots ? 'aviso' : 'ok',
  unir(sitemap ? `${sitemap.rel} con ${(leer(sitemap).match(/<loc>/g) ?? []).length} URL(s)` : 'Falta sitemap.xml en la raíz',
    !robots ? 'falta robots.txt' : bloqueaTodo ? 'robots.txt bloquea TODO el sitio (Disallow: /)' : /sitemap:/i.test(leer(robots)) ? 'robots.txt apunta al sitemap' : 'robots.txt no menciona el sitemap'));

// 8. Ficha de Google
const verificado = /name=["']google-site-verification["']/i.test(textoHtml) || existe(/^google[0-9a-f]+\.html$/i);
const mapa = /google\.[a-z.]+\/maps|maps\.app\.goo\.gl|g\.page\//i.test(todo);
punto(8, 'Ficha de Google', 'aviso',
  unir(verificado ? 'Search Console verificado (meta o archivo de Google)' : 'Sin verificación de Search Console en el sitio',
    mapa ? 'hay enlace a Google Maps' : 'sin enlace a Google Maps',
    'Revisa a mano: perfil de Google Business creado y verificado, con la web, horario y mismo nombre/dirección/teléfono que el sitio'));

// 9. Favicon
const icono = archivos.filter((f) => /(favicon|icon|apple-touch)[^/]*\.(ico|png|svg)$/i.test(f.rel));
const plantilla = archivos.filter((f) => /(^|\/)(vite|react|next|vercel|astro|svelte|nuxt)\.svg$/i.test(f.rel)).map((f) => f.rel);
const usaPlantilla = /href=["'][^"']*\/(vite|react|next|vercel)\.svg/i.test(textoHtml);
punto(9, 'Favicon', usaPlantilla || !icono.length ? 'error' : plantilla.length ? 'aviso' : 'ok',
  usaPlantilla ? 'El favicon es el del template (vite.svg / react / next).'
    : !icono.length ? 'No hay favicon.' : plantilla.length ? `Quedan logos del template: ${lista(plantilla)}` : `Encontrado: ${lista(icono.map((f) => f.rel))}`);

// 10. Alt
const sinAlt = [];
const altPobre = [];
for (const p of paginas) {
  for (const img of p.src.match(/<img\b[^>]*>/gi) ?? []) {
    const alt = img.match(/\balt=["']([^"']*)["']/i);
    const src = img.match(/\bsrc=["']([^"']+)["']/i)?.[1] ?? '?';
    if (!alt) sinAlt.push(`${p.rel}: ${basename(src)}`);
    else if (/^(image|imagen|img|foto|photo|picture|logo)$|\.(png|jpe?g|webp|svg)$/i.test(alt[1].trim())) altPobre.push(`${p.rel}: alt="${alt[1]}"`);
  }
}
punto(10, 'Texto alternativo en las imágenes', sinAlt.length ? 'error' : altPobre.length ? 'aviso' : 'ok',
  unir(sinAlt.length ? `Sin alt: ${lista(sinAlt)}` : '', altPobre.length ? `Alt poco descriptivo: ${lista(altPobre)}` : '') || 'Todas las <img> del HTML tienen alt.');

// 11. Imágenes comprimidas
const pesadas = imagenes.filter((f) => f.ext !== '.svg' && f.tam > 200 * 1024);
const viejas = imagenes.filter((f) => ['.png', '.jpg', '.jpeg'].includes(f.ext) && f.tam > 100 * 1024 && !pesadas.includes(f));
punto(11, 'Imágenes comprimidas', pesadas.length ? 'error' : viejas.length ? 'aviso' : 'ok',
  unir(pesadas.length ? `Más de 200 KB: ${lista(pesadas.map((f) => `${f.rel} (${kb(f.tam)})`))}` : '',
    viejas.length ? `Pasar a WebP/AVIF: ${lista(viejas.map((f) => `${f.rel} (${kb(f.tam)})`))}` : '') || `${imagenes.length} imagen(es) revisadas.`);

// 12. Velocidad de carga
const pesoJs = js.reduce((s, f) => s + f.tam, 0);
const pesoCss = css.reduce((s, f) => s + f.tam, 0);
const grandes = js.filter((f) => f.tam > 300 * 1024).map((f) => `${f.rel} (${kb(f.tam)})`);
const bloqueantes = paginas.flatMap((p) => (p.src.match(/<head[\s\S]*?<\/head>/i)?.[0].match(/<script\b(?![^>]*\b(async|defer|type=["']module["']))[^>]*\bsrc=[^>]*>/gi) ?? []).map(() => p.rel));
const sinLazy = paginas.reduce((n, p) => n + ((p.src.match(/<img\b[^>]*>/gi) ?? []).filter((i) => !/loading=["']lazy["']/i.test(i)).length > 2 ? 1 : 0), 0);
punto(12, 'Velocidad de carga optimizada', pesoJs > 1024 * 1024 ? 'error' : pesoJs > 400 * 1024 || bloqueantes.length || grandes.length ? 'aviso' : 'ok',
  unir(`JS total ${kb(pesoJs)} · CSS ${kb(pesoCss)}`, grandes.length ? `bundles grandes: ${lista(grandes, 3)}` : '',
    bloqueantes.length ? `scripts que bloquean el render en <head>: ${lista([...new Set(bloqueantes)], 3)}` : '',
    sinLazy ? `${sinLazy} página(s) con varias imágenes sin loading="lazy"` : '',
    'Mide con PageSpeed Insights (meta: LCP < 2,5 s en móvil)'));

// 13. Contraste
const grises = [...new Set((textoCss.match(/(?<![-\w])color:\s*#(?:[cdef][0-9a-f]{2}|[cdef]{3}|[cdef][0-9a-f]{5})\b/gi) ?? []).map((x) => x.replace(/\s+/g, '')))];
punto(13, 'Contraste de colores', 'aviso',
  unir(grises.length ? `Colores de texto muy claros en el CSS: ${lista(grises, 4)} (revisa si van sobre fondo claro)` : '',
    'Revisa a mano con Lighthouse → Accesibilidad o la extensión axe: texto normal ≥ 4.5:1, texto grande ≥ 3:1'));

// 14. Móvil
const sinViewport = paginas.filter((p) => !/<meta[^>]+name=["']viewport["']/i.test(p.src)).map((p) => p.rel);
const media = textoCss.match(/@media[^{]*\(\s*(min|max)-width/gi)?.length ?? 0;
const tailwind = /\b(sm|md|lg|xl):[a-z]/.test(textoHtml);
const bloqueaZoom = /user-scalable\s*=\s*no|maximum-scale\s*=\s*1(\.0)?\b/i.test(textoHtml);
punto(14, 'Que se vea bien en el móvil', sinViewport.length ? 'error' : media || tailwind ? (bloqueaZoom ? 'aviso' : 'ok') : 'aviso',
  unir(sinViewport.length ? `Sin meta viewport: ${lista(sinViewport)}` : `${media} media queries${tailwind ? ' + clases responsive' : ''}`,
    bloqueaZoom ? 'el viewport bloquea el zoom (quita user-scalable=no / maximum-scale=1)' : '', 'Pruébalo en 375 y 768 px'));

// 15. 404
const p404 = existe(/(^|\/)(404|not-found)(\/index)?\.html$/i);
punto(15, 'Página 404 personalizada', p404 ? 'ok' : esSpa ? 'aviso' : 'error',
  p404 ? 'Existe 404.html.' : esSpa ? 'SPA: revisa que el router tenga ruta "*" y el hosting sirva index.html.' : 'Falta 404.html.');

// 16. Enlaces rotos (internos)
const rutas = new Set(archivos.map((f) => `/${f.rel}`));
const resuelve = (url, desde) => {
  let ruta = url.split(/[?#]/)[0];
  if (!ruta) return true;
  ruta = ruta.startsWith('/') ? ruta : posix.join('/', dirname(desde), ruta);
  ruta = posix.normalize(decodeURIComponent(ruta));
  return [ruta, `${ruta}.html`, posix.join(ruta, 'index.html')].some((c) => rutas.has(c)) || ruta === '/';
};
const rotos = [];
for (const p of paginas) {
  for (const m of p.src.matchAll(/\b(?:href|src)=["']([^"']+)["']/gi)) {
    const url = m[1];
    if (/^(https?:|mailto:|tel:|data:|javascript:|#|\/\/|\{)/i.test(url)) {
      if (url.startsWith('#') && url.length > 1 && !new RegExp(`id=["']${url.slice(1).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["']`).test(p.src)) rotos.push(`${p.rel} → ${url}`);
      continue;
    }
    if (!resuelve(url, p.rel)) rotos.push(`${p.rel} → ${url}`);
  }
}
const rotosUnicos = [...new Set(rotos)];
punto(16, 'Enlaces rotos arreglados', rotosUnicos.length ? (esSpa ? 'aviso' : 'error') : 'ok',
  unir(rotosUnicos.length ? `Enlaces internos sin destino: ${lista(rotosUnicos, 6)}` : 'Enlaces internos y anclas OK',
    esSpa && rotosUnicos.length ? 'en una SPA algunas rutas las resuelve el router: confírmalas' : '',
    'Externos: revísalos con `npx linkinator <url-del-sitio>` después de deployar'));

// 17. Errores en formularios
const senalesError = /aria-invalid|role=["']alert["']|aria-live|aria-errormessage|setCustomValidity|\berror(Message|s)?\b/i.test(todo);
punto(17, 'Estado de error en formularios', !hayForm ? 'ok' : senalesError ? 'aviso' : 'error',
  !hayForm ? 'No se detectaron formularios.' : senalesError ? 'Hay manejo de errores: pruébalo a mano (vacío, inválido, sin red).' : 'Formularios sin errores accesibles (aria-invalid, role="alert").');

// 18. Anti-spam
const antispam = [
  ['reCAPTCHA', /recaptcha|grecaptcha/i], ['hCaptcha', /hcaptcha/i], ['Cloudflare Turnstile', /turnstile|challenges\.cloudflare\.com/i],
  ['honeypot', /_gotcha|honeypot|name=["'](website|url|fax|bot-field)["'][^>]*(hidden|tabindex=["']-1|display:\s*none)|data-netlify-honeypot/i],
].filter(([, re]) => re.test(todo)).map(([n]) => n);
punto(18, 'Formularios protegidos contra spam', !hayForm ? 'ok' : antispam.length ? 'ok' : 'error',
  !hayForm ? 'No se detectaron formularios.' : antispam.length ? `Protección: ${lista(antispam)}. Valida también en el servidor (límite de envíos).` : 'Sin captcha ni honeypot: agrega Turnstile/hCaptcha o un campo trampa oculto.');

// 19. Gracias
const gracias = existe(/(gracias|thank|success|exito|confirm)[^/]*(\/index)?\.html$/i) || enlaza(/\/(gracias|thank-?you|thanks|success)/i);
punto(19, 'Página de "Gracias"', gracias ? 'ok' : hayForm ? 'error' : 'aviso',
  gracias ? 'Hay página de confirmación: que diga qué pasa ahora y ofrezca un siguiente paso.'
    : hayForm ? 'Tras enviar un formulario debe haber una página o estado de confirmación.' : 'Sin formularios: solo hace falta si hay registros o compras.');

// 20. Contacto real
const contacto = [...new Set(todo.match(/mailto:[^"'\s>]+|tel:[^"'\s>]+/gi) ?? [])];
const falso = contacto.filter((c) => /example\.|tudominio|yourdomain|test@|\b555\b|1234567/i.test(c));
punto(20, 'Dirección de contacto real', !contacto.length ? (existe(/contact/i) ? 'aviso' : 'error') : falso.length ? 'error' : 'aviso',
  !contacto.length ? 'No hay mailto: ni tel:. Agrega un correo o teléfono real.'
    : falso.length ? `Datos de ejemplo: ${lista(falso)}` : `Encontrado: ${lista(contacto, 3)}. Confirma que alguien responde.`);

// 21. WhatsApp
const wa = [...new Set(todo.match(/https?:\/\/(?:wa\.me|api\.whatsapp\.com\/send|web\.whatsapp\.com\/send)[^"'\s>)]*/gi) ?? [])];
const waFalso = wa.filter((u) => /wa\.me\/?(\?|$)|phone=(\D|$)|0000|1234567|555/i.test(u));
punto(21, 'Botón de WhatsApp visible', !wa.length ? 'error' : waFalso.length ? 'error' : 'aviso',
  !wa.length ? 'No hay enlace wa.me. Agrega un botón flotante (si el negocio atiende por WhatsApp).'
    : waFalso.length ? `Número vacío o de ejemplo: ${lista(waFalso, 2)}` : `Encontrado: ${lista(wa, 2)}. Revisa a mano que se vea en móvil y tenga mensaje prellenado (?text=).`);

// 22. Analíticas
punto(22, 'Analítica instalada', analiticas.length ? 'ok' : 'error',
  analiticas.length ? `Detectado: ${lista(analiticas)}. Marca el envío o la página de gracias como conversión.` : 'No se detectó ninguna herramienta de analíticas.');

// 23. Open Graph
const sinOg = paginas.filter((p) => !/property=["']og:image["']/i.test(p.src)).map((p) => p.rel);
const ogRelativa = paginas.filter((p) => /property=["']og:image["'][^>]+content=["']\/(?!\/)/i.test(p.src) || /content=["']\/(?!\/)[^"']*["'][^>]+property=["']og:image["']/i.test(p.src)).map((p) => p.rel);
punto(23, 'Imagen Open Graph', sinOg.length === paginas.length ? 'error' : sinOg.length || ogRelativa.length ? 'aviso' : 'ok',
  sinOg.length === paginas.length ? 'Ninguna página tiene og:image.'
    : unir(sinOg.length ? `Sin og:image: ${lista(sinOg)}` : '', ogRelativa.length ? `og:image con URL relativa (debe ser absoluta): ${lista(ogRelativa)}` : '') || 'Todas las páginas tienen og:image.');

// 24. Una sola llamada a la acción
const ctas = inicio ? [...new Set([...inicio.src.matchAll(/<(a|button)\b([^>]*)>([\s\S]*?)<\/\1>/gi)]
  .filter(([, tag, attrs]) => /class=["'][^"']*\b(btn|button|cta)\b/i.test(attrs) || (tag.toLowerCase() === 'button' && !/type=["'](submit|reset)["']/i.test(attrs)))
  .map(([, , , txt]) => txt.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim()).filter((t) => t && t.length < 40))] : [];
punto(24, 'Una sola llamada a la acción', 'aviso',
  unir(ctas.length ? `Botones en el inicio: ${lista(ctas.map((t) => `"${t}"`), 6)}` : 'No se detectaron botones con clase btn/button/cta en el inicio',
    ctas.length > 2 ? 'hay varias acciones compitiendo: elige UNA principal y deja las demás como secundarias' : '',
    'Revisa a mano: una acción principal, repetida igual en el hero y al final'));

// ---------- salida ----------
r.sort((a, b) => a.n - b.n);
if (comoJson) {
  console.log(JSON.stringify({ carpeta: raiz, paginas: paginas.length, resultados: r }, null, 2));
} else {
  const icono2 = { ok: '✅', aviso: '⚠️ ', error: '❌' };
  console.log(`\nChecklist de lanzamiento · ${raiz} · ${paginas.length} página(s) HTML\n`);
  for (const x of r) console.log(`${icono2[x.estado]} ${String(x.n).padStart(2)}. ${x.nombre}\n      ${x.detalle}`);
  const c = (e) => r.filter((x) => x.estado === e).length;
  console.log(`\nResultado: ${c('ok')} ✅ · ${c('aviso')} ⚠️  · ${c('error')} ❌`);
  console.log('Los ⚠️ necesitan revisión manual; 8, 13 y 24 siempre se confirman a mano.\n');
}
process.exit(r.some((x) => x.estado === 'error') ? 1 : 0);

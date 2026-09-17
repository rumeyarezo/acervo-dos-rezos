/* ============================================================
   Acervo dos Rezos — Service Worker

   O que ele faz, em uma frase: guarda uma cópia do aplicativo no
   celular para que ele abra mesmo sem internet.

   IMPORTANTE AO PUBLICAR UMA NOVA VERSÃO:
   mude o número em CACHE_VERSION abaixo (v1 -> v2 -> v3...).
   É isso que avisa os celulares de que existe versão nova.
   Se você esquecer, as pessoas continuam vendo a versão antiga.
   ============================================================ */

const CACHE_VERSION = 'v4';
const SHELL_CACHE = `acervo-shell-${CACHE_VERSION}`;
const RUNTIME_CACHE = `acervo-runtime-${CACHE_VERSION}`;

/* Arquivos do próprio aplicativo. São baixados de uma vez na instalação. */
const SHELL_FILES = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
  './apple-touch-icon.png'
];

/* ---------- INSTALAÇÃO ---------- */
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    // Baixa um por um: se um arquivo faltar (ex.: ícone ainda não subiu),
    // a instalação não é perdida inteira por causa dele.
    await Promise.all(SHELL_FILES.map(async url => {
      try {
        await cache.add(new Request(url, { cache: 'reload' }));
      } catch (e) {
        console.warn('[SW] não consegui pré-cachear', url, e);
      }
    }));
    // Não chama skipWaiting aqui de propósito: a nova versão só entra
    // quando a pessoa confirmar no aviso, para não trocar o app embaixo
    // de quem está lendo uma cifra no meio de um rezo.
  })());
});

/* ---------- ATIVAÇÃO: limpa caches de versões antigas ---------- */
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const nomes = await caches.keys();
    await Promise.all(
      nomes
        .filter(nome => nome.startsWith('acervo-') && nome !== SHELL_CACHE && nome !== RUNTIME_CACHE)
        .map(nome => caches.delete(nome))
    );
    if (self.registration.navigationPreload) {
      try { await self.registration.navigationPreload.enable(); } catch (e) {}
    }
    await self.clients.claim();
  })());
});

/* ---------- Mensagem vinda da página ---------- */
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

/* ---------- Estratégias ---------- */

function ehSupabase(url) {
  return url.hostname.endsWith('.supabase.co');
}

function ehFonteGoogle(url) {
  return url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';
}

/* Rede primeiro: usado para abrir o app. Assim, quem está online sempre
   recebe a versão mais nova; quem está offline recebe a cópia guardada. */
async function redePrimeiro(event) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const preload = event.preloadResponse ? await event.preloadResponse : null;
    const resposta = preload || await fetch(event.request);
    if (resposta && resposta.ok) cache.put('./index.html', resposta.clone());
    return resposta;
  } catch (e) {
    const guardada = await cache.match('./index.html') || await cache.match('./');
    if (guardada) return guardada;
    return new Response(
      '<!doctype html><meta charset="utf-8"><title>Sem conexão</title>' +
      '<body style="font-family:sans-serif;background:#26432f;color:#f7f4e8;padding:40px;text-align:center">' +
      '<h1>Sem conexão</h1><p>Abra o Acervo dos Rezos uma vez com internet para poder usá-lo offline depois.</p></body>',
      { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 503 }
    );
  }
}

/* Cache primeiro: arquivos que não mudam sem trocar de nome (ícones). */
async function cachePrimeiro(request, nomeCache) {
  const cache = await caches.open(nomeCache);
  const guardada = await cache.match(request);
  if (guardada) return guardada;
  const resposta = await fetch(request);
  if (resposta && resposta.ok) cache.put(request, resposta.clone());
  return resposta;
}

/* Guardado primeiro, atualiza depois: as fontes aparecem na hora e se
   renovam em segundo plano. */
async function guardadoEAtualiza(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const guardada = await cache.match(request);
  const naRede = fetch(request).then(resposta => {
    if (resposta && (resposta.ok || resposta.type === 'opaque')) cache.put(request, resposta.clone());
    return resposta;
  }).catch(() => null);
  if (guardada) return guardada;
  const resposta = await naRede;
  return resposta || new Response('', { status: 504, statusText: 'Sem conexão' });
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Dados e login do Supabase NUNCA passam pelo cache: sempre rede.
  // Servir uma cifra velha ou um token guardado causaria confusão real.
  if (ehSupabase(url)) return;

  // Abrir o app (navegação)
  if (request.mode === 'navigate') {
    event.respondWith(redePrimeiro(event));
    return;
  }

  // Fontes do Google
  if (ehFonteGoogle(url)) {
    event.respondWith(guardadoEAtualiza(request));
    return;
  }

  // Arquivos do próprio site
  if (url.origin === self.location.origin) {
    event.respondWith((async () => {
      try {
        return await cachePrimeiro(request, SHELL_CACHE);
      } catch (e) {
        const guardada = await caches.match(request);
        // respondWith nunca pode devolver "undefined": sem cópia guardada,
        // devolvemos um 504 explícito em vez de quebrar a requisição.
        return guardada || new Response('', { status: 504, statusText: 'Sem conexão' });
      }
    })());
    return;
  }

  // Qualquer outra coisa (pdf.js, Tesseract etc.): rede direto, sem cache.
  // São arquivos grandes e só fazem sentido com internet de qualquer forma.
});

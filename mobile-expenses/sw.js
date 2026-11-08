const CACHE='expenses-shell-v4';
const DATA_CACHE='expenses-data-v1';
const SHELL=['./','./index.html','./styles.css','./app.js','./manifest.webmanifest','./icon.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE&&k!==DATA_CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.pathname.endsWith('/data.json')){
    // Ключ без query (?ts=... меняется каждый заход): иначе каждая загрузка
    // клала бы новую запись, а офлайн-поиск промахивался бы мимо.
    const key = url.origin + url.pathname;
    event.respondWith(
      fetch(event.request,{cache:'no-store'}).then(response=>{
        if(response && response.ok){
          const copy=response.clone();
          caches.open(DATA_CACHE).then(cache=>cache.put(key,copy));
        }
        return response;
      }).catch(()=>caches.match(key))
    );
    return;
  }
  event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)));
});

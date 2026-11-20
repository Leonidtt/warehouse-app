/* Only loaded from /pwa/, never from the Telegram Mini App. */
(function () {
  'use strict';
  if (!/^\/pwa\/?$/.test(location.pathname) || window.Telegram?.WebApp?.initData) return;
  const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  if (isStandalone()) document.body.classList.add('pwa-mode');
  const card = document.querySelector('#screen-login .login-card');
  if (card) {
    const description = card.querySelector('p');
    if (description) description.textContent = 'Откройте основного бота «Склад» в Telegram, на Главной выберите «Вход на сайт» и введите полученный код здесь.';
    const help = document.createElement('div');
    help.className = 'pwa-install-info';
    const heading = document.createElement('strong');
    heading.textContent = isStandalone() ? 'Приложение установлено' : 'Установить «Склад» на телефон';
    const info = document.createElement('p');
    const apple = /iPhone|iPad|iPod/i.test(navigator.userAgent);
    info.textContent = isStandalone()
      ? 'Для входа используйте одноразовый код из Telegram. После входа сессия действует до 30 дней, её можно завершить в настройках.'
      : apple
        ? 'В Safari нажмите «Поделиться» → «На экран Домой». Затем запустите «Склад» с главного экрана и войдите по коду из Telegram.'
        : 'Откройте меню браузера и выберите «Установить приложение» или «Добавить на главный экран». После установки войдите по коду из Telegram.';
    help.append(heading, info);
    card.append(help);
    window.addEventListener('beforeinstallprompt', event => {
      if (isStandalone()) return;
      event.preventDefault();
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'secondary';
      button.textContent = 'Установить «Склад»';
      button.onclick = async () => {
        button.disabled = true;
        try { await event.prompt(); await event.userChoice; }
        finally { button.remove(); }
      };
      help.append(button);
    }, {once:true});
  }
  if ('serviceWorker' in navigator) {
    const register = () => navigator.serviceWorker.register('/pwa/sw.js', {scope:'/pwa/'})
      .catch(error => console.warn('PWA registration:', error));
    if (document.readyState === 'complete') register();
    else window.addEventListener('load', register, {once:true});
  }
  // iOS Safari lacks BarcodeDetector. Use the locally hosted Apache-2.0 jsQR decoder.
  // The existing camera button, manual entry and Telegram scanner remain untouched.
  if (typeof window.BarcodeDetector === 'undefined' && navigator.mediaDevices?.getUserMedia) {
    const script = document.createElement('script');
    script.src = '/pwa/jsqr.js?v=1';
    script.async = true;
    script.onload = () => {
      if (typeof window.jsQR !== 'function' || typeof window.BarcodeDetector !== 'undefined') return;
      window.BarcodeDetector = class {
        constructor() {
          this.canvas = document.createElement('canvas');
          this.context = this.canvas.getContext('2d', {willReadFrequently:true});
        }
        async detect(video) {
          if (!this.context || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return [];
          const ratio = Math.min(1, 700 / video.videoWidth);
          const width = Math.max(1, Math.round(video.videoWidth * ratio));
          const height = Math.max(1, Math.round(video.videoHeight * ratio));
          if (this.canvas.width !== width) this.canvas.width = width;
          if (this.canvas.height !== height) this.canvas.height = height;
          this.context.drawImage(video, 0, 0, width, height);
          const pixels = this.context.getImageData(0, 0, width, height);
          const qr = window.jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts:'attemptBoth'});
          return qr?.data ? [{rawValue:qr.data}] : [];
        }
      };
    };
    script.onerror = () => console.warn('The optional PWA QR decoder could not be loaded.');
    document.head.append(script);
  }
})();

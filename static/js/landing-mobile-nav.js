(() => {
 const dialog = document.getElementById('landing-menu-drawer');
 const opener = document.querySelector('[data-open-landing-menu]');
 if (!dialog || !opener) return;
 opener.setAttribute('aria-expanded', 'false');
 opener.addEventListener('click', () => { dialog.showModal(); opener.setAttribute('aria-expanded', 'true'); });
 dialog.querySelector('[data-close-landing-menu]').addEventListener('click', () => dialog.close());
 dialog.addEventListener('close', () => { opener.setAttribute('aria-expanded', 'false'); opener.focus(); });
 dialog.querySelectorAll('a').forEach(link => link.addEventListener('click', () => dialog.close()));
 dialog.addEventListener('click', event => { if (event.target === dialog) { const r=dialog.getBoundingClientRect(); if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom) dialog.close(); } });
})();

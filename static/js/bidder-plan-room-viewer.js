(function () {
  'use strict';

  const root = document.getElementById('prViewerRoot');
  const host = document.getElementById('prViewerHost');
  if (!root || !host) return;

  const streamUrl = root.dataset.streamUrl;
  const mime = (root.dataset.mime || '').toLowerCase();

  if (!streamUrl) return;

  if (mime.startsWith('image/')) {
    const img = document.createElement('img');
    img.className = 'pr-viewer-image';
    img.alt = root.dataset.title || 'Document';
    img.src = streamUrl;
    host.innerHTML = '';
    host.appendChild(img);
    return;
  }

  if (mime === 'application/pdf' || streamUrl) {
    const pdfjs = window.pdfjsLib;
    if (!pdfjs) {
      host.innerHTML = '<p class="pr-muted">PDF viewer failed to load. <a href="' + streamUrl + '">Open file</a></p>';
      return;
    }
    pdfjs.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    host.innerHTML = '<div class="pr-pdf-toolbar"><button type="button" id="prPdfPrev">Prev</button><span id="prPdfPage">Page 1</span><button type="button" id="prPdfNext">Next</button></div><canvas id="prPdfCanvas"></canvas>';

    let pdfDoc = null;
    let pageNum = 1;
    const canvas = document.getElementById('prPdfCanvas');
    const ctx = canvas.getContext('2d');

    function renderPage(num) {
      pdfDoc.getPage(num).then((page) => {
        const viewport = page.getViewport({ scale: 1.35 });
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        page.render({ canvasContext: ctx, viewport });
        document.getElementById('prPdfPage').textContent = `Page ${num} of ${pdfDoc.numPages}`;
      });
    }

    pdfjs.getDocument({ url: streamUrl, withCredentials: true }).promise.then((pdf) => {
      pdfDoc = pdf;
      renderPage(pageNum);
    }).catch(() => {
      host.innerHTML = '<p class="pr-muted">Could not open PDF in browser. Use Download instead.</p>';
    });

    document.getElementById('prPdfPrev')?.addEventListener('click', () => {
      if (!pdfDoc || pageNum <= 1) return;
      pageNum -= 1;
      renderPage(pageNum);
    });
    document.getElementById('prPdfNext')?.addEventListener('click', () => {
      if (!pdfDoc || pageNum >= pdfDoc.numPages) return;
      pageNum += 1;
      renderPage(pageNum);
    });
  }
})();

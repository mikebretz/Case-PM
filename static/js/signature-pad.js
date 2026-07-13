/**
 * Signature pad — mouse, touch, and stylus (Surface Pen) via Pointer Events.
 */
(function (global) {
  'use strict';

  function canvasPoint(canvas, clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    };
  }

  function lineWidthForPressure(pressure, base) {
    const p = typeof pressure === 'number' && pressure > 0 ? pressure : 0.5;
    return Math.max(1.2, base * (0.45 + p * 1.1));
  }

  /**
   * @param {HTMLCanvasElement} canvas
   * @param {{ readOnly?: boolean, strokeStyle?: string, baseLineWidth?: number }} options
   */
  function attach(canvas, options = {}) {
    if (!canvas) return null;
    const readOnly = !!options.readOnly;
    const strokeStyle = options.strokeStyle || '#111827';
    const baseLineWidth = options.baseLineWidth || 2.5;
    const ctx = canvas.getContext('2d', { alpha: true });

    ctx.strokeStyle = strokeStyle;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    canvas.style.touchAction = 'none';
    canvas.style.msTouchAction = 'none';

    let drawing = false;
    let lastX = 0;
    let lastY = 0;
    let activePointerId = null;

    const onPointerDown = (e) => {
      if (readOnly) return;
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if (activePointerId != null) return;
      e.preventDefault();
      activePointerId = e.pointerId;
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch (_) { /* ignore */ }
      const pt = canvasPoint(canvas, e.clientX, e.clientY);
      drawing = true;
      lastX = pt.x;
      lastY = pt.y;
      ctx.lineWidth = lineWidthForPressure(e.pressure, baseLineWidth);
      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
    };

    const onPointerMove = (e) => {
      if (!drawing || e.pointerId !== activePointerId) return;
      e.preventDefault();
      const pt = canvasPoint(canvas, e.clientX, e.clientY);
      ctx.lineWidth = lineWidthForPressure(e.pressure, baseLineWidth);
      ctx.lineTo(pt.x, pt.y);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(pt.x, pt.y);
      lastX = pt.x;
      lastY = pt.y;
    };

    const endStroke = (e) => {
      if (e && e.pointerId !== activePointerId) return;
      drawing = false;
      if (activePointerId != null) {
        try {
          canvas.releasePointerCapture(activePointerId);
        } catch (_) { /* ignore */ }
      }
      activePointerId = null;
    };

    const listeners = [
      ['pointerdown', onPointerDown],
      ['pointermove', onPointerMove],
      ['pointerup', endStroke],
      ['pointercancel', endStroke],
      ['pointerleave', endStroke],
    ];

    if (!readOnly) {
      listeners.forEach(([type, fn]) => {
        canvas.addEventListener(type, fn, { passive: false });
      });
      canvas.style.cursor = 'crosshair';
    } else {
      canvas.style.cursor = 'not-allowed';
    }

    return {
      canvas,
      ctx,
      clear() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      },
      destroy() {
        listeners.forEach(([type, fn]) => canvas.removeEventListener(type, fn));
        endStroke({ pointerId: activePointerId });
      },
    };
  }

  global.CasePMSignaturePad = { attach, canvasPoint };
})(window);

import { JSDOM } from 'jsdom';
import React from 'react';

export function setupDom() {
  if (globalThis.window && globalThis.document) {
    return;
  }

  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost:3000',
    pretendToBeVisual: true
  });

  const keys = [
    'window',
    'document',
    'localStorage',
    'HTMLElement',
    'HTMLInputElement',
    'HTMLSelectElement',
    'HTMLButtonElement',
    'Element',
    'Node',
    'Event',
    'CustomEvent',
    'Headers',
    'Request',
    'Response',
    'FormData',
    'MutationObserver'
  ];

  for (const key of keys) {
    if (dom.window[key]) {
      Object.defineProperty(globalThis, key, {
        value: dom.window[key],
        configurable: true,
        writable: true
      });
    }
  }

  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
    writable: true
  });

  Object.defineProperty(globalThis, 'self', {
    value: dom.window,
    configurable: true,
    writable: true
  });

  dom.window.confirm = () => true;
  dom.window.alert = () => {};
  globalThis.React = React;
  globalThis.confirm = () => true;
  globalThis.alert = () => {};
  globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
  globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
  globalThis.requestIdleCallback = (callback) => setTimeout(callback, 1);
  globalThis.cancelIdleCallback = (id) => clearTimeout(id);

  return dom;
}

setupDom();

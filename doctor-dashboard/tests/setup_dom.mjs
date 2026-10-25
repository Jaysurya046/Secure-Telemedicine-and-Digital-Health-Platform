import { JSDOM } from 'jsdom';

export function setupDom() {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost:3001',
    pretendToBeVisual: true
  });

  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.navigator = dom.window.navigator;
  globalThis.localStorage = dom.window.localStorage;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.Event = dom.window.Event;
  globalThis.CustomEvent = dom.window.CustomEvent;
  globalThis.Headers = dom.window.Headers || globalThis.Headers;
  globalThis.Request = dom.window.Request || globalThis.Request;
  globalThis.Response = dom.window.Response || globalThis.Response;
  globalThis.FormData = dom.window.FormData || globalThis.FormData;

  return dom;
}
